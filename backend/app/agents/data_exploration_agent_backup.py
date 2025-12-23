from langchain import hub
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from sqlalchemy import create_engine
from langgraph.prebuilt import ToolNode, tools_condition, create_react_agent
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import MessagesState
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing import TypedDict, Annotated, List, Dict, Any, Optional, Literal
import json
import os
from datetime import datetime
import logging
from pydantic import BaseModel, Field
from app.schemas.chat import DataContext
from app.agents.tools.custom_toolkit import CustomToolkit
from app.agents.state import ExplainableAgentState
from app.agents.nodes.planner_node import PlannerNode
from app.agents.nodes.explainer_node import ExplainerNode

logger = logging.getLogger(__name__)


class DataExplorationAgent:
    """Data Exploration Agent - Specialized for SQL database queries and data analysis with explanations and routing"""
    
    def __init__(self, llm, db_path: str, logs_dir: str = None, checkpointer=None, store=None, use_postgres_checkpointer: bool = True):
        self.llm = llm
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.db = SQLDatabase(self.engine)
        self.toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
        # Filter out sql_db_query tool - all queries should use sql_db_to_df
        self.sql_tools = [tool for tool in self.toolkit.get_tools() if tool.name != "sql_db_query"]
        self.custom_toolkit = CustomToolkit(llm=self.llm, db_engine=self.engine)
        self.custom_tools = self.custom_toolkit.get_tools()
        self.tools = self.sql_tools + self.custom_tools
        self.store = store
        self.explainer = ExplainerNode(llm)
        self.planner = PlannerNode(llm, self.tools)
        # Default logs directory: backend/logs/
        if logs_dir is None:
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            logs_dir = os.path.join(backend_dir, "logs")
        self.logs_dir = logs_dir
        os.makedirs(self.logs_dir, exist_ok=True)
        
        # Set up checkpointer
        if checkpointer is not None:
            self.checkpointer = checkpointer
        elif use_postgres_checkpointer:
            try:
                from app.core.checkpointer import checkpointer_manager
                from app.core.database import db_manager
                from langgraph.checkpoint.postgres import PostgresSaver
                import psycopg
                
                if checkpointer_manager.is_initialized():
                    # Get the database URI and create a persistent connection
                    db_uri = db_manager.get_db_uri()
                    # Create a connection that will be managed by the checkpointer
                    conn = psycopg.connect(db_uri, autocommit=True)
                    self.checkpointer = PostgresSaver(conn)
                else:
                    logger.warning("Checkpointer not initialized, falling back to MemorySaver")
                    self.checkpointer = MemorySaver()
            except Exception as e:
                logger.error(f"Failed to create PostgreSQL checkpointer: {e}")
                self.checkpointer = MemorySaver()
        else:
            self.checkpointer = None
        
        # Create handoff tools and assistant agent
        self.create_handoff_tools()
        
        # Create base assistant agent with routing capabilities
        base_assistant_agent = create_react_agent(
            model=llm,
            tools=[self.transfer_to_data_exploration],
            prompt=(
                "You are an assistant that routes tasks to specialized agents.\n\n"
                "AVAILABLE AGENTS:\n"
                "- data_exploration_agent: Handles database queries and visualizations, SQL analysis, and data exploration\n"
                "  Use this for: SQL queries, database analysis, table inspection, data queries, schema questions, visualizations\n\n"
                "ROUTING LOGIC:\n"
                "- For DATA EXPLORATION queries: Transfer to data_exploration_agent\n"
                "- For general conversation: Respond normally without transferring\n\n"
                "TRANSFER RULES:\n"
                "- IMPORTANT: Only route to agents when you receive a NEW user message, not for agent responses\n"
                "- **CRITICAL: ONLY USE ONE TOOL CALL PER USER MESSAGE for transfers. PASS THE FULL TASK IN A SINGLE CALL.**\n"
                "- **CRITICAL: DO NOT SAY ANYTHING WHEN TRANSFERRING. JUST TRANSFER.**\n"
                "- **Example: If user asks for '3 different charts', call the transfer tool ONCE with the full request**\n\n"
                "EXAMPLES:\n"
                "- 'Show me sales data' → Transfer to data_exploration_agent\n"
                "- 'What tables are in the database?' → Transfer to data_exploration_agent\n"
                "- 'Hello, how are you?' → Respond directly\n"
            ),
            name="assistant"
        )
        
        self._use_planning = None
        self._use_explainer = None
        
        def assistant_agent(state):
            use_planning = state.get("use_planning", True)
            use_explainer = state.get("use_explainer", True)
            agent_type = state.get("agent_type", "data_exploration_agent")
            query = state.get("query", "")
            
            # Store use_planning value for tools to access
            self._use_planning = use_planning
            self._use_explainer = use_explainer
            result = base_assistant_agent.invoke(state)
            
            if isinstance(result, dict):
                result["use_planning"] = use_planning
                result["use_explainer"] = use_explainer
                result["agent_type"] = agent_type
                result["query"] = query
            
            return result
        
        self.assistant_agent = assistant_agent
        
        # Create the graph
        self.graph = self.create_graph()
    
    def create_handoff_tools(self):

        @tool("transfer_to_data_exploration", description="Transfer database and SQL queries to the data exploration agent")
        def transfer_to_data_exploration(
            state: Annotated[Dict[str, Any], InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            task_description: str = ""
        ) -> Command:
            """Transfer to data exploration agent"""
            
            tool_message = {
                "role": "tool",
                "content": f"Transferring to data exploration agent: {task_description}",
                "name": "transfer_to_data_exploration",
                "tool_call_id": tool_call_id,
            }
            
            # Extract query from latest human message for new queries
            query = state.get("query", "")
            status = state.get("status", "approved")
            
            if status == "approved" and "messages" in state and state["messages"]:
                latest_human_msg = self._get_latest_human_message(state["messages"])
                if latest_human_msg:
                    query = latest_human_msg
            
            # Get use_planning value from stored value
            use_planning = self._use_planning
            if use_planning is None:
                use_planning = state.get("use_planning", True)
            
            # Get use_explainer value from state
            use_explainer = self._use_explainer
            if use_explainer is None:
                use_explainer = state.get("use_explainer", True)
            
            update_state = {
                "messages": state.get("messages", []) + [tool_message],
                "agent_type": "data_exploration_agent",
                "routing_reason": f"Transferred to data exploration agent: {task_description}",
                "query": query,
                "plan": state.get("plan", ""),
                "steps": state.get("steps", []),
                "step_counter": state.get("step_counter", 0),
                "human_comment": state.get("human_comment"),
                "status": state.get("status", "approved"),
                "assistant_response": state.get("assistant_response", ""),
                "use_planning": use_planning,
                "use_explainer": use_explainer,
                "visualizations": state.get("visualizations", []),
                "data_context": state.get("data_context")
            }
            
            return Command(
                goto="data_exploration_flow",
                update=update_state,
                graph=Command.PARENT,
            )
        
        self.transfer_to_data_exploration = transfer_to_data_exploration
    
    def create_graph(self):
        """Create the LangGraph state graph"""
        graph = StateGraph(ExplainableAgentState)
        
        # Add nodes
        graph.add_node("assistant", self.assistant_agent)
        graph.add_node("data_exploration_flow", self.data_exploration_entry)
        graph.add_node("planner", self.planner_node)
        graph.add_node("agent", self.agent_node)
        graph.add_node("tools", self.tools_node)
        graph.add_node("tool_explanation", self.tool_explanation_node)
        graph.add_node("explain", self.explainer_node)
        graph.add_node("human_feedback", self.human_feedback)
        
        # Start with assistant for routing
        graph.set_entry_point("assistant")
        
        # Data exploration flow entry point - decides planning vs direct
        graph.add_conditional_edges(
            "data_exploration_flow",
            self.should_plan,
            {
                "planner": "planner",
                "agent": "agent"
            }
        )

        graph.add_edge("planner", "human_feedback")
        graph.add_conditional_edges(
            "human_feedback",
            self.should_execute,
            {
                "agent": "agent",
                "planner": "planner",
                "end": END
            }
        )
        graph.add_conditional_edges(
            "agent",
            self.should_continue,
            {
                "tools": "tool_explanation",
                "end": END
            }
        )
        graph.add_edge("tool_explanation", "tools")
        graph.add_conditional_edges(
            "tools",
            self.should_explain,
            {
                "explain": "explain",
                "agent": "agent"
            }
        )
        graph.add_edge("explain", "agent")
        
        # Compile with checkpointer
        if self.checkpointer:
            if self.store:
                return graph.compile(interrupt_before=["human_feedback"], checkpointer=self.checkpointer, store=self.store)
            else:
                return graph.compile(interrupt_before=["human_feedback"], checkpointer=self.checkpointer)
        else:
            # Fallback to MemorySaver if no checkpointer provided
            return graph.compile(interrupt_before=["human_feedback"], checkpointer=MemorySaver())
    
    def data_exploration_entry(self, state: ExplainableAgentState):
        """Entry point for data exploration flow"""
        status = state.get("status", "approved")
        messages = state.get("messages", [])
        current_query = state.get("query", "")
        
        if status == "approved":
            latest_human_msg = self._get_latest_human_message(messages)
            if latest_human_msg and latest_human_msg != current_query:
                return {
                    **state,
                    "query": latest_human_msg
                }
        
        return state
    
    def _get_latest_human_message(self, messages: List[BaseMessage]) -> Optional[str]:
        """Extract the latest human message from message history"""
        if not messages:
            return None
        for msg in reversed(messages):
            if hasattr(msg, 'content') and hasattr(msg, '__class__') and 'HumanMessage' in str(msg.__class__):
                return msg.content
        return None
    
    def should_plan(self, state: ExplainableAgentState):
        """Determine if planning is needed"""
        use_planning = state.get("use_planning", True)
        
        if use_planning:
            return "planner"  # Go through planning first
        else:
            return "agent"    # Go directly to data exploration
    
    def human_feedback(self, state: ExplainableAgentState):
        """Human feedback interrupt point"""
        pass
    
    def should_execute(self, state: ExplainableAgentState):
        """Determine next step after human feedback"""
        if state.get("status") == "approved":
            return "agent"
        elif state.get("status") == "feedback":
            return "planner"
        else:
            return "end"  # End the conversation
    
    def planner_node(self, state: ExplainableAgentState):
        """Execute planner node"""
        return self.planner.execute(state)
    
    def should_continue(self, state: ExplainableAgentState):
        """Determine if agent should continue to tools or end"""
        messages = state["messages"]
        last_message = messages[-1]
        
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        else:
            return "end"  # End the conversation after agent completes
    
    def should_explain(self, state: ExplainableAgentState):
        """Determine if explanation is needed"""
        use_explainer = state.get("use_explainer", True)
        
        if use_explainer:
            return "explain"
        else:
            return "agent"  # Skip explainer and go directly back to agent
    
    def agent_node(self, state: ExplainableAgentState):
        """Agent node that processes messages and decides on tool usage"""
        messages = state["messages"]
        
        system_message = self._build_system_message()
        
        llm_with_tools = self.llm.bind_tools(self.tools)
        
        conversation_messages = [msg for msg in messages 
                               if not isinstance(msg, SystemMessage)]
        
        all_messages = [SystemMessage(content=system_message)] + conversation_messages
        
        response = llm_with_tools.invoke(all_messages)
        
        return {
            "messages": messages + [response],
            "steps": state.get("steps", []),
            "step_counter": state.get("step_counter", 0),
            "query": state.get("query", ""),
            "plan": state.get("plan", ""),
            "data_context": state.get("data_context"),  
            "visualizations": state.get("visualizations", [])  
        }
    
    def _build_system_message(self):
        """Build system message for the agent"""
        
        base_prompt = """You are a helpful SQL database assistant.

CORE RESPONSIBILITIES:
1. Answer user questions accurately using the available tools.
2. Avoid making assumptions; verify with data.
3. Be efficient: Do not repeat successful tool calls.

RESPONSE STYLE:
- Be direct and concise - answer only what is asked
- Use a clear, professional tone
- Format data as markdown tables when showing query results
- Use code blocks with syntax highlighting for code/SQL
- **NEVER** generate base64 images or any image data - provide explanations only
- When visualizations are needed, use tools (smart_transform_for_viz or large_plotting_tool) - do NOT create images yourself
"""
        db_guidelines = """DATABASE OPERATIONS:

1. **EXPLORATION FIRST**:
   - Always check `sql_db_list_tables` or `sql_db_schema` if you are unsure about table names or columns.
   - Do not guess column names.

2. **QUERY CONSTRUCTION**:
   - Write syntactically correct SQLite queries.
   - **LIMIT RESULTS**: Always use `LIMIT` when appropriate to avoid unnecessarily large datasets.
   - **SELECTIVE**: Select only necessary columns.
   - **READ-ONLY**: SELECT statements ONLY. No INSERT/UPDATE/DELETE.

3. **ERROR HANDLING**:
   - If a query fails, check the error message.
   - Common errors: Wrong column name, syntax error.
   - Fix the query and try ONCE more. If it fails again, ask the user for clarification.
"""

        viz_rules = self._get_visualization_rules()

        tool_rules = """TOOL USAGE & EXECUTION STRATEGY:

1. **THINK BEFORE ACTING**:
   - Before calling a tool, check the conversation history.
   - Has this tool been called with these arguments before? If yes, DO NOT call it again. Use the existing output.
   - Do you have enough information to answer? If yes, stop calling tools and answer.

2. **PREVENTING RECURSION & LOOPS**:
   - You are limited to a small number of tool calls per turn.
   - If a tool fails or returns unexpected results, DO NOT retry immediately with the same arguments.
   - Analyze the error, change your approach, or inform the user.
   - **CRITICAL**: If you find yourself calling the same tool twice with same arguments and still produce error, STOP.

3. **CHOOSING THE RIGHT TOOL**:
   - **sql_db_to_df**: Use for ALL SQL queries. Executes queries and stores results as DataFrame in Redis for other tools.
   - **python_repl**: For calculations/analysis on the DataFrame created by `sql_db_to_df`.
   - **large_plotting_tool**: For static matplotlib images, large datasets (>100 rows), or complex statistical plots. Requires DataFrame from `sql_db_to_df`.
   - **smart_transform_for_viz**: For simple, interactive frontend charts (bar, line, pie) with small datasets (≤100 rows). Requires DataFrame from `sql_db_to_df`.

4. **WORKFLOWS**:
   - **Analysis**: `sql_db_to_df` -> `dataframe_info` -> `python_repl`
   - **Plotting (Matplotlib)**: `sql_db_to_df` -> `large_plotting_tool` 
   - **Plotting (Frontend)**: `sql_db_to_df` -> `smart_transform_for_viz` (when user requests visualization)

5. **DATAFRAME MANAGEMENT**:
   - Always run `sql_db_to_df` first to execute SQL queries and create DataFrame.
   - Always check if DataFrame is available/expired before using `python_repl`, `large_plotting_tool`, or `smart_transform_for_viz`.
   - If expired/missing, run `sql_db_to_df` again to refresh the DataFrame.
"""

        output_rules = """OUTPUT FORMAT - CRITICAL RULES:
🚫 ABSOLUTELY FORBIDDEN - NEVER DO THESE:
- NEVER generate base64 images (data:image/png;base64,...) - THIS IS STRICTLY PROHIBITED
- NEVER create image data in any format (base64, binary, encoded, etc.)
- NEVER include markdown image tags with base64 data
- NEVER generate any image content yourself - ONLY use visualization tools

✅ CORRECT BEHAVIOR:
- For frontend visualizations: ONLY use smart_transform_for_viz tool (returns JSON, not images)
- For matplotlib/static plots: ONLY use large_plotting_tool (it handles image generation and upload)
- For image URLs from database: use standard markdown format ![Alt](url) - but ONLY for URLs from database queries
- Provide ONLY explanations and text responses - let tools handle all image generation
- When visualization tools are called, provide a brief explanation of what was visualized, but DO NOT generate any image data yourself

REMEMBER: Your role is to EXPLAIN and use TOOLS. Tools generate images. You do NOT generate images.
"""

        interaction_rules = """INTERACTION:
- After providing data, you can suggest relevant next steps when helpful
- Example: "Would you like to visualize this data or perform additional analysis?"
- Keep suggestions natural and relevant to the user's workflow
- Focus on answering the user's question completely and clearly
"""

        system_message = f"""{base_prompt}

{db_guidelines}

{viz_rules}

{tool_rules}

{output_rules}

{interaction_rules}

EXAMPLES:

Good Visualization Request:
User: "Show a bar chart of top 5 actors by film count"
Response:
1. Brief summary: "Here are the top 5 actors by film count..."
2. Call smart_transform_for_viz with viz_type='bar'
3. Done - no images or extra suggestions

Things to Avoid:
- GENERATING BASE64 IMAGES - ABSOLUTELY FORBIDDEN - NEVER DO THIS
- Creating any image data yourself - tools handle all image generation
- Including data:image/png;base64,... in any response
- Creating visualizations without user request
- Using unsupported chart types
- Calling the same tool repeatedly with identical arguments
- Looping on failed queries

CRITICAL: If you find yourself about to generate base64 or any image data, STOP. Use a visualization tool instead, or provide only a text explanation.
"""
        
        return system_message
    
    def _get_visualization_rules(self):
        """Get visualization rules with intelligent tool selection logic"""
        try:
            from app.utils.chart_utils import get_supported_charts
            supported = get_supported_charts()
            charts_help = [
                f"  • {chart_type}: variants = {', '.join(info.get('variants', []))}"
                for chart_type, info in supported.items()
            ]
            supported_charts_list = "\n".join(charts_help)
            
            return f"""VISUALIZATION GUIDELINES:

TOOL SELECTION LOGIC:
You have TWO visualization tools available. BOTH require a DataFrame from sql_db_to_df:

1. smart_transform_for_viz (Frontend Interactive Charts):
   • Use for: Interactive frontend charts (bar, line, pie) with ≤ 100 rows
   • Use for: Standard frontend-rendered visualizations that users can interact with
   • Use for: When data can be easily aggregated/summarized
   • Prerequisites: Must run `sql_db_to_df` first to create DataFrame
   • Supported types: {supported_charts_list}
   • Output: JSON format for frontend rendering

2. large_plotting_tool (Matplotlib Static Images):
   • Use for: Static matplotlib images with large datasets (> 100 rows)
   • Use for: Complex scatter plots with many data points
   • Use for: Time series data with many points
   • Use for: Statistical plots (histograms, box plots, etc.)
   • Use for: When user specifically requests "matplotlib", "static image", or "high-quality" plots
   • Use for: Advanced matplotlib features not available in frontend charts
   • Prerequisites: Must run `sql_db_to_df` first to create DataFrame
   • Output: Markdown image syntax with Supabase URL

DECISION PROCESS:
1. First, determine if user wants a visualization (chart, graph, plot, visualize)
2. If yes, run `sql_db_to_df` to execute SQL query and create DataFrame
3. Then, consider the data size, chart type, and user preference:
   - Small data (≤100 rows) + Interactive frontend chart → Use smart_transform_for_viz
   - Large data (>100 rows) OR User requests "matplotlib"/"static" → Use large_plotting_tool
   - Complex statistical plots → Use large_plotting_tool
   - Simple bar/line/pie charts with small data → Use smart_transform_for_viz

KEY DIFFERENTIATION:
• smart_transform_for_viz: Interactive frontend charts, small datasets (≤100 rows), requires DataFrame
• large_plotting_tool: Static matplotlib images, large datasets (>100 rows) OR user requests static/matplotlib, requires DataFrame

IMPORTANT:
• ALWAYS run `sql_db_to_df` first to create the DataFrame before using either visualization tool
• Choose the right tool based on data size, chart type, and user requirements
• ABSOLUTELY DO NOT generate any image data yourself (no base64, no binary, no encoded images)
• NEVER include data:image/png;base64,... in your responses
• Both tools will automatically load the DataFrame from Redis using the data_context
• Your role: Explain what was visualized. Tools' role: Generate images.
"""
        except Exception:
            return """VISUALIZATION GUIDELINES:
• ALWAYS run sql_db_to_df first to create DataFrame before using visualization tools
• Use smart_transform_for_viz for interactive frontend charts with small datasets (≤100 rows)
• Use large_plotting_tool for static matplotlib images with large datasets (>100 rows) or when user requests matplotlib/static plots
• Both tools require DataFrame from sql_db_to_df
• Only call when explicitly requested
• Do not generate image data
"""

    def tool_explanation_node(self, state: ExplainableAgentState):
        """Generate user-friendly explanation before tool execution"""
        messages = state["messages"]
        if not messages:
            return {"messages": []}
        
        last_message = messages[-1]
        
        if not getattr(last_message, 'tool_calls', None):
            return {"messages": []}

        if getattr(last_message, 'content', None):
            return {"messages": []}

        tool_name_to_desc = {}
        for tool in getattr(self, 'tools', []) or []:
            name = getattr(tool, 'name', None)
            desc = getattr(tool, 'description', None)
            if name:
                tool_name_to_desc[name] = desc or "No description available"
        
        tool_descriptions = []
        for call in last_message.tool_calls:
            name = call.get('name', 'unknown')
            args = call.get('args', {})
            desc = tool_name_to_desc.get(name, "No description available")
            
            args_str = json.dumps(args, ensure_ascii=False) if not isinstance(args, str) else args
            if len(args_str) > 200:
                args_str = args_str[:200] + "..."
            
            tool_descriptions.append(f"- {name}: {desc}\n  Args: {args_str}")
        
        tools_text = "\n".join(tool_descriptions)
        
        system_prompt = f"""Provide a concise, user-facing explanation (1–2 sentences) of the next step you will take to answer the question.

Internal context (do not expose tool names):
{tools_text}

Use a clear, professional, conversational tone. Focus on the intent and expected outcome, not too detailed on implementation details.
Do not mention specific tool names or parameters.

Examples:
- 'I'll first review the database structure to identify where this information is stored.'
- 'Now, I'll run a targeted query to retrieve the relevant records and summarize the results.'"""

        try:
            # Include all previous messages for context
            explanation_messages = [SystemMessage(content=system_prompt)] + messages[:-1]
            response = self.llm.invoke(explanation_messages)
            explanation_text = getattr(response, 'content', str(response))
        except Exception:
            explanation_text = f"Running the following tools:\n{tools_text}"
        
        # Modify the existing message instead of adding new one
        modified_message = AIMessage(
            content=explanation_text,
            tool_calls=getattr(last_message, 'tool_calls', None),
            id=getattr(last_message, 'id', None)
        )
        
        # Replace the last message
        return {
            "messages": messages[:-1] + [modified_message]
        }
    
    def tools_node(self, state: ExplainableAgentState):
        """Execute tools and capture step information"""
        messages = state["messages"]
        last_message = messages[-1]
        
        steps = state.get("steps", [])
        step_counter = state.get("step_counter", 0)
    
        # Execute tools
        tool_node = ToolNode(tools=self.tools)
        result = tool_node.invoke(state)
        
        logger.info("Tool node result: %s", result)
        
        # Capture step information for explainer
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                step_counter += 1
                
                # Find the corresponding tool output
                tool_output = None
                for msg in result["messages"]:
                    if hasattr(msg, 'tool_call_id') and msg.tool_call_id == tool_call['id']:
                        tool_output = msg.content
                        break
                
                step_info = {
                    "id": step_counter,
                    "type": tool_call['name'],
                    "tool_name": tool_call['name'],
                    "input": json.dumps(tool_call['args']),
                    "output": tool_output or "No output captured",
                    "context": state.get("query", "Database query"),
                    "timestamp": datetime.now().isoformat()
                }
                
                # Add explanation fields with default values when explainer is disabled
                use_explainer = state.get("use_explainer", True)
                if not use_explainer:
                    step_info.update({
                        "decision": f"Execute {tool_call['name']} tool",
                        "reasoning": f"Used {tool_call['name']} to process the query",
                        "confidence": 0.8,
                        "why_chosen": f"Selected {tool_call['name']} as the appropriate tool"
                    })
                
                steps.append(step_info)
                
                if tool_call['name'] == "smart_transform_for_viz":
                    try:
                        viz_dict = json.loads(tool_output)
                        state["visualizations"].append(viz_dict)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse visualization output: {tool_output}")
                        state["visualizations"].append({"error": "Invalid JSON output"})

                if tool_call['name'] == "sql_db_to_df":
                    logger.info(
                        "sql_db_to_df raw output for tool_call_id=%s: %s",
                        tool_call.get('id'),
                        tool_output,
                    )
                    try:
                        parsed_output = json.loads(tool_output)
                    except (TypeError, json.JSONDecodeError):
                        logger.info(
                            "Failed to parse sql_db_to_df output for tool_call_id=%s. Raw output: %s",
                            tool_call.get('id'),
                            tool_output,
                        )
                        continue
                    
                    data_context_payload = parsed_output.get("data_context")
                    if data_context_payload:
                        try:
                            # Convert shape list to tuple if needed
                            if "shape" in data_context_payload and isinstance(data_context_payload["shape"], list):
                                data_context_payload["shape"] = tuple(data_context_payload["shape"])
                            
                            # Parse datetime strings if needed
                            if "created_at" in data_context_payload and isinstance(data_context_payload["created_at"], str):
                                data_context_payload["created_at"] = datetime.fromisoformat(data_context_payload["created_at"])
                            
                            if "expires_at" in data_context_payload and isinstance(data_context_payload["expires_at"], str):
                                data_context_payload["expires_at"] = datetime.fromisoformat(data_context_payload["expires_at"])
                            
                            state["data_context"] = DataContext(**data_context_payload)
                            logger.info(
                                "Successfully updated data_context for tool_call_id=%s: df_id=%s",
                                tool_call.get('id'),
                                data_context_payload.get('df_id')
                            )
                        except Exception as e:
                            logger.error(
                                "Failed to create DataContext for tool_call_id=%s. Error: %s. Payload: %s",
                                tool_call.get('id'),
                                str(e),
                                data_context_payload,
                                exc_info=True
                            )

        return {
            "messages": result["messages"],
            "steps": steps,
            "step_counter": step_counter,
            "query": state.get("query", ""),
            "plan": state.get("plan", ""),
            "data_context": state.get("data_context"),  # Preserve DataFrame context
            "visualizations": state.get("visualizations", [])  # Preserve visualizations
        }
    
    def explainer_node(self, state: ExplainableAgentState):
        """Explain the last step taken and ensure all steps have required fields"""
        steps = state.get("steps", [])
        updated_steps = []
        
        for i, step in enumerate(steps):
            step_copy = step.copy()
            
            missing_fields = [field for field in ["decision", "reasoning", "confidence", "why_chosen"] 
                             if field not in step_copy]
            
            if missing_fields:
                try:
                    if i == len(steps) - 1:
                        # Get detailed explanation for the last step
                        explanation = self.explainer.explain_step(step_copy)
                        step_copy.update({
                            "decision": explanation.decision,
                            "reasoning": explanation.reasoning,
                            "why_chosen": explanation.why_chosen,
                            "confidence": explanation.confidence
                        })
                    else:
                        # For previous steps, try to generate better defaults based on available data
                        tool_type = step_copy.get('type', 'unknown')
                        tool_result = step_copy.get('result', 'No result available')
                        
                        step_copy.update({
                            "decision": f"Execute {tool_type} tool",
                            "reasoning": f"Used {tool_type} to process the query. Result: {str(tool_result)[:100]}...",
                            "confidence": 0.7,  # Lower confidence for auto-generated explanations
                            "why_chosen": f"Selected {tool_type} as the appropriate tool for this step"
                        })
                except Exception as e:
                    # Fallback if explanation generation fails
                    step_copy.update({
                        "decision": f"Step {i+1} execution",
                        "reasoning": f"Error generating explanation: {str(e)}",
                        "confidence": 0.5,
                        "why_chosen": "Unable to determine reasoning"
                    })
            
            updated_steps.append(step_copy)
        
        return {
            "messages": state["messages"],
            "steps": updated_steps,
            "step_counter": state.get("step_counter", 0),
            "query": state.get("query", ""),
            "plan": state.get("plan", ""),
            "data_context": state.get("data_context"),  # Preserve DataFrame context
            "visualizations": state.get("visualizations", [])  # Preserve visualizations
        }
    
    def continue_with_feedback(self, user_feedback: str, status: str = "feedback", config=None):
        """Continue execution with user feedback"""
        if config is None:
            config = {"configurable": {"thread_id": "main_thread"}}
        
        state_update = {"human_comment": user_feedback, "status": status}
        self.graph.update_state(config, state_update)
        
        events = list(self.graph.stream(None, config, stream_mode="values"))
        return events
    
    def approve_and_continue(self, config=None):
        """Approve plan and continue execution"""
        if config is None:
            config = {"configurable": {"thread_id": "main_thread"}}
        state_update = {"status": "approved"}
        self.graph.update_state(config, state_update)
        
        # Continue execution
        events = list(self.graph.stream(None, config, stream_mode="values"))
        return events

    def update_llm(self, new_llm):
        """Update the LLM for this agent and all its components"""
        logger.info("Updating LLM for DataExplorationAgent")
        
        try:
            # Update the main LLM
            self.llm = new_llm
            
            # Update toolkit with new LLM
            self.toolkit = SQLDatabaseToolkit(db=self.db, llm=new_llm)
            # Filter out sql_db_query tool - all queries should use sql_db_to_df
            self.sql_tools = [tool for tool in self.toolkit.get_tools() if tool.name != "sql_db_query"]
            
            # Update custom toolkit with new LLM and database engine
            self.custom_toolkit = CustomToolkit(llm=new_llm, db_engine=self.engine)
            self.custom_tools = self.custom_toolkit.get_tools()
            
            # Update combined tools
            self.tools = self.sql_tools + self.custom_tools
            
            # Update explainer with new LLM
            self.explainer = ExplainerNode(new_llm)
            
            # Update planner with new LLM and tools
            self.planner = PlannerNode(new_llm, self.tools)
            
            # Recreate the graph with updated components
            self.graph = self.create_graph()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update LLM: {e}")
            return False

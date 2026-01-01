from langchain_core import prompts as hub
from langchain_openai import ChatOpenAI
from sqlalchemy import create_engine
from langgraph.prebuilt import ToolNode, tools_condition, create_react_agent
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import MessagesState
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool, InjectedToolCallId, BaseTool
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import InjectedState
from langgraph.types import Command, Send, interrupt
from langgraph.prebuilt.interrupt import HumanInterrupt, HumanResponse, HumanInterruptConfig, ActionRequest
from typing import TypedDict, Annotated, List, Dict, Any, Optional, Literal, Callable
import json
import os
from datetime import datetime
import logging
import uuid
from pydantic import BaseModel, Field
from app.schemas.chat import DataContext
from app.agents.tools.custom_toolkit import CustomToolkit
from app.agents.state import ExplainableAgentState
from app.agents.nodes.explainable.explainable_planner_node import ExplainablePlannerNode
from app.agents.nodes.explainer_node import ExplainerNode
from app.agents.nodes.error_explainer_node import ErrorExplainerNode
from app.agents.nodes.agent_executor_node import AgentExecutorNode
from app.agents.nodes.task_scheduler_node import TaskSchedulerNode
from app.agents.nodes.joiner_node import JoinerNode
from app.agents.assistant_agent import AssistantAgent

logger = logging.getLogger(__name__)


class DataExplorationAgent:
  
    def __init__(
        self, 
        llm, 
        db_path: str, 
        logs_dir: str = None, 
        checkpointer=None, 
        store=None, 
        use_postgres_checkpointer: bool = True,
        require_tool_approval: bool | Dict[str, bool] = False,
        risky_tools: List[str] = None
    ):
        self.llm = llm
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.require_tool_approval = require_tool_approval
        self.risky_tools = risky_tools or []
        self.custom_toolkit = CustomToolkit(
            llm=self.llm, 
            db_engine=self.engine,
            db_path=self.db_path
        )
        self.tools = self.custom_toolkit.get_tools()

        self.store = store
        self.explainer = ExplainerNode(llm, available_tools=self.tools)
        self.error_explainer = ErrorExplainerNode(llm)
        self.planner = ExplainablePlannerNode(llm, self.tools)
        self.agent_executor = AgentExecutorNode(llm, self.tools)
        self.task_scheduler = TaskSchedulerNode(self.tools)
        self.joiner = JoinerNode(llm)
        
        if logs_dir is None:
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            logs_dir = os.path.join(backend_dir, "logs")
        self.logs_dir = logs_dir
        os.makedirs(self.logs_dir, exist_ok=True)
        
        if checkpointer is not None:
            self.checkpointer = checkpointer
        elif use_postgres_checkpointer:
            try:
                from app.core.checkpointer import checkpointer_manager
                from app.core.database import db_manager
                from langgraph.checkpoint.postgres import PostgresSaver
                import psycopg
                
                if checkpointer_manager.is_initialized():
                    db_uri = db_manager.get_db_uri()
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

        
        self.create_handoff_tools()
        
        self.assistant_agent_instance = AssistantAgent(
            llm=llm,
            transfer_tools=[self.transfer_to_data_exploration]
        )
        self.assistant_agent = self.assistant_agent_instance
        self.agent_executor_node = lambda state: self.agent_executor.execute(state)
        self.joiner_node = lambda state: self.joiner.execute(state)
        
        self.graph = self.create_graph()
        
        # Commented out to prevent blocking during startup
        # Graph visualization can be accessed via /api/v1/graph/visualization-image endpoint
        # self.save_graph_visualization()
    
    def save_graph_visualization(self):
        try:
            graph_image = self.graph.get_graph().draw_mermaid_png()
            
            graph_path = os.path.join(self.logs_dir, "agent_graph.png")
            with open(graph_path, "wb") as f:
                f.write(graph_image)
            
            logger.info(f"Graph visualization saved to: {graph_path}")
        except Exception as e:
            logger.error(f"Failed to generate graph visualization: {e}")
            logger.info("Note: Graph visualization requires pygraphviz. Install with: pip install pygraphviz")
    
 
    def create_handoff_tools(self):
        @tool("transfer_to_data_exploration", description="Transfer database and SQL queries to the data exploration agent")
        def transfer_to_data_exploration(
            state: Annotated[Dict[str, Any], InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            task_description: str = ""
        ) -> Command:
            tool_message = {
                "role": "tool",
                "content": f"Transferring to data exploration agent: {task_description}",
                "name": "transfer_to_data_exploration",
                "tool_call_id": tool_call_id,
            }
            
            query = state.get("query", "")
            status = state.get("status", "approved")
            
            if status == "approved" and "messages" in state and state["messages"]:
                latest_human_msg = self._get_latest_human_message(state["messages"])
                if latest_human_msg:
                    query = latest_human_msg
            
            use_planning = self.assistant_agent_instance.get_planning_flag()
            if use_planning is None:
                use_planning = state.get("use_planning", True)
            
            use_explainer = self.assistant_agent_instance.get_explainer_flag()
            if use_explainer is None:
                use_explainer = state.get("use_explainer", True)
            
            update_state = {
                "messages": state.get("messages", []) + [tool_message],
                "agent_type": "data_exploration_tool",
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
                "data_context": state.get("data_context"),
                "tasks": state.get("tasks", []),
                "observations": state.get("observations", {}),
                "execution_mode": state.get("execution_mode", "parallel")
            }
            
            return Command(
                goto="data_exploration_flow",
                update=update_state,
                graph=Command.PARENT,
            )
        
        self.transfer_to_data_exploration = transfer_to_data_exploration
    
    
    def tool_approval_node(self, state: ExplainableAgentState) -> dict:
        from langgraph.types import interrupt
        
        messages = state.get("messages", [])
        if not messages:
            return {"status": "approved"}
        
        last_message = messages[-1]
        
        if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
            return {"status": "approved"}
        
        if not self.require_tool_approval:
            return {"status": "approved"}
        
        risky_tool_calls = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call.get("name")
            if tool_name in self.risky_tools:
                risky_tool_calls.append(tool_call)
        
        if not risky_tool_calls:
            return {"status": "approved"}
        
        tool_call = risky_tool_calls[0]
        
        request = {
            "interrupt_type": "tool_approval",  # Identify this as tool-level approval
            "action_request": {
                "action": tool_call.get("name"),
                "args": tool_call.get("args", {})
            },
            "config": {
                "allow_ignore": True,
                "allow_respond": False,
                "allow_edit": True,
                "allow_accept": True
            },
            "description": f"Please review and approve the '{tool_call.get('name')}' tool call"
        }
        
        logger.info(f"Tool approval requested for: {tool_call.get('name')}")
        
        response = interrupt(request)
        
        logger.info(f"Tool approval response received: {response.get('type')}")
        
        if response["type"] == "accept":
            return {"status": "approved"}
        elif response["type"] == "edit":
            edited_action = response["args"]
            last_message.tool_calls[0]["args"] = edited_action.args
            return {"status": "approved", "messages": messages}
        elif response["type"] == "ignore":
            return {"status": "rejected"}
        else:
            return {"status": "rejected"}
    
    def route_after_agent(self, state: ExplainableAgentState) -> str:
        
        messages = state.get("messages", [])
        if not messages:
            return "end"
        
        last_message = messages[-1]
        
        if not (hasattr(last_message, 'tool_calls') and last_message.tool_calls):
            if self._has_consecutive_errors(messages):
                logger.info("Agent gave up after error - routing to error_explainer")
                return "error_explainer"
            else:
                logger.info("Agent completed successfully - routing to end")
                return "end"
        
        # Always go to tool_explanation first to generate reasoning
        logger.info("Routing to tool_explanation to generate tool reasoning")
        return "tool_explanation"

    
    def route_after_tool_explanation(self, state: ExplainableAgentState) -> str:
        """Route after tool_explanation: check if approval is needed for risky tools"""
        if not self.require_tool_approval:
            logger.info("Tool approval disabled - routing directly to tools")
            return "tools"
        
        messages = state.get("messages", [])
        if not messages:
            return "tools"
        
        last_message = messages[-1]
        if not (hasattr(last_message, 'tool_calls') and last_message.tool_calls):
            return "tools"
        
        # Check if any tool calls are risky
        for tool_call in last_message.tool_calls:
            if tool_call.get("name") in self.risky_tools:
                logger.info(f"Risky tool detected after explanation: {tool_call.get('name')} - routing to tool_approval")
                return "tool_approval"
        
        # No risky tools - execute directly
        logger.info("No risky tools detected - routing directly to tools")
        return "tools"
    
    def route_after_tool_approval(self, state: ExplainableAgentState) -> str:
        status = state.get("status", "approved")
        if status == "approved":
            return "tools"
        else:
            return "agent"
    
    def create_graph(self):

        graph = StateGraph(ExplainableAgentState)
        
        graph.add_node("assistant", self.assistant_agent)
        graph.add_node("data_exploration_flow", self.data_exploration_entry)
        graph.add_node("planner", self.planner_node)
        graph.add_node("task_scheduler", self.task_scheduler.execute)
        graph.add_node("agent", self.agent_node)
        graph.add_node("tools", self.tools_node)
        graph.add_node("tool_explanation", self.tool_explanation_node)
        graph.add_node("explain", self.explainer_node)
        graph.add_node("human_feedback", self.human_feedback)
        
        graph.add_node("agent_executor", self.agent_executor_node)
        graph.add_node("joiner", self.joiner_node)
        graph.add_node("error_explainer", self.error_explainer_node)
        
        # Add tool_approval node for hybrid HITL
        graph.add_node("tool_approval", self.tool_approval_node)
        
        graph.set_entry_point("assistant")
        
        graph.add_conditional_edges(
            "data_exploration_flow",
            self.should_plan,
            {
                "planner": "planner",
                "agent": "agent"
            }
        )
        
        graph.add_conditional_edges(
            "planner",
            self.route_after_planner,
            {
                "human_feedback": "human_feedback",
                "task_scheduler": "task_scheduler",
                "end": END
            }
        )
        
        graph.add_conditional_edges(
            "human_feedback",
            self.route_after_approval,
            {
                "task_scheduler": "task_scheduler",
                "agent": "agent",
                "planner": "planner",
                "end": END
            }
        )
        
        graph.add_edge("task_scheduler", "agent_executor")
        
        graph.add_conditional_edges(
            "agent_executor",
            self.route_agent_executor,
            {
                "tools": "tools",
                "agent_executor": "agent_executor",
                "joiner": "joiner"
            }
        )
        
        # Tools route back based on execution mode
        graph.add_conditional_edges(
            "tools",
            self.route_after_tools,
            {
                "agent_executor": "agent_executor",  
                "explain": "explain",                
                "agent": "agent",
                "error_explainer": "error_explainer"
            }
        )
        
        graph.add_conditional_edges(
            "joiner",
            self.after_joiner,
            {
                "planner": "planner",
                "error_explainer": "error_explainer",
                "end": END
            }
        )
        
        graph.add_conditional_edges(
            "agent",
            self.route_after_agent,
            {
                "tool_explanation": "tool_explanation",
                "error_explainer": "error_explainer",
                "end": END
            }
        )
        
        # After tool_explanation, check if approval is needed
        graph.add_conditional_edges(
            "tool_explanation",
            self.route_after_tool_explanation,
            {
                "tool_approval": "tool_approval",
                "tools": "tools"
            }
        )
        
        # After tool_approval, go directly to tools
        graph.add_conditional_edges(
            "tool_approval",
            self.route_after_tool_approval,
            {
                "tools": "tools",
                "agent": "agent"
            }
        )
        graph.add_edge("error_explainer", END)
        
        # Update explain node to use conditional routing
        graph.add_conditional_edges(
            "explain",
            self.route_after_explain,
            {
                "agent_executor": "agent_executor",  # Planning mode
                "agent": "agent"  # Non-planning mode
            }
        )
        
        if self.checkpointer:
            if self.store:
                return graph.compile(checkpointer=self.checkpointer, store=self.store)
            else:
                return graph.compile(checkpointer=self.checkpointer)
        else:
            return graph.compile(checkpointer=MemorySaver())
    
    def route_after_planner(self, state: ExplainableAgentState) -> str:
        response_type = state.get("response_type", "plan")
        
        if response_type == "continue":
            logger.info("Planner generated continuation plan - skipping approval")
            return "task_scheduler"
        elif response_type == "cancel":
            logger.info("Planner determined task cannot be solved - ending")
            return "end"
        else:
            logger.info(f"Planner generated new plan (type: {response_type}) - requiring approval")
            return "human_feedback"
    
    def route_after_approval(self, state: ExplainableAgentState) -> str:
        status = state.get("status")
        
        if status == "cancelled":
            return "end"
        elif status == "feedback":
             # If providing feedback/comment, maybe replan
            return "planner"

    
        # Always use dynamic planning with task_scheduler
        return "task_scheduler"
    
    def route_agent_executor(self, state: ExplainableAgentState) -> str:
        messages = state.get("messages", [])
        
        if messages and hasattr(messages[-1], 'tool_calls') and messages[-1].tool_calls:
            return "tools"
        
        continue_execution = state.get("continue_execution", False)
        
        if continue_execution:
            return "agent_executor"
        else:
            return "joiner"
    
    def route_after_tools(self, state: ExplainableAgentState) -> str:
        # Route based on dynamic planning
        dynamic_plan = state.get("dynamic_plan")
        
        if dynamic_plan:
            return "agent_executor"  # Planning mode: continue to next step
        else:
            return "agent"  # Non-planning mode: return to agent
    
    def route_tasks(self, state: ExplainableAgentState):
        return self.task_scheduler.route_tasks(state)
    
    def after_joiner(self, state: ExplainableAgentState) -> str:
        """Route after joiner - NO explainer here anymore (it already ran after each tool)"""
        decision = state.get("joiner_decision")
        
        if decision == "finish":
            if self._has_consecutive_errors(state.get("messages", [])):
                return "error_explainer"
            if state.get("use_explainer") == True:
                return "explain"
            return "end"
        elif decision in ["continue", "replan"]:
            return "planner"
        else:
            logger.warning(f"Unexpected joiner decision: {decision}, defaulting to end")
            return "end"
    
    def route_after_explain(self, state: ExplainableAgentState) -> str:
        """Route after explanation - back to execution loop"""
        dynamic_plan = state.get("dynamic_plan")
        if dynamic_plan:
            return "agent_executor"  # Planning mode: continue to next step
        else:
            return "agent"  # Non-planning mode: return to agent
    
    
    def should_continue_group(self, state: ExplainableAgentState) -> str:
        continue_execution = state.get("continue_execution", False)
        
        if continue_execution:
            return "agent_executor"
        else:
            return "joiner"
    
    def _create_ai_message_for_next_tasks(self, tasks: List[Dict]) -> AIMessage:
        tool_calls = []
        for task in tasks:
            tool_calls.append({
                "name": task["tool_name"],
                "args": task.get("args", {}),
                "id": f"call_task_{task['idx']}",
                "type": "tool_call"
            })
        
        task_descriptions = [f"{t['tool_name']}" for t in tasks]
        content = f"Executing next tasks: {', '.join(task_descriptions)}"
        
        return AIMessage(
            content=content,
            tool_calls=tool_calls
        )
    
    def data_exploration_entry(self, state: ExplainableAgentState):
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
        if not messages:
            return None
        for msg in reversed(messages):
            if hasattr(msg, 'content') and hasattr(msg, '__class__') and 'HumanMessage' in str(msg.__class__):
                return msg.content
        return None
    
    def should_plan(self, state: ExplainableAgentState):
        use_planning = state.get("use_planning", True)
        
        if use_planning:
            return "planner"
        else:
            return "agent"
    
    def human_feedback(self, state: ExplainableAgentState):
        """Node that pauses for human feedback/approval"""
        logger.info("Entering human_feedback node - pausing for input")
        
        # Use interrupt to pause and wait for user input
        # The value returned will be what's passed in Command(resume=...)
        feedback_data = interrupt("awaiting_feedback")
        
        logger.info(f"Received human feedback: {feedback_data}")
        
        updates = {}
        
        # Handle standard feedback payload
        if isinstance(feedback_data, dict):
            if "action" in feedback_data:
                action = feedback_data["action"]
                if action == "cancel":
                    updates["status"] = "cancelled"
                    return updates
                elif action == "feedback":
                    updates["status"] = "feedback"
                    updates["human_feedback"] = feedback_data.get("comment")
                    return updates
        
        return updates
    
    def should_execute(self, state: ExplainableAgentState):
        if state.get("status") == "approved":
            return "agent"
        elif state.get("status") == "feedback":
            return "planner"
        else:
            return "end"  # End the conversation
    
    def planner_node(self, state: ExplainableAgentState):
        return self.planner.execute(state)
    
    def explainer_node(self, state: ExplainableAgentState):
        return self.explainer.execute(state)
    
    def error_explainer_node(self, state: ExplainableAgentState):
        return self.error_explainer.execute(state)
    
    def should_continue(self, state: ExplainableAgentState):
        messages = state["messages"]
        last_message = messages[-1]
        
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:   
            return "tools"
        else:
            if self._has_consecutive_errors(messages):
                logger.info("Agent gave up after error - routing to error_explainer")
                return "error_explainer"
            else:
                logger.info("Agent completed successfully - routing to end")
                return "end" 
    
    def _has_consecutive_errors(self, messages):
        tool_messages = [msg for msg in messages if type(msg).__name__ == 'ToolMessage']
        
        if len(tool_messages) < 1:
            return False
        
        last = tool_messages[-1]
        
        # Check if the ToolMessage has status='error'
        has_status = hasattr(last, 'status')
        if has_status:
            status = getattr(last, 'status', None)
            is_error = status == 'error'
            if is_error:
                return True
        
        if hasattr(last, 'content') and last.content:
            content = str(last.content)
            
            # 1. Try JSON parsing first
            try:
                content_json = json.loads(content)
                if isinstance(content_json, dict) and "error" in content_json:
                    return True
            except json.JSONDecodeError:
                pass
            
            # 2. Fallback to string prefix check
            is_prefix_error = content.startswith("Error:") or "ERROR:" in content or "error" in content.lower()
            return is_prefix_error
        
        return False
    
    def should_explain(self, state: ExplainableAgentState):
        """Route after tools: proceed with normal explanation flow"""
        use_explainer = state.get("use_explainer", True)
        if use_explainer:
            return "explain"
        else:
            return "agent" 
    
    def agent_node(self, state: ExplainableAgentState):
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

CRITICAL ANTI-HALLUCINATION RULES:
- **NEVER invent or guess data** when a tool returns empty output or fails
- **ALWAYS acknowledge** when a query returns no results or a tool fails
- **IF a tool output is empty or "None" or blank**: Explicitly tell the user "The query returned no results" or "The table was not found"
- **DO NOT** fill in plausible-sounding information when you don't have real data
- **VERIFY FIRST**: If a tool fails or returns empty output, try an alternative approach (e.g., list tables first) or inform the user

RESPONSE STYLE:
- Be direct and concise - answer only what is asked
- Use a clear, professional tone
- Format data as markdown tables when showing query results
- Use code blocks with syntax highlighting for code/SQL
- **NEVER** generate base64 images or any image data - provide explanations only
- When visualizations are needed, use tools (smart_transform_for_viz or large_plotting_tool) - do NOT create images yourself
"""
        db_guidelines = """DATABASE OPERATIONS:

1. **UNIFIED DATA ACCESS**:
   - Use `data_exploration_agent` tool for ALL database interactions.
   - This tool automatically:
     - Generates correct SQL
     - Executes the query
     - Caches results in Redis (as DataFrame)
     - Returns metadata and samples
   - **DO NOT** use `text2SQL` or `sql_db_query` manually.
   - Simply ask `data_exploration_agent` for what you need (e.g., "Retrieve sales data for 2023").

2. **HANDLING RESULTS**:
   - The tool returns a JSON with `data_context` (metadata about the cached DataFrame).
   - Use this context for subsequent analysis or visualization.
   - If `data_exploration_agent` returns an error, report it directly (it has built-in retry/refinement).
"""

        viz_rules = self._get_visualization_rules()

        tool_rules = """TOOL USAGE RULES:

1. **DATA RETRIEVAL**:
   - **data_exploration_agent**: Unified tool for all database queries.
     - Input: Natural language question about data
     - Automatically: Generates SQL → Executes → Stores DataFrame in Redis
     - Returns: Data preview and Redis storage ID
     - Example: "Get top 10 users by age" → handles everything automatically

2. **VISUALIZATION**:
   - **smart_transform_for_viz**: For interactive frontend charts (bar, line, pie).
     - Requires: Prior usage of `data_exploration_agent` to load data.
   - **large_plotting_tool**: For static matplotlib plots (complex/large data).
     - Requires: Prior usage of `data_exploration_agent` to load data.

3. **ADVANCED ANALYSIS**:
   - **python_repl**: Use ONLY for complex transformations not possible with SQL.
     - Requires: DataFrame from `data_exploration_agent`.

4. **WORKFLOW**:
   - **Standard**: `data_exploration_agent` → (results shown to user)
   - **With Viz**: `data_exploration_agent` → `smart_transform_for_viz`
   - **Deep Analysis**: `data_exploration_agent` → `python_repl` → `large_plotting_tool`
"""

        output_rules = """OUTPUT FORMAT - CRITICAL RULES:
 ABSOLUTELY FORBIDDEN - NEVER DO THESE:
- NEVER generate base64 images (data:image/png;base64,...) - THIS IS STRICTLY PROHIBITED
- NEVER create image data in any format (base64, binary, encoded, etc.)
- NEVER include markdown image tags with base64 data
- NEVER generate any image content yourself - ONLY use visualization tools

CORRECT BEHAVIOR:
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

Handling Empty Tool Output - WRONG (HALLUCINATION):
User: "Explain the scatter_data table"
Tool: sql_db_query → "" (empty output)
Response: "The scatter_data table has columns: id (INTEGER), x_value (REAL), y_value (REAL)..." ❌
NEVER DO THIS - You just invented data!

Things to Avoid:
- GENERATING BASE64 IMAGES - ABSOLUTELY FORBIDDEN - NEVER DO THIS
- **INVENTING DATA when tools return empty output** - CRITICAL ISSUE
- **GUESSING table structure when PRAGMA returns nothing**
- Creating any image data yourself - tools handle all image generation
- Including data:image/png;base64,... in any response
- Creating visualizations without user request
- Using unsupported chart types
- Calling the same tool repeatedly with identical arguments
- Looping on failed queries

CRITICAL: If you find yourself about to generate base64 or any image data, STOP. Use a visualization tool instead, or provide only a text explanation. CRITICAL: If a tool returns empty output and you don't know the answer, SAY SO. Never make up plausible-sounding data.
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
    
        # Execute tools with error handling
        try:
            tool_node = ToolNode(tools=self.tools)
            result = tool_node.invoke(state)
            
            logger.info("Tool node result: %s", result)
            
            # Check if any tool returned an error
            # ToolNode catches exceptions and returns them as error messages
            for msg in result.get("messages", []):
                if hasattr(msg, 'content') and msg.content:
                    content = str(msg.content)
                    
                    # Check if this is an error message from ToolNode
                    # Covers: ValueError, TypeError, SQLAlchemy errors, etc.
                    is_error = (
                        content.startswith("Error:") or 
                        "OperationalError" in content or 
                        "IntegrityError" in content or
                        "ProgrammingError" in content or
                        ("Error" in content and "Exception" in content)
                    )
                    
                    if is_error:
                        # Extract error details
                        tool_name = "unknown"
                        tool_input = {}
                        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                            tool_call = last_message.tool_calls[0]
                            tool_name = tool_call.get('name', 'unknown')
                            tool_input = tool_call.get('args', {})
                        
                        # Use regex to extract error message and type
                        import re
                        
                        # Pattern 1: Error: ExceptionType('message') or Error: ExceptionType("message")
                        pattern1 = r"Error:\s*(\w+Error|Exception)\(['\"](.+?)['\"]\)"
                        match1 = re.search(pattern1, content)
                        
                        # Pattern 2: (sqlite3.OperationalError) message [SQL: query]
                        pattern2 = r"\((\w+\.\w+)\)\s*(.+?)\s*\[SQL:"
                        match2 = re.search(pattern2, content)
                        
                        if match1:
                            error_type = match1.group(1)
                            error_message = match1.group(2)
                        elif match2:
                            error_type = match2.group(1).split('.')[-1]  # Get "OperationalError" from "sqlite3.OperationalError"
                            error_message = match2.group(2)
                        else:
                            # Fallback: extract first line or first sentence
                            error_type = "ToolExecutionError"
                            # Remove "Error: " prefix if present
                            error_message = content.replace("Error: ", "")
                            # Try to extract detailed error from JSON
                            try:
                                content_json = json.loads(tool_output)
                                if isinstance(content_json, dict) and "error" in content_json:
                                    error_message = content_json["error"]
                            except:
                                pass # Keep original string if not JSON
                        error_info = {
                            "error_message": error_message,
                            "error_type": error_type,
                            "tool_name": tool_name,
                            "tool_input": tool_input
                        }
                        
                        logger.info(f"Detected tool error: {error_info}")
                        
                        # Return state with error information AND tool result messages
                        # Error detection happens in should_continue via consecutive error check
                        return {
                            "error_info": error_info,
                            "messages": result.get("messages", []),
                            "steps": steps,
                            "step_counter": step_counter
                        }
            
        except Exception as e:
            # Capture unexpected errors during tool execution
            logger.error(f"Tool execution error: {e}", exc_info=True)
            
            # Extract tool information from last message
            tool_name = "unknown"
            tool_input = {}
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                tool_call = last_message.tool_calls[0]
                tool_name = tool_call.get('name', 'unknown')
                tool_input = tool_call.get('args', {})
            
            error_info = {
                "error_message": str(e),
                "error_type": type(e).__name__,
                "tool_name": tool_name,
                "tool_input": tool_input
            }
            
            # Return state with error information
            # Error detection happens in should_continue via consecutive error check
            return {
                "error_info": error_info,
                "messages": messages,
                "steps": steps,
                "step_counter": step_counter
            }
        
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
        return self.explainer.execute(state)
    
    def continue_with_feedback(self, user_feedback: str, status: str = "feedback", config=None):
        if config is None:
            config = {"configurable": {"thread_id": "main_thread"}}
        
        state_update = {"human_comment": user_feedback, "status": status}
        self.graph.update_state(config, state_update)
        
        events = list(self.graph.stream(None, config, stream_mode="values"))
        return events
    
    def approve_and_continue(self, config=None):
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
            
            # Update parallel execution components
            self.task_parser = TaskParserNode(new_llm, self.tools)
            self.task_executor = TaskExecutorNode(self.tools)
            self.parallel_scheduler = ParallelSchedulerNode(self.tools)
            self.joiner = JoinerNode(new_llm)
            
            # Recreate the graph with updated components
            self.graph = self.create_graph()
            
            # Regenerate graph visualization
            # Commented out to prevent blocking during LLM updates
            # self.save_graph_visualization()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update LLM: {e}")
            return False

"""
Main Agent with step-by-step execution.

This agent uses a simpler execution model where it executes one plan step at a time,
allowing the agent to make multiple tool calls per step as needed.
"""

from langchain_openai import ChatOpenAI
from sqlalchemy import create_engine
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.types import Command
from typing import List, Dict, Any, Optional, Literal, Annotated
import json
import re
import os
from datetime import datetime
import logging
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import InjectedState
from langchain_core.tools import InjectedToolCallId

from app.agents.tools.custom_toolkit import CustomToolkit
from app.agents.state import ExplainableAgentState
from app.agents.nodes.explainable.explainable_planner_node import ExplainablePlannerNode
from app.agents.nodes.explainer_node import ExplainerNode
from app.agents.nodes.finalizer_node import FinalizerNode
from app.agents.assistant_agent import AssistantAgent

logger = logging.getLogger(__name__)


class MainAgent:
    def __init__(
        self,
        llm,
        db_path: str,
        logs_dir: str = None,
        checkpointer=None,
        store=None,
        use_postgres_checkpointer: bool = True
    ):
        self.llm = llm
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}')
        
        # Initialize toolkit and tools
        self.custom_toolkit = CustomToolkit(
            llm=self.llm,
            db_engine=self.engine,
            db_path=self.db_path
        )
        self.tools = self.custom_toolkit.get_tools()
        
        self.planner = ExplainablePlannerNode(llm, self.tools)
        self.explainer = ExplainerNode(llm, available_tools=self.tools)
        self.finalizer = FinalizerNode(llm)
        
        # Create handoff tools and assistant agent
        self.create_handoff_tools()
        self.assistant_agent_instance = AssistantAgent(
            llm=llm,
            transfer_tools=[self.transfer_to_main_agent]
        )
        self.assistant_agent = self.assistant_agent_instance
        
        # Setup logs directory
        if logs_dir is None:
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            logs_dir = os.path.join(backend_dir, "logs")
        self.logs_dir = logs_dir
        os.makedirs(self.logs_dir, exist_ok=True)
        
        # Setup checkpointer
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
        
        # Setup LangGraph Store for conversation-scoped memories
        if store is not None:
            self.store = store
        else:
            # Use InMemoryStore for development
            from langgraph.store.memory import InMemoryStore
            self.store = InMemoryStore()
            logger.info("Initialized InMemoryStore for conversation memories")
        
        # Build the graph
        self.graph = self.create_graph()
        self.save_graph_visualization()
    
    def save_graph_visualization(self):
        try:
            graph_image = self.graph.get_graph().draw_mermaid_png()
            graph_path = os.path.join(self.logs_dir, "main_agent_graph.png")
            with open(graph_path, "wb") as f:
                f.write(graph_image)
            logger.info(f"Graph visualization saved to: {graph_path}")
        except Exception as e:
            logger.error(f"Failed to generate graph visualization: {e}")
    
    def create_handoff_tools(self):
        """Create handoff tools for assistant agent routing."""
        @tool("transfer_to_main_agent", description="Transfer to the main agent for data exploration and analysis tasks")
        def transfer_to_main_agent(
            state: Annotated[Dict[str, Any], InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            task_description: str = ""
        ) -> Command:
            tool_message = {
                "role": "tool",
                "content": f"Transferring to main agent: {task_description}",
                "name": "transfer_to_main_agent",
                "tool_call_id": tool_call_id,
            }
            
            query = state.get("query", "")
            status = state.get("status", "approved")
            
            # Get latest human message if available
            if status == "approved" and "messages" in state and state["messages"]:
                latest_human_msg = self._get_latest_human_message(state["messages"])
                if latest_human_msg:
                    query = latest_human_msg
            
            update_state = {
                "messages": state.get("messages", []) + [tool_message],
                "agent_type": "main_agent",
                "routing_reason": f"Transferred to main agent: {task_description}",
                "query": query,
                "steps": state.get("steps", []),
                "step_counter": state.get("step_counter", 0),
                "human_comment": state.get("human_comment"),
                "status": state.get("status", "approved"),
                "assistant_response": state.get("assistant_response", ""),
                "visualizations": state.get("visualizations", []),
                "data_context": state.get("data_context"),
            }
            
            return Command(
                goto="main_agent_flow",
                update=update_state,
                graph=Command.PARENT,
            )
        
        self.transfer_to_main_agent = transfer_to_main_agent
    
    def _get_latest_human_message(self, messages: List[BaseMessage]) -> Optional[str]:
        """Get the latest human message from message history."""
        if not messages:
            return None
        for msg in reversed(messages):
            if hasattr(msg, 'content') and hasattr(msg, '__class__') and 'HumanMessage' in str(msg.__class__):
                return msg.content
        return None
    
    def main_agent_entry(self, state: ExplainableAgentState) -> Dict[str, Any]:
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
    
    def process_query(self, state: ExplainableAgentState) -> Dict[str, Any]:
        dynamic_plan = state.get("dynamic_plan")
        current_idx = state.get("current_step_index", 0)
        messages = state.get("messages", [])
        steps = state.get("steps", [])
        step_counter = state.get("step_counter", 0)
        
        if not dynamic_plan or current_idx >= len(dynamic_plan.steps):
            logger.info(f"All steps completed. Current index: {current_idx}, Total steps: {len(dynamic_plan.steps) if dynamic_plan else 0}")
            return {"messages": messages}
        
        # Get current step
        current_step = dynamic_plan.steps[current_idx]
        step_instruction = current_step.goal
        
        logger.info(f"Executing step {current_idx + 1}/{len(dynamic_plan.steps)}: {step_instruction}")
        
        system_message = self._build_system_message()
        
        # Create instruction message
        instruction_message = HumanMessage(
            content=f"Execute the following step: {step_instruction}"
        )
        
        # Bind tools and invoke
        llm_with_tools = self.llm.bind_tools(self.tools)
        
        # Filter out system messages from conversation
        conversation_messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]
        
        # Invoke with system message + conversation + instruction
        all_messages = [SystemMessage(content=system_message)] + conversation_messages + [instruction_message]
        response = llm_with_tools.invoke(all_messages)
        
        logger.info(f"Agent response has {len(response.tool_calls) if hasattr(response, 'tool_calls') and response.tool_calls else 0} tool calls")
        
        # NEW: Generate decision/reasoning for tool calls BEFORE tools execute
        if hasattr(response, 'tool_calls') and response.tool_calls:
            decision_reasoning = dict()
            if state.get("use_explainer", True):
                decision_reasoning = self._generate_tool_decision_reasoning(
                    tool_calls=response.tool_calls,
                    current_step=current_step,
                    state=state
                )
            
            # Create tool_calls array
            step_counter += 1
            tool_calls_list = []
            
            for tool_call in response.tool_calls:
                tool_calls_list.append({
                    "tool_call_id": tool_call['id'],
                    "tool_name": tool_call.get('name', 'unknown'),
                    "input": json.dumps(tool_call.get('args', {})),
                })
            
            # Create single step entry with tool_calls array
            # Build default decision text from tool names
            tool_names = [tc.get('name', 'unknown') for tc in response.tool_calls]
            default_decision = f"Using {', '.join(tool_names)}" if tool_names else "Executing step"
            default_reasoning = current_step.goal if current_step else "Executing planned step"
            
            step_entry = {
                "id": step_counter,
                "plan_step_index": current_idx,
                "decision": decision_reasoning.get('decision', default_decision),
                "reasoning": decision_reasoning.get('reasoning', default_reasoning),
                "timestamp": datetime.now().isoformat(),
                "tool_calls": tool_calls_list
            }
            steps.append(step_entry)
            logger.info(f"Created step {step_counter} with {len(tool_calls_list)} tool calls")

        
        # Increment step index
        new_step_index = current_idx + 1
        
        return {
            "messages": messages + [instruction_message, response],
            "current_step_index": new_step_index,
            "steps": steps,
            "step_counter": step_counter
        }
    
    def _generate_tool_decision_reasoning(
        self,
        tool_calls: List[Dict[str, Any]],
        current_step: Any,
        state: Dict[str, Any]
    ) -> Dict[str, str]:
        context = self._analyze_execution_context(state)
        
        tool_names = [tc.get('name', 'unknown') for tc in tool_calls]
        tool_summary = ", ".join(tool_names)
        
        tool_details = []
        for tool_name in tool_names:
            tool_obj = next((t for t in self.tools if t.name == tool_name), None)
            if tool_obj:
                tool_details.append(f"- {tool_name}: {tool_obj.description}")
            else:
                tool_details.append(f"- {tool_name}: (description not available)")
        
        tool_details_str = "\n".join(tool_details)
        
        # Build context info
        context_info = f"""- Available Data: {', '.join(context['available_data'])}
- Data Needed: {current_step.goal}
- Previous Output: {context.get('previous_output', 'None')}
- User Query: {state.get('query', 'Unknown')}"""
        
        # Generate reasoning via LLM
        prompt = f"""Explain the tool selection decision for this step.

**Current Step Goal**: {current_step.goal if current_step else 'Execute task'}

**Tool Calls Being Made** ({len(tool_calls)} call(s)):
{tool_summary}

**Tool Call Details**:
{chr(10).join([f"- Call {i+1}: {tc.get('name', 'unknown')} with args: {json.dumps(tc.get('args', {}))}" for i, tc in enumerate(tool_calls)])}

**Tool Descriptions**:
{tool_details_str}

**Available Context**:
{context_info}

**Alternative Tools from Plan**:
{self._format_tool_alternatives(current_step, tool_names)}

**Task**: Provide:
1. **Decision**: What tool(s) are being used (1 sentence, mention if multiple calls)
2. **Reasoning**: Why this tool and these specific inputs are chosen NOW given the current context (2-3 sentences)

Focus on execution-time factors:
- What data is currently available?
- Why is this tool appropriate for the current situation?
- How do the inputs address the step goal?
- If multiple calls: Why are multiple calls needed?
"""
        
        try:
            response = self.llm.invoke([SystemMessage(content=prompt)])
            content = response.content
            
            decision_match = re.search(r'\*\*Decision\*\*:?\s*(.+?)(?=\n\n|\n\d+\.|\*\*Reasoning\*\*|$)', content, re.DOTALL | re.IGNORECASE)
            decision = decision_match.group(1).strip() if decision_match else f"Using {tool_summary}"
            
            reasoning_match = re.search(r'\*\*Reasoning\*\*:?\s*(.+?)(?=\n\n|\n\d+\.|$)', content, re.DOTALL | re.IGNORECASE)
            reasoning = reasoning_match.group(1).strip() if reasoning_match else content
            
            logger.info(f"Parsed decision: {decision[:50]}...")
            logger.info(f"Parsed reasoning: {reasoning[:50]}...")
            
            return {
                "decision": decision,
                "reasoning": reasoning
            }
        except Exception as e:
            logger.error(f"Error generating decision reasoning: {e}")
            return {
                "decision": f"Using {tool_summary}",
                "reasoning": "Selected based on step requirements"
            }
    
    def _analyze_execution_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        available_data = []
        steps = state.get('steps', [])
        
        # Check what data is available from previous steps
        for step in steps:
            output = step.get('output', '')
            if 'DataFrame' in str(output) or 'stored' in str(output) or 'rows' in str(output).lower():
                tool_name = step.get('tool_name', 'unknown')
                available_data.append(f"Data from {tool_name}")
        
        # Get previous step output
        previous_output = None
        if steps:
            previous_output = str(steps[-1].get('output', ''))[:200]
        
        return {
            "available_data": available_data if available_data else ["No data in memory"],
            "previous_output": previous_output
        }
    
    def _format_tool_alternatives(self, current_step: Any, selected_tools: List[str]) -> str:
        alternatives = []
        for option in current_step.tool_options:
            if option.tool_name not in selected_tools:
                alternatives.append(
                    f"  - {option.tool_name} (Priority {option.priority}): {option.use_case}"
                )
        
        if alternatives:
            return "\n".join(alternatives)
        else:
            return "  (No alternatives in plan)"
    
    def tools_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        messages = state.get("messages", [])
        last_message = messages[-1]
        steps = state.get("steps", [])
        step_counter = state.get("step_counter", 0)
        data_context = state.get("data_context")  # Preserve existing data_context
        
        # Execute tools
        tool_node = ToolNode(tools=self.tools)
        result = tool_node.invoke(state)
        
        logger.info(f"Tool execution completed with {len(result.get('messages', []))} tool messages")
        
        # Match outputs to tool_calls within the latest step AND extract data_context
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls and steps:
            latest_step = steps[-1]  # Get the step we just created in process_query
            
            for tool_call in last_message.tool_calls:
                tool_call_id = tool_call['id']
                
                # Find corresponding output
                tool_output = None
                for msg in result.get("messages", []):
                    if hasattr(msg, 'tool_call_id') and msg.tool_call_id == tool_call_id:
                        tool_output = msg.content
                        break
                
                # Find corresponding tool_call entry and update with output
                for tc in latest_step.get('tool_calls', []):
                    if tc.get('tool_call_id') == tool_call_id:
                        tc['output'] = tool_output or "No output captured"
                        logger.info(f"Matched output for {tc.get('tool_name')}: {tool_call_id[:8]}...")
                        
                        # Extract data_context from tool output if present
                        if tool_output:
                            try:
                                output_data = json.loads(tool_output)
                                if isinstance(output_data, dict) and 'data_context' in output_data:
                                    from app.schemas.chat import DataContext
                                    data_context = DataContext(**output_data['data_context'])
                                    logger.info(f"Extracted data_context from tool output: {data_context.df_id}")
                            except (json.JSONDecodeError, Exception) as e:
                                logger.debug(f"Could not extract data_context from tool output: {e}")
                        
                        break
        
        return {
            "messages": result.get("messages", []),
            "steps": steps,
            "step_counter": step_counter,
            "data_context": data_context 
        }
    
    def should_continue(self, state: ExplainableAgentState) -> Literal["tools", "finalizer", "human_feedback", "process_query"]:
        if state.get("human_comment"):
            logger.info("Routing to human_feedback for replan")
            return "human_feedback"
        
        messages = state.get("messages", [])
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                logger.info("Tool calls detected, routing to tools")
                return "tools"
        
        # Check if we've completed all steps (only after confirming no tool calls)
        dynamic_plan = state.get("dynamic_plan")
        current_idx = state.get("current_step_index", 0)
        
        # If we're at or past the end of the plan and no tool calls, we're done
        if dynamic_plan and current_idx >= len(dynamic_plan.steps):
            logger.info("All steps completed, routing to finalizer")
            return "finalizer"
        
        # Continue to next step
        logger.info("Continuing to next step")
        return "process_query"
    
    def finalizer_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        logger.info("Finalizing execution with comprehensive evaluation")
        return self.finalizer.execute(state)
    
    def human_feedback(self, state: ExplainableAgentState) -> Dict[str, Any]:
        from langgraph.types import interrupt
        logger.info("Entering human_feedback node - pausing for input") 
        feedback_data = interrupt("awaiting_feedback")
        logger.info(f"Received human feedback: {feedback_data}")
        updates = {} 
        if isinstance(feedback_data, dict):
            if "action" in feedback_data:
                action = feedback_data["action"]
                if action == "cancel":
                    updates["status"] = "cancelled"
                    return updates
                elif action == "feedback":
                    updates["status"] = "feedback"
                    updates["human_comment"] = feedback_data.get("comment")
                    return updates
        
        return updates
    
    def route_after_feedback(self, state: ExplainableAgentState) -> Literal["planner", "finalizer"]:
        """Route after human feedback."""
        status = state.get("status")
        
        if status == "cancelled":
            return "finalizer"
        elif status == "feedback":
            return "planner"
        else:
            return "finalizer"
    
    def planner_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """Execute planner node."""
        return self.planner.execute(state)
    
    def explainer_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """Execute explainer node to generate result explanations."""
        return self.explainer.execute(state)
    
    def _build_system_message(self) -> str:
        """Build system message for the execution agent."""
        return """You are a data exploration agent executing a specific step from a plan.

Your task is to execute the given step instruction using the available tools.

IMPORTANT RULES:
1. You can make MULTIPLE tool calls if needed to complete the step
2. Focus on completing the specific step instruction given
3. Use the appropriate tools based on the step goal
4. Be efficient - don't repeat successful tool calls
5. If a tool fails, try an alternative approach

TOOL USAGE:
- data_exploration_agent: For database queries and SQL
- smart_transform_for_viz: For interactive frontend charts (small data)
- large_plotting_tool: For matplotlib plots (large data or complex visualizations)
- python_repl: For data analysis and transformations
- dataframe_info: To check available data

Execute the step instruction and use as many tools as needed to complete it."""
    
    def create_graph(self):
        """Create the main agent graph."""
        graph = StateGraph(ExplainableAgentState)
        
        # Add nodes
        graph.add_node("assistant", self.assistant_agent)
        graph.add_node("main_agent_flow", self.main_agent_entry)
        graph.add_node("planner", self.planner_node)
        graph.add_node("process_query", self.process_query)
        graph.add_node("tools", self.tools_node)
        graph.add_node("explainer", self.explainer_node)  # NEW: Add explainer node
        graph.add_node("finalizer", self.finalizer_node)
        graph.add_node("human_feedback", self.human_feedback)
        
        # Set entry point to assistant
        graph.set_entry_point("assistant")
        
        # Route from assistant to main agent flow
        graph.add_edge("main_agent_flow", "planner")
        
        # Add edges
        graph.add_edge("planner", "process_query")
        
        # Conditional routing after process_query
        graph.add_conditional_edges(
            "process_query",
            self.should_continue,
            {
                "tools": "tools",
                "finalizer": "finalizer",
                "human_feedback": "human_feedback",
                "process_query": "process_query"
            }
        )
          
        graph.add_edge("tools", "explainer")
        
        # After explainer, go back to process_query for next step
        graph.add_edge("explainer", "process_query")
        #  # After tools, check what to do next (don't go directly to process_query)
        # graph.add_conditional_edges(
        #     "tools",
        #     self.should_continue,
        #     {
        #         "tools": "tools",  # In case more tool calls needed
        #         "cleanup": "cleanup",
        #         "human_feedback": "human_feedback",
        #         "process_query": "process_query"
        #     }
        # )
        # After human_feedback, route based on action
        graph.add_conditional_edges(
            "human_feedback",
            self.route_after_feedback,
            {
                "planner": "planner",
                "finalizer": "finalizer"
            }
        )
        
        # Finalizer goes to END
        graph.add_edge("finalizer", END)
        
        # Compile with checkpointer and store
        if self.checkpointer:
            return graph.compile(checkpointer=self.checkpointer, store=self.store)
        else:
            return graph.compile(checkpointer=MemorySaver(), store=self.store)



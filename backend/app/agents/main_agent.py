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
from typing import List, Dict, Any, Optional, Literal
import json
import os
from datetime import datetime
import logging

from app.agents.tools.custom_toolkit import CustomToolkit
from app.agents.state import ExplainableAgentState
from app.agents.nodes.planner_node import PlannerNode
from app.agents.nodes.explainer_node import ExplainerNode

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
        
        # Initialize nodes
        self.planner = PlannerNode(llm, self.tools)
        self.explainer = ExplainerNode(llm, available_tools=self.tools)
        
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
    
    def process_query(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Execute the current step from the plan.
        
        This node:
        1. Gets the current step from dynamic_plan
        2. Uses the step's goal as instruction
        3. Lets the agent make multiple tool calls if needed
        4. Captures all tool call arguments and outputs in step info
        5. Increments current_step_index
        """
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
        
        # Build system message for the agent
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
        
        # Increment step index
        new_step_index = current_idx + 1
        
        return {
            "messages": messages + [instruction_message, response],
            "current_step_index": new_step_index,
            "steps": steps,
            "step_counter": step_counter
        }
    
    def tools_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Execute tools and capture step information.
        
        Supports multiple tool calls in one message - captures all arguments
        and all outputs in the step info.
        """
        messages = state.get("messages", [])
        last_message = messages[-1]
        steps = state.get("steps", [])
        step_counter = state.get("step_counter", 0)
        
        # Execute tools
        tool_node = ToolNode(tools=self.tools)
        result = tool_node.invoke(state)
        
        logger.info(f"Tool execution completed with {len(result.get('messages', []))} tool messages")
        
        # Capture step information for ALL tool calls
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            # Group all tool calls for this step
            all_tool_names = []
            all_tool_inputs = []
            all_tool_outputs = []
            
            for tool_call in last_message.tool_calls:
                tool_name = tool_call.get('name', 'unknown')
                tool_args = tool_call.get('args', {})
                
                all_tool_names.append(tool_name)
                all_tool_inputs.append(tool_args)
                
                # Find corresponding output
                tool_output = None
                for msg in result.get("messages", []):
                    if hasattr(msg, 'tool_call_id') and msg.tool_call_id == tool_call['id']:
                        tool_output = msg.content
                        break
                
                all_tool_outputs.append(tool_output or "No output captured")
            
            # Create single step info with all tool calls
            step_counter += 1
            step_info = {
                "id": step_counter,
                "type": "multi_tool" if len(all_tool_names) > 1 else all_tool_names[0],
                "tool_names": all_tool_names,  # List of all tools called
                "tool_name": all_tool_names[0] if all_tool_names else "unknown",  # Primary tool for compatibility
                "inputs": all_tool_inputs,  # List of all inputs
                "input": json.dumps(all_tool_inputs[0]) if all_tool_inputs else "{}",  # Primary input for compatibility
                "outputs": all_tool_outputs,  # List of all outputs
                "output": all_tool_outputs[0] if all_tool_outputs else "No output",  # Primary output for compatibility
                "context": state.get("query", ""),
                "timestamp": datetime.now().isoformat(),
                "tool_call_count": len(all_tool_names)
            }
            
            steps.append(step_info)
            logger.info(f"Captured step {step_counter} with {len(all_tool_names)} tool calls: {all_tool_names}")
        
        return {
            "messages": result.get("messages", []),
            "steps": steps,
            "step_counter": step_counter
        }
    
    def should_continue(self, state: ExplainableAgentState) -> Literal["tools", "cleanup", "human_feedback", "process_query"]:
        """
        Route after process_query.
        
        Routes to:
        - human_feedback: if feedback/comment exists
        - tools: if last message has tool calls (PRIORITY - check this first!)
        - cleanup: if all steps completed OR no more work to do
        - process_query: otherwise (continue to next step)
        """
        # Check for feedback/replan request
        if state.get("human_comment"):
            logger.info("Routing to human_feedback for replan")
            return "human_feedback"
        
        # IMPORTANT: Check for tool calls FIRST before checking step completion
        # This prevents skipping tool execution when we're on the last step
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
            logger.info("All steps completed, routing to cleanup")
            return "cleanup"
        
        # Continue to next step
        logger.info("Continuing to next step")
        return "process_query"
    
    def cleanup_state(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Cleanup planning fields while preserving execution history.
        
        Clears:
        - plan
        - dynamic_plan
        - current_step_index
        
        Preserves (for checkpointing):
        - messages
        - steps
        - data_context
        - visualizations
        """
        logger.info("Cleaning up planning state while preserving execution history")
        
        return {
            "plan": None,
            "dynamic_plan": None,
            "current_step_index": 0
            # Preserve: messages, steps, data_context, visualizations, etc.
        }
    
    def human_feedback(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """
        Handle human feedback for replanning.
        
        Uses existing human_feedback mechanism from data_exploration_agent.
        """
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
    
    def route_after_feedback(self, state: ExplainableAgentState) -> Literal["planner", "cleanup"]:
        """Route after human feedback."""
        status = state.get("status")
        
        if status == "cancelled":
            return "cleanup"
        elif status == "feedback":
            return "planner"
        else:
            return "cleanup"
    
    def planner_node(self, state: ExplainableAgentState) -> Dict[str, Any]:
        """Execute planner node."""
        return self.planner.execute(state)
    
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
        graph.add_node("planner", self.planner_node)
        graph.add_node("process_query", self.process_query)
        graph.add_node("tools", self.tools_node)
        graph.add_node("cleanup", self.cleanup_state)
        graph.add_node("human_feedback", self.human_feedback)
        
        # Set entry point
        graph.set_entry_point("planner")
        
        # Add edges
        graph.add_edge("planner", "process_query")
        
        # Conditional routing after process_query
        graph.add_conditional_edges(
            "process_query",
            self.should_continue,
            {
                "tools": "tools",
                "cleanup": "cleanup",
                "human_feedback": "human_feedback",
                "process_query": "process_query"
            }
        )
        
        # After tools, go back to process_query
        graph.add_edge("tools", "process_query")
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
                "cleanup": "cleanup"
            }
        )
        
        # Cleanup goes to END
        graph.add_edge("cleanup", END)
        
        # Compile with checkpointer
        if self.checkpointer:
            return graph.compile(checkpointer=self.checkpointer)
        else:
            return graph.compile(checkpointer=MemorySaver())


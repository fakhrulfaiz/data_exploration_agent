"""
Planner Node for query planning and feedback handling.
Generates execution plans and handles user feedback for plan revisions.
"""

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Dict, Any
from app.agents.schemas.tool_selection import DynamicPlan, PlanStep, ToolOption
import json
import logging

logger = logging.getLogger(__name__)


class FeedbackResponse(BaseModel):
    response_type: Literal["answer", "replan", "cancel"] = Field(
        description="Type of response: answer for direct answers, replan for creating new plans, cancel for cancellation"
    )
    content: str = Field(
        description="Content that can hold either the direct answer to user's question, a revised plan, or a general response"
    )
    new_query: Optional[str] = Field(
        default=None, 
        description="New query if the user requested a different question"
    )


class PlannerNode:
    
    def __init__(self, llm, tools):
        self.llm = llm
        self.tools = tools
    
    @staticmethod
    def _get_tool_selection_guidelines() -> str:
        """Shared tool selection guidelines for planning and replanning"""
        return """**TOOL SELECTION GUIDELINES**:

1. **Data Retrieval & SQL**:
   - ALWAYS use `data_exploration_agent` for database queries
   - This tool handles: natural language → SQL generation → execution → DataFrame storage
   - Returns data stored in Redis for further processing
   - Example: "Get user data" → data_exploration_agent automatically generates and executes SQL

2. **Visualizations** (when charts/graphs are requested):
   
   **Use smart_transform_for_viz when**:
   - Small datasets (≤100 rows)
   - Interactive frontend charts (bar, line, pie)
   - Requires DataFrame from data_exploration_agent
   
   **Use large_plotting_tool when**:
   - Large datasets (>100 rows)
   - User requests "matplotlib", "static image", or "high-quality" plots
   - Complex statistical plots (histograms, scatter plots, box plots)
   - Requires DataFrame from data_exploration_agent

3. **Data Analysis**:
   - Use python_repl for complex calculations, statistics, transformations
   - Use dataframe_info to check what data is available
   - python_repl requires DataFrame from data_exploration_agent

4. **Standard Workflows**:
   - **Simple Query**: data_exploration_agent → (results shown to user)
   - **With Visualization**: data_exploration_agent → smart_transform_for_viz
   - **Complex Analysis**: data_exploration_agent → python_repl → large_plotting_tool

5. **Error Prevention**:
   - data_exploration_agent automatically handles SQL generation and execution
   - Always call data_exploration_agent BEFORE visualization or analysis tools
   - Be specific about what data you need in the question parameter"""
    
    def execute(self, state):
        messages = state["messages"]
        user_query = state.get("query", "")
        status = state.get("status", "approved")

        if status == "cancelled":
            return {
                "messages": messages,
                "status": "cancelled"
            }
        
        return self._handle_dynamic_planning(state, messages, user_query)
        
        if status == "feedback" and state.get("human_comment"):
            return self._handle_feedback(state, messages, user_query)
        else:
            return self._handle_dynamic_planning(state, messages, user_query)
    
    def _handle_feedback(self, state, messages, user_query):
        human_feedback = state.get('human_comment', '')
        
        updated_messages = messages + [HumanMessage(content=human_feedback)]
         
        try:
            tool_descriptions = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])
            
            core_prompt = self._get_core_planner_prompt(user_query)
            
            replan_prompt = f"""Analyze user feedback and respond appropriately. You must provide a JSON response with three fields: response_type, content, and new_query.

RESPONSE TYPES:
1. "answer" - User asks questions about the plan → Provide clear explanations
2. "replan" - If User wants changes, improvements, or points out inefficiencies → Create revised numbered plan using available tools. If user changes the original request, set new_query field.
3. "cancel" - User wants to stop → Confirm cancellation

REQUIRED FIELDS:
- response_type: One of "answer", "replan", or "cancel"
- content: Your response text (if replan, must follow the planning guidelines below)
- new_query: Set to null unless user wants a completely different query (only for "replan" type when user changes the original request)

CONTEXT:
Query: {user_query}
Plan: {state.get('plan', 'No previous plan')}
Feedback: {human_feedback}
Tools: {tool_descriptions}

FEEDBACK RESPONSE EXAMPLES:
- "What does step 2 do?" → response_type: "answer", content: "explain the step", new_query: null
- "This seems redundant" → response_type: "answer", content: "Which step seems redundant for you?", new_query: null
- "Can we skip unnecessary steps?" → response_type: "replan", content: "streamline the approach", new_query: null
- "Change to show all artists" → response_type: "replan", content: "create new plan", new_query: "show all artists"
- "Cancel this" → response_type: "cancel", content: "confirm cancellation", new_query: null
- "Show 3 rows from database" → response_type: "answer", content: "ask user for which table they want to see the rows from", new_query: null

Be intuitive: If user suggests optimizations or questions efficiency, the system should always try to answer with your opinion first and then if user wants to change the plan,
consider replan. For vague feedback, ask for clarification. If user ask question, do you best to answer and DO NOT replan directly.

---

PLANNING GUIDELINES (for "replan" type):
When response_type is "replan", follow these comprehensive planning guidelines:

{core_prompt}"""
            
            conversation_messages = [msg for msg in updated_messages 
                                   if not isinstance(msg, SystemMessage)]
            
            all_messages = [
                SystemMessage(content=replan_prompt)
            ] + conversation_messages
            
            llm_with_structure = self.llm.with_structured_output(FeedbackResponse)
            response = llm_with_structure.invoke(all_messages)
            logger.info(f"LLM Response: {response}")
            logger.info(f"Response Type: {response.response_type}")
            logger.info(f"New Query: {response.new_query}")
          
            if response.response_type == "cancel":
                return {
                    "messages": updated_messages,
                    "query": user_query,
                    "plan": state.get("plan", ""),
                    "steps": state.get("steps", []),
                    "step_counter": state.get("step_counter", 0),
                    "assistant_response": response.content,
                    "status": "cancelled",
                    "response_type": "cancel"
                }
            elif response.response_type == "answer":
                answer_message = AIMessage(content=response.content)
                return {
                    "messages": updated_messages + [answer_message],
                    "query": user_query,
                    "plan": state.get("plan", ""),
                    "steps": state.get("steps", []),
                    "step_counter": state.get("step_counter", 0),
                    "assistant_response": response.content,
                    "status": "feedback",
                    "response_type": "answer"
                }
            elif response.response_type == "replan":
                plan = response.content
                new_query = response.new_query if response.new_query else user_query
                replan_message = AIMessage(content=response.content)
                return {
                    "messages": updated_messages + [replan_message],
                    "query": new_query,
                    "plan": plan,
                    "steps": [],  # Reset steps for new plan
                    "step_counter": 0,  # Reset counter for new plan
                    "assistant_response": response.content,
                    "status": "feedback",  # Require approval for new plan
                    "response_type": "replan"  # Mark as new plan
                }
            else:
                plan = f"Revised plan based on feedback: {human_feedback}"
                fallback_message = AIMessage(content=plan)
                return {
                    "messages": updated_messages + [fallback_message],
                    "query": user_query,
                    "plan": plan,
                    "steps": [],  # Reset steps for new plan
                    "step_counter": 0,  # Reset counter
                    "assistant_response": plan,
                    "status": "feedback",
                    "response_type": "replan"  # Mark as replan
                }
                
        except Exception as e:
            logger.error(f"Error in feedback processing: {e}")
            plan = f"Error processing feedback: {human_feedback}. Please try again."
            error_message = AIMessage(content=plan)
            
            return {
                "messages": updated_messages + [error_message],
                "query": user_query,
                "plan": state.get("plan", ""),  # Preserve original plan on error
                "steps": state.get("steps", []),  # Preserve steps on error
                "step_counter": state.get("step_counter", 0),
                "assistant_response": plan,
                "status": "feedback",  # Stay in feedback mode for retry
                "response_type": "answer"  # Treat errors as answers/clarifications
            }
    
    def _handle_dynamic_planning(self, state, messages, user_query):

        tool_descriptions = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])
        tool_guidelines = self._get_tool_selection_guidelines()
        
        # Check if this is a continuation from joiner (task incomplete)
        is_continuation = False
        if messages and isinstance(messages[-1], HumanMessage):
            last_msg_content = messages[-1].content.lower()
            if "task is not complete" in last_msg_content or "missing" in last_msg_content:
                is_continuation = True
        
        planning_prompt = f"""You are a data exploration query planner. Create a CONCISE, FOCUSED execution plan.

**Query**: {user_query}

**CRITICAL INSTRUCTIONS**:
1. **Be MINIMAL** - Only create steps that are ABSOLUTELY NECESSARY to answer the query
2. **One tool per step when possible** - Only list multiple tool options if there's genuine uncertainty about data size or format
3. **Focus on the goal** - Don't add extra steps for "potential" analysis unless explicitly requested
4. **Simple queries = Simple plans** - If the query is straightforward, keep it to 1-2 steps maximum
5. **Write CLEAR step goals** - Each goal will be used as a prompt for the execution agent, so be specific and actionable
6. **IMPORTANT**: If the task CANNOT be solved with available tools, return an EMPTY plan (no steps) - the system will handle cancellation

**Step Goal Writing Guidelines**:
- GOOD: "Generate SQL query to retrieve all table names from the database"
- GOOD: "Execute the SQL query and return the list of tables"
- GOOD: "Create an interactive bar chart showing album sales by artist"
- BAD: "Retrieve data" (too vague)
- BAD: "Prepare data for visualization" (unclear what to do)
- BAD: "Analyze results" (not actionable)

{tool_guidelines}

**When to provide MULTIPLE tool options**:
- Query execution when result size is unknown (sql_db_query vs sql_db_to_df)
- Visualization when data size affects tool choice (smart_transform_for_viz vs large_plotting_tool)
- Do NOT for simple queries with obvious single tool
- Do NOT for "potential" future steps that aren't requested

**When to provide SINGLE tool option**:
- Query asks for simple information (e.g., "what tables exist", "show schema")
- Visualization type is clear and data size is known
- Analysis step is straightforward

**Plan Template**:

Step 1:
- Goal: [Clear, specific description of what this step accomplishes]
- Tool Options:
  * [tool_name] (Priority 1): [When to use this tool for this specific step]
  * [alternative_tool] (Priority 2): [When to use this alternative] (only if genuinely needed)

Step 2:
- Goal: [Clear, specific description of what this step accomplishes]
- Tool Options:
  * [tool_name] (Priority 1): [When to use this tool for this specific step]

**Available Tools**:
{tool_descriptions}

**Your task**: Generate ONLY the steps needed to answer the query. Each step goal should be clear, specific, and actionable - it will be used to instruct the execution agent. Don't over-plan. Be direct and efficient.
"""
        
        try:
            # Use structured output for reliable parsing
            structured_llm = self.llm.with_structured_output(DynamicPlan)
            
            conversation_messages = [msg for msg in messages 
                                   if not isinstance(msg, SystemMessage)]
            
            all_messages = [
                SystemMessage(content=planning_prompt)
            ] + conversation_messages
            
            response = structured_llm.invoke(all_messages)
            
            # Convert structured plan to readable format for display
            plan_text = self._format_dynamic_plan(response)
            
            # Determine response_type based on context
            if len(response.steps) == 0:
                # Empty plan = task cannot be solved
                response_type = "cancel"
            elif is_continuation:
                # Continuation from joiner = no approval needed
                response_type = "continue"
            else:
                # New plan = needs approval
                response_type = "plan"

            # Determine start index for execution
            start_index = 0
            if is_continuation:
                # If continuing, try to start after the previously executed steps
                old_plan = state.get("dynamic_plan")
                if old_plan and hasattr(old_plan, 'steps'):
                    # If new plan extends old plan (has more steps), start at the new steps
                    if len(response.steps) > len(old_plan.steps):
                        start_index = len(old_plan.steps)
                        logger.info(f"Continuation plan detected. Advancing start index to {start_index} (Skipping first {len(old_plan.steps)} steps)")
                    else:
                        # Fallback: if plan length significantly changed or same, start from 0 
                        # and rely on AgentExecutor to skip completed steps
                        logger.info("Continuation plan has same or fewer steps - starting from index 0")

            return {
                "messages": messages + [AIMessage(content=plan_text)],
                "query": user_query,
                "plan": plan_text,
                "dynamic_plan": response,  # Store structured plan
                "current_step_index": start_index,  # Start at new steps if applicable
                "steps": [],
                "step_counter": 0,
                "response_type": response_type
            }
            
        except Exception as e:
            logger.error(f"Error in dynamic planning: {e}", exc_info=True)
            # Fallback to simple plan // later
            # return self._handle_initial_planning(state, messages, user_query)
    
    def _format_dynamic_plan(self, plan: DynamicPlan) -> str:
        """Format structured plan for display."""
        lines = [f"**Strategy**: {plan.overall_strategy}\n"]
        
        for step in plan.steps:
            lines.append(f"\n**Step {step.step_number}**: {step.goal}")
            lines.append("Tool Options:")
            
            for option in sorted(step.tool_options, key=lambda x: x.priority):
                lines.append(f"  {option.priority}. {option.tool_name}: {option.use_case}")
            
            if step.context_requirements:
                lines.append(f"  Requires: {step.context_requirements}")
        
        return "\n".join(lines)


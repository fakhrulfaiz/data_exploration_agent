"""
Planner Node for query planning and feedback handling.
Generates execution plans and handles user feedback for plan revisions.
"""

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)


class FeedbackResponse(BaseModel):
    """Model for handling user feedback responses"""
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
    """Node responsible for planning query execution and handling feedback"""
    
    def __init__(self, llm, tools):
        self.llm = llm
        self.tools = tools
    
    def execute(self, state):
        """Execute planner node logic
        
        Args:
            state: Current agent state
            
        Returns:
            Updated state with plan or feedback response
        """
        messages = state["messages"]
        user_query = state.get("query", "")
        status = state.get("status", "approved")

        if status == "cancelled":
            return {
                "messages": messages,
                "status": "cancelled"
            }
        
        if status == "feedback" and state.get("human_comment"):
            return self._handle_feedback(state, messages, user_query)
        else:
            return self._handle_initial_planning(state, messages, user_query)
    
    def _handle_feedback(self, state, messages, user_query):
        """Handle user feedback on existing plan
        
        Args:
            state: Current agent state
            messages: Message history
            user_query: Original user query
            
        Returns:
            Updated state with feedback response
        """
        human_feedback = state.get('human_comment', '')
        
        # Add human feedback message once at the start for consistency
        updated_messages = messages + [HumanMessage(content=human_feedback)]
         
        try:
            # Get tool descriptions for the prompt without binding tools
            tool_descriptions = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])
            
            replan_prompt = f"""Analyze user feedback and respond appropriately. You must provide a JSON response with three fields: response_type, content, and new_query.

RESPONSE TYPES:
1. "answer" - User asks questions about the plan → Provide clear explanations
2. "replan" - If User wants changes, improvements, or points out inefficiencies → Create revised numbered plan using available tools. If user changes the original request, set new_query field.
3. "cancel" - User wants to stop → Confirm cancellation

REQUIRED FIELDS:
- response_type: One of "answer", "replan", or "cancel"
- content: Your response text (if replan, must follow strict format below)
- new_query: Set to null unless user wants a completely different query (only for "replan" type when user changes the original request)

PLAN FORMAT (for "replan" type only):
When creating a revised plan, use this EXACT format:
- Each step: "N. tool_name: description"
- N is the step number (1, 2, 3, etc.)
- tool_name is the exact tool name (no backticks, no "the", no "tool" word)
- After colon, brief description

EXAMPLE REPLAN:
1. sql_db_list_tables: Get all available tables
2. sql_db_schema: Examine schema of relevant tables
3. sql_db_to_df: Execute query to retrieve data

CONTEXT:
Query: {user_query}
Plan: {state.get('plan', 'No previous plan')}
Feedback: {human_feedback}
Tools: {tool_descriptions}

EXAMPLES:
- "What does step 2 do?" → response_type: "answer", content: "explain the step", new_query: null
- "Add error handling" → response_type: "replan", content: "create new plan with error handling", new_query: null
- "This seems redundant" → response_type: "answer", content: "Which step seems redundant for you?", new_query: null
- "Can we skip unnecessary steps?" → response_type: "replan", content: "streamline the approach", new_query: null
- "Change to show all artists" → response_type: "replan", content: "create new plan", new_query: "show all artists"
- "Cancel this" → response_type: "cancel", content: "confirm cancellation", new_query: null
- "Show 3 rows from database" → response_type: "answer", content: "ask user for which table they want to see the rows from", new_query: null

Be intuitive: If user suggests optimizations or questions efficiency, the system should always try to answer with your opinion first and then if user wants to change the plan,
consider replan. For vague feedback, ask for clarification. If user ask question, do you best to answer and DO NOT replan directly."""
            
            # Filter out previous system messages to avoid conflicts
            conversation_messages = [msg for msg in updated_messages 
                                   if not isinstance(msg, SystemMessage)]
            
            # Prepare messages with system message FIRST, then conversation history (including feedback)
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
                    "response_type": "answer"  # Mark as clarification/answer
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
                # Fallback case - treat as replan
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
    
    def _handle_initial_planning(self, state, messages, user_query):
        """Handle initial plan generation
        
        Args:
            state: Current agent state
            messages: Message history
            user_query: User query to plan for
            
        Returns:
            Updated state with initial plan
        """
        
        planning_prompt = f"""You are a database query planner. Analyze the request and create a step-by-step plan.
                            Query: {user_query}

                            Create a concise plan that outlines the specific steps needed to answer this query.
                            
                            CRITICAL FORMAT REQUIREMENTS:
                            - Each step MUST follow this exact format: "N. tool_name: description"
                            - N is the step number (1, 2, 3, etc.)
                            - tool_name is the exact tool name (no backticks, no "the", no "tool" word)
                            - After the colon, describe ONLY what THIS SPECIFIC TOOL does, not the entire workflow
                            - Be clear about the INPUT and OUTPUT of each tool
                            - Avoid vague phrases like "find", "get", "compute" - be specific about the tool's action
                            
                            WRITING CLEAR DESCRIPTIONS:
                             BAD: "text2SQL: Find the total track time of top 5 playlists" (too vague, sounds like it does everything)
                             GOOD: "text2SQL: Convert the question into a SQL query that retrieves playlist names and their total track times, ordered by duration, limited to 5 rows"
                            
                             BAD: "python_repl: Compute the total" (unclear what to compute)
                             GOOD: "python_repl: Sum the track times from the DataFrame to get the final total"
                            
                            Each tool description should answer:
                            - What does THIS tool receive as input?
                            - What action does THIS tool perform?
                            - What does THIS tool output?
                            
                            
                            TOOL SELECTION GUIDELINES:
                            
                            1. **SQL Query Generation**:
                               - ALWAYS use text2SQL first to generate SQL queries from natural language
                               - text2SQL has access to database schema and will generate correct queries
                               - Provide context about what data you need
                            
                            2. **SQL Query Execution** - Choose based on output size and next steps:
                               
                               **Use sql_db_query when**:
                               - Query returns small results (≤20 rows)
                               - Results will be shown directly to user (no further processing needed)
                               - Simple SELECT queries
                               - Example: "Show me 5 customer names" → text2SQL + sql_db_query
                               
                               **Use sql_db_to_df when**:
                               - Query returns large results (>20 rows)
                               - Results need further processing (calculations, transformations, visualizations)
                               - Data will be used by python_repl or visualization tools
                               - Example: "Show top 100 albums" → text2SQL + sql_db_to_df + visualization tool
                               
                               Key difference:
                               - sql_db_query: Returns results directly to agent (not stored)
                               - sql_db_to_df: Stores results as DataFrame in Redis for further use
                            
                            3. **DataFrame Management**:
                               - ALWAYS run sql_db_to_df BEFORE using python_repl, smart_transform_for_viz, or large_plotting_tool
                               - These tools require a DataFrame to be available in Redis
                               - The DataFrame is automatically loaded by these tools using data_context
                            
                            4. **Visualizations** (when charts/graphs are requested):
                               
                               **Use smart_transform_for_viz when**:
                               - Small datasets (≤100 rows)
                               - Interactive frontend charts (bar, line, pie)
                               - User wants to explore data interactively
                               - Requires DataFrame from sql_db_to_df
                               
                               **Use large_plotting_tool when**:
                               - Large datasets (>100 rows)
                               - User requests "matplotlib", "static image", or "high-quality" plots
                               - Complex statistical plots (histograms, scatter plots, box plots)
                               - Requires DataFrame from sql_db_to_df
                            
                            5. **Data Analysis**:
                               - You can use use simple sql query with count, sum, avg, min, max, group by, order by, limit clauses for simple calculations
                               - Use python_repl for calculations, statistics, transformations
                               - Use dataframe_info to check what data is available
                               - python_repl requires DataFrame from sql_db_to_df
                            
                            6. **Error Prevention**:
                               - Use LIMIT clauses in SQL queries to avoid large datasets
                               - Select only necessary columns
                               - Be specific about what each tool does to avoid confusion
                            
                            COMMON WORKFLOWS:
                            
                            Simple Query (small result, no further processing):
                            1. text2SQL: Convert question to SQL query
                            2. sql_db_query: Execute query and return results directly
                            
                            Simple Query (needs further processing):
                            1. text2SQL: Convert question to SQL query
                            2. sql_db_to_df: Execute query and store results
                            3. python_repl: Perform calculations or analysis
                            
                            Query with Visualization (small data):
                            1. text2SQL: Convert question to SQL query
                            2. sql_db_to_df: Execute query and store results as DataFrame
                            3. smart_transform_for_viz: Create interactive chart from DataFrame
                            
                            Query with Visualization (large data):
                            1. text2SQL: Convert question to SQL query
                            2. sql_db_to_df: Execute query and store results as DataFrame
                            3. large_plotting_tool: Create matplotlib plot from DataFrame
                            
                            EXAMPLE FORMAT:
                            1. [tool_name]: [What this tool receives as input]. Input: [specific input]. Action: [What this tool does]. Output: [What this tool produces].
                            
                            2. [next_tool]: [What this tool receives]. Input: [from previous step]. Action: [specific action]. Output: [result type and description].
                            
                            3. [final_tool]: [What this tool does with the data]. Input: [data from previous step]. Action: [final processing]. Output: [final deliverable].
                            
                            HANDLING UNCERTAINTY:
                            If you're not sure about the exact approach or need to explore the data first, you can indicate this in your plan.
                            After listing the numbered steps, add a note like:
                            - "We'll run these steps first to explore the data, then decide on the best visualization approach."
                            - "This initial exploration will help determine if additional analysis is needed."
                            - "After seeing the results, we may need to adjust our approach for optimal presentation."
                            
                            After listing all numbered steps, add a final paragraph (NOT numbered) explaining what the result will be.
                            For example: "The visualization will be displayed in the interface, allowing for interactive exploration of the data."
                            
                            DO NOT use phrases like "Use the", "Execute the", or wrap tool names in backticks.
                            Write naturally as an agent explaining its plan.
                            Each step should be on its own line."""

        try:

            tool_descriptions = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])

            # Filter out previous system messages to avoid conflicts
            conversation_messages = [msg for msg in messages 
                                   if not isinstance(msg, SystemMessage)]
            
            # Prepare messages with system message FIRST, then conversation history
            all_messages = [
                SystemMessage(content=f"Available tools for planning:\n{tool_descriptions}"),
                SystemMessage(content=planning_prompt)
            ] + conversation_messages  # Include conversation history without system messages
            
            response = self.llm.invoke(all_messages)
            plan = response.content
            
        except Exception as e:
            logger.error(f"Error in initial planning: {e}")
            plan = f"Simple plan: Analyze the query '{user_query}' using available database tools like sql_db_list_tables, sql_db_schema, and sql_db_to_df."
        
        return {
            "messages": messages + [AIMessage(content=plan)],
            "query": user_query,
            "plan": plan,
            "steps": state.get("steps", []),
            "step_counter": state.get("step_counter", 0)
        }

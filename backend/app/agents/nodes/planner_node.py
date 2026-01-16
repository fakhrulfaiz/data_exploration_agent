"""
Planner Node for query planning and feedback handling.
Generates execution plans and handles user feedback for plan revisions.
"""

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Dict, Any
from app.agents.schemas.tool_selection import DynamicPlan, PlanStep, ToolOption
from app.agents.prompts.planner_context_template import get_planner_context, get_intent_system_prompt
import json
import logging

logger = logging.getLogger(__name__)


class FeedbackResponse(BaseModel):
    response_type: Literal["answer", "replan", "cancel"] = Field(
        description="Type of response: answer for direct answers, replan for creating new plans, cancel for cancellation"
    )
    content: str = Field(
        description="Content that can hold the direct answer to user's question. If replan, this explains the strategy change."
    )
    new_query: Optional[str] = Field(
        default=None, 
        description="New query if the user requested a different question"
    )


class PlannerNode:
    
    def __init__(self, llm, tools):
        self.llm = llm
        self.tools = tools
        
        # Use OpenAI GPT-4o-mini specifically for planning (better structured output)
        # This ensures reliable plan generation even when using other LLMs for other tasks
        from langchain_openai import ChatOpenAI
        import os
        self.planning_llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.0
        )
        logger.info("PlannerNode initialized with dedicated OpenAI planning LLM")
    
    def _get_planning_style_directive(self, user_id: Optional[str] = None) -> str:
        """Get planning-focused communication style directive based on user preferences."""
        if not user_id:
            return ""
        
        try:
            from app.services.dependencies import get_redis_profile_service, get_profile_service
            redis_service = get_redis_profile_service()
            profile_service = get_profile_service()
            
            profile = profile_service.get_user_profile(user_id)
            style = profile.get('communication_style', 'balanced') if profile else 'balanced'
            
        except Exception as e:
            logger.warning(f"Failed to fetch communication style: {e}")
            style = 'balanced'
        
        directives = {
            'concise': """
**PLANNING STYLE: CONCISE**
- Create minimal steps (combine where possible)
- Use brief, action-oriented step goals
- Focus on essential tool options only
- Keep overall strategy to 1-2 sentences
Example: "Strategy: Query and visualize data. Step 1: Get top 5 paintings by year. Step 2: Create bar chart."
""",
            'detailed': """
**PLANNING STYLE: DETAILED**
- Break down into well-defined steps but still combine it 
- Provide comprehensive step goals with context
- List all relevant tool options with detailed use cases
- Explain the overall strategy thoroughly
- Include context requirements and dependencies
Example: "Strategy: First, we'll retrieve the top 5 paintings sorted by creation year from the database to identify the oldest artworks. Then, we'll create a comprehensive bar chart visualization to display these paintings chronologically, making it easy to see the temporal distribution. Step 1: Query the paintings table to retrieve the top 5 oldest paintings, ensuring we get the title, artist, and year_created columns for complete context..."
""",
            'balanced': """
**PLANNING STYLE: BALANCED**
- Create clear, focused steps without over-explaining
- Provide specific step goals with key details
- List primary tool options with brief rationale
- Keep strategy clear and purposeful (2-3 sentences)
Example: "Strategy: Retrieve the oldest paintings from the database and visualize them. Step 1: Query for top 5 paintings sorted by year_created. Tool: data_exploration_tool for SQL query execution. Step 2: Create bar chart showing paintings by year. Tool: large_plotting_tool for direct visualization."
"""
        }
        
        return directives.get(style, directives['balanced'])

    def _generate_intent_understanding(self, user_query: str, use_explainer: bool, state: Dict[str, Any] = None, planning_style_directive: str = ""):
        """Returns AIMessage with thought process or None"""
        if not use_explainer:
            logger.debug("Explainer mode disabled, skipping intent generation")
            return None
        
        context = get_planner_context()
        try:
            from app.services.rag_service import get_rag_service
            
            rag_service = get_rag_service()
            thought_patterns = rag_service.retrieve_thought_patterns(
                query=user_query,
                n_results=2 
            )
            
            if thought_patterns:
                examples_context = "\n\n**Similar Query Examples**:\n"
                for i, pattern in enumerate(thought_patterns, 1):
                    examples_context += f"\nExample {i} ({pattern['complexity']} complexity):\n"
                    examples_context += f"Query: \"{pattern['example_query']}\"\n"
                    examples_context += f"Thought: {pattern['example_thought']}\n"
                
                context += examples_context
                logger.info(f"Retrieved {len(thought_patterns)} thought pattern examples from RAG")
                logger.debug(f"Pattern types: {[p['pattern_type'] for p in thought_patterns]}")
        except Exception as e:
            logger.warning(f"Failed to retrieve thought patterns from RAG: {e}")
        
        system_message = get_intent_system_prompt(context=context)

        user_message = f"""Analyze this query: "{user_query}" """
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_message),
                HumanMessage(content=user_message)
            ])
            
            # POST-PROCESSING: Ensure response starts with "Thought:" prefix
            # Some LLMs (especially smaller ones) don't follow this instruction consistently
            content = response.content.strip()
            if not content.startswith("Thought:"):
                # Add the prefix if missing
                content = f"Thought: {content}"
                response.content = content
                logger.debug("Added missing 'Thought:' prefix to intent response")
            
            logger.info(f"Generated thought process: {response.content.strip()[:100]}...")
            
            # Return only the response message for streaming
            return response
            
        except Exception as e:
            logger.error(f"Error generating intent understanding: {e}", exc_info=True)
            return None
    
    def _build_intent_context(self, intent: str) -> str:
        if not intent:
            return ""
        
        return f"""
**Agent Thinking Process**:
{intent}

Create the plan based on this understanding.
"""
    
    def execute(self, state):
        messages = state["messages"]
        user_query = state.get("query", "")
        status = state.get("status", "approved")

        if status == "cancelled":
            return {
                "messages": messages,
                "status": "cancelled"
            }
        
        # Check for feedback/replan request BEFORE default planning
        if status == "feedback" and state.get("human_comment"):
            return self._handle_feedback(state, messages, user_query)
        else:
            return self._handle_dynamic_planning(state, messages, user_query)
            
    def _get_core_planner_prompt(self, user_query: str) -> str:
        """Get the core planning instructions and guidelines."""
        tool_descriptions = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])
        
        return f"""You are an efficient task planner. Your job is to plan tasks that handle dependencies correctly.
You are given a user query/task and a list of tools.

**Query**: {user_query}

**Available Tools**:
{tool_descriptions}

**INSTRUCTIONS**:
1. **Recognize Dependencies** - If a tool needs data/information from another tool, create separate steps
2. **Be Minimal BUT Complete** - Only create necessary steps, but don't skip steps that provide required inputs
3. **Think Through Data Flow** - Ask yourself: "Does this tool have the data it needs to execute?"
4. **Write CLEAR step goals** - Each goal will be used as a prompt for the execution agent, so be specific and actionable
5. **One Step Can Mean Multiple Tool Calls** - The execution agent can call the same tool multiple times with different arguments for a single step
6. **Prefer SQL over Python** - If a sub-agent can filter/sort/limit data in the database (e.g., "oldest", "top 5"), do it in the query step instead of retrieving all data and using 'smart_data_analysis'.
7. **Visual/Depiction Queries**: If query implies visual content (e.g. 'depicting', 'showing', 'swords', 'war'), you MUST create a step for `image_batch_qa_tool` to extract this data FIRST. DO NOT use `smart_data_analysis` to "count" or "find" visual attributes directly - it cannot see images.
8. **If use Image QA tool** - must query and return 'img_path' not image URL column
9. **User Preference** -  You must strictly follow "User Preferences" if provided.

**When to Create Multiple Steps**:
- Tool needs data that must be retrieved first (database → analysis)
- Tool needs output from another tool (query → transform → visualize)
- Sequential operations that can't be done in one call

**When to Use Single Step**:
- Complete sub-agents that handle entire workflows (e.g., data_exploration_tool can query + store)
- Tool has all information needed in the user query
- No dependencies on other tools
"""

    def _handle_feedback(self, state, messages, user_query):
        human_feedback = state.get('human_comment', '')
        
        updated_messages = messages + [HumanMessage(content=human_feedback)]
         
        try:
            tool_descriptions = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])
            
            core_prompt = self._get_core_planner_prompt(user_query)
            
            replan_prompt = f"""Analyze user feedback and respond appropriately. You must provide a JSON response with three fields: response_type, content, and new_query.

RESPONSE TYPES:
1. "answer" - User asks questions about the plan → Provide clear explanations
2. "replan" - If User wants changes, improvements, or points out inefficiencies → Trigger a replan. In 'content', explain WHAT needs to change (strategy), but DO NOT write the full numbered plan steps yourself.
3. "cancel" - User wants to stop → Confirm cancellation

REQUIRED FIELDS:
- response_type: One of "answer", "replan", or "cancel"
- content: 
    - If "answer": Your full explanation.
    - If "replan": A brief instruction/strategy modification for the planner (e.g. "Include image analysis steps" or "Filter by year first"). DO NOT generate schema/steps here.
    - If "cancel": Confirmation message.
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

PLANNING GUIDELINES (for "replan" decision):
- If the user's request requires using different tools or changing the order of steps -> "replan"
- If the user provides a hint or requirement -> "replan" (and summarize it in 'content')
- If the user asks for clarification -> "answer"

Context only (do not generate plan based on this):
{core_prompt}"""
            
            conversation_messages = [msg for msg in updated_messages 
                                   if not isinstance(msg, SystemMessage)]
            
            all_messages = [
                SystemMessage(content=replan_prompt)
            ] + conversation_messages
            
            llm_with_structure = self.planning_llm.with_structured_output(FeedbackResponse)
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
                # Delegate actual planning to the structured planner
                # We update the state with the feedback and let dynamic planning handle it
                # The 'content' from feedback response serves as the 'intent' or guidance
                
                logger.info(f"Delegating replan to dynamic planner. Guidance: {response.content}")
                
                # CRITICAL: Add the FeedbackResponse's guidance as an AIMessage
                # This provides the planner with the INTERPRETED instruction, not just raw user comment
                # Example: User says "mention tool name" → FeedbackResponse interprets as 
                # "Specify the use of 'data_exploration_tool' directly in the step description"
                guidance_message = AIMessage(content=f"Feedback guidance (Always follow this guidance): {response.content}")
                messages_with_guidance = updated_messages + [guidance_message]
                
                # If there's a new query (user changed their mind completely), update it
                actual_query = response.new_query if response.new_query else user_query
                
                # Call dynamic planning with the guidance included in messages
                # The planner will see: [original plan, user comment, AI guidance]
                result = self._handle_dynamic_planning(state, messages_with_guidance, actual_query)
                
                # CRITICAL: Clear human_comment so routing doesn't think there's pending feedback
                # The comment was already processed and incorporated into the new plan
                result["human_comment"] = None
                
                return result
            else:
                # Fallback
                plan = f"Revised plan based on feedback: {human_feedback}"
                fallback_message = AIMessage(content=plan)
                return {
                    "messages": updated_messages + [fallback_message],
                    "query": user_query,
                    "plan": plan,
                    "steps": [],  
                    "step_counter": 0,
                    "assistant_response": plan,
                    "status": "feedback",
                    "response_type": "replan"
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
        use_explainer = state.get("use_explainer", True)
        
        # Get planning style directive based on user preferences (if explainer enabled)
        planning_style_directive = ""
        if use_explainer:
            user_id = state.get("user_id")
            planning_style_directive = self._get_planning_style_directive(user_id)
        
        # Generate intent understanding (if explainer enabled)
        thought_response = None
        if use_explainer:
            thought_response = self._generate_intent_understanding(user_query, use_explainer, state, planning_style_directive)
        
        # Build intent context for prompt
        intent_context = self._build_intent_context(thought_response) if use_explainer else ""
        
        # Get error explanation if available (from error_explainer)
        error_explanation = state.get("error_explanation")
        error_context = ""
        
        logger.info(f"Planner checking for error_explanation: {error_explanation is not None}")
        if error_explanation:
            logger.info(f"Error explanation found: {error_explanation.get('what_happened', 'N/A')[:100]}")
        
        if error_explanation:
            error_context = f"""
**IMPORTANT - Previous Error Context:**
The previous plan failed with the following error:
- What happened: {error_explanation.get('what_happened', 'Unknown')}
- Why it happened: {error_explanation.get('why_it_happened', 'Unknown')}
- Suggestions: {', '.join(error_explanation.get('alternative_suggestions', []))}

**You MUST create a plan that addresses this error and avoids making the same mistake.**
"""
            logger.info(f"Error context added to planning prompt (length: {len(error_context)})")
        else:
            logger.info("No error_explanation in state - skipping error context")
        
        tool_descriptions = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])
        
        is_continuation = False
        if messages and isinstance(messages[-1], SystemMessage.__bases__[0]):
            last_msg_content = str(messages[-1].content).lower()
            if "task is not complete" in last_msg_content or "missing" in last_msg_content:
                is_continuation = True
        
        planning_prompt = f"""You are an efficient task planner. Your job is to plan tasks that handle dependencies correctly.
You are given a user query/task and a list of tools.

{planning_style_directive}

{intent_context}

If Error Context provided, focus on solving the error. Be concise.
{error_context}

**Query**: {user_query}

**INSTRUCTIONS**:
1. **Recognize Dependencies** - If a tool needs data/information from another tool, create separate steps
2. **Be Minimal BUT Complete** - Only create necessary steps, but don't skip steps that provide required inputs
3. **Think Through Data Flow** - Ask yourself: "Does this tool have the data it needs to execute?"
4. **Write CLEAR step goals** - Each goal will be used as a prompt for the execution agent, so be specific and actionable
5. **One Step Can Mean Multiple Tool Calls** - The execution agent can call the same tool multiple times with different arguments for a single step
6. **Prefer SQL over Python** - If a sub-agent can filter/sort/limit data in the database (e.g., "oldest", "top 5"), do it in the query step instead of retrieving all data and using 'smart_data_analysis'.
7. **Visual/Depiction Queries**: If query implies visual content (e.g. 'depicting', 'showing', 'swords', 'war'), you MUST create a step for `image_batch_qa_tool` to extract this data FIRST. DO NOT use `smart_data_analysis` to "count" or "find" visual attributes directly - it cannot see images.
8. **If use Image QA tool** - must query and return 'img_path' not image URL column
9. **User Preference** -  You must strictly follow "User Preferences" if provided.
**When to Create Multiple Steps**:
- Tool needs data that must be retrieved first (database → analysis)
- Tool needs output from another tool (query → transform → visualize)
- Sequential operations that can't be done in one call

**When to Use Single Step**:
- Complete sub-agents that handle entire workflows (e.g., data_exploration_tool can query + store)
- Tool has all information needed in the user query
- No dependencies on other tools

**IMPORTANT - Single Step with Multiple Tool Calls**:
- The execution agent can generate MULTIPLE tool calls for a SINGLE step if needed
- Don't artificially split steps when the same tool can handle multiple variations in parallel
- Example: "Create bar, line, and pie charts" → execution agent calls the viz tool 3 times with different args
**Plan Template**:

Step 1:
- Goal: [Clear, specific description of what this step accomplishes]
- Tool Options:
  * [tool_name] (Priority 1): [When to use this tool for this specific step]
  * [alternative_tool] (Priority 2): [When to use this alternative] (only if genuinely needed)

Step 2:
- Goal: [Clear, specific description - can mention multiple outputs if they use the same tool]
- Tool Options:
  * [tool_name] (Priority 1): [When to use this tool for this specific step]

Plan and list the tasks in a way that each task can be solved by one of these tools.
{tool_descriptions}


CRITICAL - Understanding Sub-Agents:
- Some tools are SUB-AGENTS that handle entire workflows internally
- data_exploration_tool: Handles question → SQL generation → execution → storage
- ONE call to a complete sub-agent is sufficient for its entire domain

Your task: Generate the steps needed to answer the query. Think through dependencies carefully - if a tool needs data, make sure a previous step provides it.
"""
        
        # Generate structured plan
        try:
            # Use dedicated OpenAI LLM for planning (better at structured output)
            structured_llm = self.planning_llm.with_structured_output(DynamicPlan)
            
            conversation_messages = [msg for msg in messages 
                                   if not isinstance(msg, SystemMessage)]
            
            all_messages = [
                SystemMessage(content=planning_prompt)
            ] + conversation_messages
            
            response = structured_llm.invoke(all_messages)
            
            # VALIDATION: Filter out incomplete/hallucinated steps
            # Smaller LLMs sometimes generate partial steps with missing required fields
            valid_steps = []
            for step in response.steps:
                # Check if step has all required fields properly filled
                if (hasattr(step, 'goal') and step.goal and 
                    hasattr(step, 'tool_options') and step.tool_options and
                    len(step.tool_options) > 0):
                    # Ensure tool_options have required fields
                    valid_tool_options = [
                        opt for opt in step.tool_options 
                        if hasattr(opt, 'tool_name') and opt.tool_name and
                           hasattr(opt, 'use_case') and opt.use_case
                    ]
                    if valid_tool_options:
                        step.tool_options = valid_tool_options
                        valid_steps.append(step)
                        logger.debug(f"✅ Valid step {step.step_number}: {step.goal[:50]}...")
                    else:
                        logger.warning(f"❌ Skipping step {step.step_number}: No valid tool options")
                else:
                    logger.warning(f"❌ Skipping incomplete step {getattr(step, 'step_number', '?')}: Missing required fields")
            
            # Update response with only valid steps
            response.steps = valid_steps
            
            if len(valid_steps) == 0:
                logger.error("No valid steps generated - all steps were incomplete/hallucinated")
            else:
                logger.info(f"Plan validation: {len(valid_steps)}/{len(response.steps)} steps are valid")
            
            # Format plan for display (WITHOUT intent - it's streamed separately)
            plan_text = self._format_dynamic_plan(response)
            
            # Determine response type
            existing_plan = state.get("dynamic_plan")
            has_existing_plan = existing_plan is not None and hasattr(existing_plan, 'steps') and len(existing_plan.steps) > 0
            
            if len(response.steps) == 0:
                response_type = "cancel"
            elif is_continuation:
                response_type = "continue"
            elif has_existing_plan:
                response_type = "replan"
            else:
                response_type = "plan"
            
            # Determine start index for continuation
            start_index = 0
            if is_continuation:
                old_plan = state.get("dynamic_plan")
                if old_plan and hasattr(old_plan, 'steps'):
                    if len(response.steps) > len(old_plan.steps):
                        start_index = len(old_plan.steps)
                        logger.info(f"Continuation plan detected. Advancing start index to {start_index}")
                    else:
                        logger.info("Continuation plan has same or fewer steps - starting from index 0")
            
            return {
                "messages": messages + [AIMessage(content=plan_text)],  # Thought already in messages
                "query": user_query,
                "plan": plan_text,
                "dynamic_plan": response,  # Includes intent if available
                "current_step_index": start_index,
                "steps": [],
                "step_counter": 0,
                "response_type": response_type
            }
            
        except Exception as e:
            logger.error(f"Error in dynamic planning: {e}", exc_info=True)
            raise
    
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


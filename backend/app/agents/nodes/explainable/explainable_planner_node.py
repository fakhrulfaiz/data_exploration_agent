"""
Explainable Planner Node - extends PlannerNode with intent understanding.

This node adds a layer of explainability by generating intent understanding
before creating the execution plan. It can be toggled on/off via enable_explainer flag.
"""

from langchain_core.messages import SystemMessage, HumanMessage
from typing import Optional, Dict, Any
import logging

from app.agents.nodes.planner_node import PlannerNode
from app.agents.schemas.tool_selection import IntentUnderstanding, DynamicPlan
from app.agents.prompts.planner_context_template import get_planner_context, get_intent_system_prompt

logger = logging.getLogger(__name__)


class ExplainablePlannerNode(PlannerNode):
    def _generate_intent_understanding(self, user_query: str, use_explainer: bool, state: Dict[str, Any] = None):
        """Returns AIMessage with thought process or None"""
        if not use_explainer:
            logger.debug("Explainer mode disabled, skipping intent generation")
            return None
        
        # Fetch user preferences if user_id is available
        user_preferences = ""
        if state and state.get("user_id"):
            try:
                from app.services.dependencies import get_redis_profile_service, get_profile_service
                from app.agents.prompts.user_preferences import get_user_preference_prompt
                
                redis_service = get_redis_profile_service()
                profile_service = get_profile_service()
                user_preferences = get_user_preference_prompt(
                    state["user_id"],
                    redis_service,
                    profile_service
                )
                logger.info(f"Fetched user preferences for user {state['user_id']}")
            except Exception as e:
                logger.warning(f"Failed to fetch user preferences: {e}")
        
        context = get_planner_context(user_preferences)
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
        
        system_message = get_intent_system_prompt(context=context, user_preferences=user_preferences)

        user_message = f"""Analyze this query: "{user_query}" """
        
        try:
            # Use raw LLM for natural thinking output
            response = self.llm.invoke([
                SystemMessage(content=system_message),
                HumanMessage(content=user_message)
            ])
            
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
        
    
    def _format_dynamic_plan(self, plan: DynamicPlan) -> str:
        lines = []
        lines.append(f"**Strategy**: {plan.overall_strategy}\n")
        
        for step in plan.steps:
            lines.append(f"\n**Step {step.step_number}**: {step.goal}")
            lines.append("Tool Options:")
            
            for option in sorted(step.tool_options, key=lambda x: x.priority):
                lines.append(f"  {option.priority}. {option.tool_name}: {option.use_case}")
            
            if step.context_requirements:
                lines.append(f"  Requires: {step.context_requirements}")
        
        return "\n".join(lines)
    
    def _handle_dynamic_planning(self, state, messages, user_query):
        use_explainer = state.get("use_explainer", True)
        thought_response = self._generate_intent_understanding(user_query, use_explainer, state)
        
        # No intent context needed anymore
        intent_context = self._build_intent_context(thought_response)
        
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
 
{intent_context}

{error_context}

**Query**: {user_query}

**INSTRUCTIONS**:
1. **Recognize Dependencies** - If a tool needs data/information from another tool, create separate steps
2. **Be Minimal BUT Complete** - Only create necessary steps, but don't skip steps that provide required inputs
3. **Think Through Data Flow** - Ask yourself: "Does this tool have the data it needs to execute?"
4. **Write CLEAR step goals** - Each goal will be used as a prompt for the execution agent, so be specific and actionable
5. **One Step Can Mean Multiple Tool Calls** - The execution agent can call the same tool multiple times with different arguments for a single step
6. **Prefer SQL over Python** - If a sub-agent can filter/sort/limit data in the database (e.g., "oldest", "top 5"), do it in the query step instead of retrieving all data and using python_repl.
7. **If use Image QA tool** - must query and return 'img_path' not image URL column
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


**CRITICAL - Understanding Complete Sub-Agents**:
- Some tools are SUB-AGENTS that handle entire workflows internally
- data_exploration_tool: Handles question → SQL generation → execution → storage
- ONE call to a complete sub-agent is sufficient for its entire domain

**Your task**: Generate the steps needed to answer the query. Think through dependencies carefully - if a tool needs data, make sure a previous step provides it.
"""
        
        # Step 6: Generate structured plan
        try:
            from langchain_core.messages import AIMessage
            
            structured_llm = self.llm.with_structured_output(DynamicPlan)
            
            conversation_messages = [msg for msg in messages 
                                   if not isinstance(msg, SystemMessage)]
            
            all_messages = [
                SystemMessage(content=planning_prompt)
            ] + conversation_messages
            
            response = structured_llm.invoke(all_messages)
            
            # Step 8: Format plan for display (WITHOUT intent - it's streamed separately)
            plan_text = self._format_dynamic_plan(response)
            
            # Step 9: Add plan message
            # (Thought was already added to messages earlier)
            
            # Step 10: Determine response type
            # Check if this is a replan (existing plan + new plan being created)
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
            
            # Step 10: Determine start index for continuation
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

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

logger = logging.getLogger(__name__)


class ExplainablePlannerNode(PlannerNode):
    def _generate_intent_understanding(self, user_query: str, use_explainer: bool) -> Optional[IntentUnderstanding]:
        if not use_explainer:
            logger.debug("Explainer mode disabled, skipping intent generation")
            return None
        
        system_message = """You are an intent understanding agent.
Your goal is to providing a "Thinking Process" narrative for the user's query.

Instructions:
1. Analyze the user's request.
2. Output a single, coherent paragraph written in first-person ("I need to...", "The goal is...").
3. Explain the constraints, what data is needed, and the logical approach.
4. DO NOT use bullet points or lists. Just a clear thought process.

Answer with Thought: [Your thought process here]
"""

        user_message = f"""Analyze this query: "{user_query}" """
        
        try:
            # Use raw LLM for natural thinking output
            response = self.llm.invoke([
                SystemMessage(content=system_message),
                HumanMessage(content=user_message)
            ])
            
            thought_process = response.content.strip()
            
            logger.info(f"Generated thought process: {thought_process}")
            
            return IntentUnderstanding(
                main_intent=thought_process,
                sub_intents=[]  # Empty list as requested (thought only)
            )
            
        except Exception as e:
            logger.error(f"Error generating intent understanding: {e}", exc_info=True)
            return None
    
    def _build_intent_context(self, intent: Optional[IntentUnderstanding]) -> str:
        if not intent:
            return ""
        
        return f"""
**Agent Thinking Process**:
{intent.main_intent}

Create the plan based on this understanding.
"""
        
       
    
    def _format_dynamic_plan(self, plan: DynamicPlan) -> str:
        lines = []
        
        if plan.intent:
            lines.append(f"**Intent**: {plan.intent.main_intent}\n")
            lines.append("")
        
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
        intent = self._generate_intent_understanding(user_query, use_explainer)
        
        intent_context = self._build_intent_context(intent)
        
        tool_descriptions = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])
        
        is_continuation = False
        if messages and isinstance(messages[-1], SystemMessage.__bases__[0]):
            last_msg_content = str(messages[-1].content).lower()
            if "task is not complete" in last_msg_content or "missing" in last_msg_content:
                is_continuation = True
        
        planning_prompt = f"""You are an efficient task planner. Your job is to plan tasks that handle dependencies correctly.
    You are given a user query/task and a list of tools.

{intent_context}

**Query**: {user_query}

**INSTRUCTIONS**:

1. **Recognize Dependencies** - If a tool needs data/information from another tool, create separate steps
2. **Be Minimal BUT Complete** - Only create necessary steps, but don't skip steps that provide required inputs
3. **Think Through Data Flow** - Ask yourself: "Does this tool have the data it needs to execute?"
4. **Write CLEAR step goals** - Each goal will be used as a prompt for the execution agent, so be specific and actionable

**Dependency Recognition Examples**:
- BAD: "Use image_qa_mock to analyze the 2 oldest paintings" (Where do the image URLs come from?)
- GOOD: Step 1: "Query database to get the 2 oldest paintings and their image URLs"
          Step 2: "Use image_qa_mock to analyze the images from step 1"

- BAD: "Create a visualization of customer distribution" (What data? From where?)
- GOOD: Step 1: "Query database to get customer distribution data"
          Step 2: "Create visualization using the data from step 1"

**When to Create Multiple Steps**:
- Tool needs data that must be retrieved first (database → analysis)
- Tool needs output from another tool (query → transform → visualize)
- Sequential operations that can't be done in one call

**When to Use Single Step**:
- Complete sub-agents that handle entire workflows (e.g., data_exploration_tool can query + store)
- Tool has all information needed in the user query
- No dependencies on other tools

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
            
            # Step 7: Attach intent to plan
            if intent:
                response.intent = intent
            
            # Step 8: Format plan for display
            plan_text = self._format_dynamic_plan(response)
            
            # Step 9: Determine response type
            if len(response.steps) == 0:
                response_type = "cancel"
            elif is_continuation:
                response_type = "continue"
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
                "messages": messages + [AIMessage(content=plan_text)],
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

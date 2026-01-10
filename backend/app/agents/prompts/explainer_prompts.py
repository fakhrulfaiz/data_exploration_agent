def get_explainer_system_prompt(user_preferences: str = "") -> str:
  
    base_prompt = """You are an execution explainer for a data exploration system.

Your role is to explain what happened during tool execution in a way that helps users understand:
1. What the tool accomplished (task completion status)
2. What the results mean and why they matter (execution summary)
3. What specific data was found (data evidence)
4. What the user can do next (actionable suggestions)

CRITICAL RULES:
- Base ALL explanations on actual tool outputs - NO hallucinations
- Extract specific facts from the output (numbers, names, counts)
- Avoid vague claims like "efficiently processed" or "successfully analyzed"
- Contextualize the result: Explain WHY this result is important for the overall goal
- Provide 2-3 concrete next actions the user can take

EXPLANATION STRUCTURE:
- Task Completion: Did it succeed/partially succeed/fail?
- Execution Summary: What happened and WHY it matters in 1-2 sentences
- Data Evidence: Specific facts from the output
- Actionable Suggestions: What can the user do with this result?"""

    # Inject user preferences if provided
    if user_preferences:
        return user_preferences + "\n\n" + base_prompt
    
    return base_prompt


def get_explanation_prompt_template(
    tool_name: str,
    tool_description: str,
    tool_input: str,
    tool_output: str,
    context: str,
    user_preferences: str = "",
    existing_decision: str = None,
    existing_reasoning: str = None
) -> str:
   
    context_section = f"""**Execution Context**:
{context}

**Tool Executed**: {tool_name}
**Tool Purpose**: {tool_description}

**Input Parameters**:
{tool_input}

**Tool Output**:
{tool_output}"""

    existing_section = ""
    if existing_decision or existing_reasoning:
        existing_section = "\n\n**Pre-existing Explanation** (DO NOT repeat, build upon it):\n"
        if existing_decision:
            existing_section += f"Decision: {existing_decision}\n"
        if existing_reasoning:
            existing_section += f"Reasoning: {existing_reasoning}\n"

    # Build task section with user preference consideration
    task_section = """
**Your Task**:
Generate a domain-specific explanation that:
1. Evaluates task completion status (success/partial/failed/unknown)
2. Summarizes what happened and its significance in 1-2 sentences
3. Extracts specific data evidence from the output (numbers, names, counts)
4. Provides 2-3 actionable suggestions for what the user can do next

**Important**:
- Base everything on the actual tool output above
- Explain WHY the result is relevant to the task
- Extract specific facts (e.g., "Found 42 paintings" not "Found paintings")
- Avoid performance claims unless verifiable from output
- Make suggestions concrete and clickable"""

    # Combine all sections
    if user_preferences:
        return user_preferences + "\n\n" + context_section + existing_section + "\n" + task_section
    
    return context_section + existing_section + "\n" + task_section

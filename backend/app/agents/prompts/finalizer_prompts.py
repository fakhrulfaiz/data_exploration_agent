import json

def get_finalizer_thought_system_prompt(user_preferences: str = "") -> str:

    base_prompt = """You are a synthesis agent analyzing execution results.

Your role is to:
1. Synthesize all execution steps into a coherent understanding
2. Determine if we have enough information to answer the user's query
3. Identify any limitations or gaps in the data

CRITICAL RULES:
- Base your analysis ONLY on actual execution results
- Don't make assumptions about data that wasn't retrieved
- Be honest about limitations or partial results
- Connect the dots between steps to show the complete picture"""

    # Inject user preferences if provided
    if user_preferences:
        return user_preferences + "\n\n" + base_prompt
    
    return base_prompt


def get_finalizer_thought_prompt(
    query: str,
    steps_summary: str,
    user_preferences: str = ""
) -> str:
    base_prompt = f"""**User Query**: {query}

**Execution Summary**:
{steps_summary}

**Your Task**:
Analyze the execution and provide:
1. **Overall Synthesis**: How do all the steps work together? Do we have what we need to answer the query?
2. **Reasoning Chain**: Step-by-step breakdown of what happened in each execution step

Focus on:
- What data was retrieved and transformed
- How each step contributed to answering the query
"""

    # Inject user preferences if provided
    if user_preferences:
        return user_preferences + "\n\n" + base_prompt
    
    return base_prompt


def get_finalizer_response_system_prompt(user_preferences: str = "", patterns: list = []) -> str:
    base_prompt = """You are a response synthesizer for a data exploration system.

Your role is to create a clear, direct answer to the user's query based on execution results.

RESPONSE GUIDELINES:
- Start with a direct answer to the query
- Support with specific data from execution results
- Use markdown formatting for readability
- Include relevant numbers, names, and facts
- Be honest about or partial results

**HANDLING ERRORS:**
When execution fails due to an error:
- **DO NOT** show raw error messages like "Error: Table not found", "Error Type: validation_error", "Tool Name: data_exploration_tool"
- **DO NOT** list technical error details
- **DO NOT** ask follow-up questions (e.g., "Would you like to...?", "Do you want to...?")
- **ONLY** acknowledge what couldn't be done in natural, conversational language
- Example: "I couldn't load the customer table because it doesn't exist in your database."
- Provide brief context about WHY if known, then stop
- The error explainer has already provided detailed guidance to the user

FORMAT:
- Use headers (##) to organize sections
- Use bullet points for lists
- Use **bold** for emphasis
- Use code blocks for data/SQL if relevant
- Keep it concise but complete

IMAGE FORMATTING RULES:
- **Generated Plots**: If the output contains plot images from large_plotting_tool (URLs starting with https://), preserve them EXACTLY as-is. Do NOT modify the URL.
- **Local Dataset Images**: If citing local images from the dataset (e.g., 'images/img_X.jpg'), ALWAYS use table format to save space. Show max 3 sample rows.
- Do NOT display local images inline with ![Image](/api/static/...) - this takes too much vertical space
- **Tables**: Make sure local dataset images are always displayed in tables, only external images (plots, web images) are in normal markdown format
- **Relative Paths**: Use relative paths `/api/static/...` for local dataset resources only, NOT for generated plots"""

    # Add RAG patterns as examples if provided
    if patterns:
        base_prompt += "\n\nRESPONSE PATTERN EXAMPLES:"
        for p in patterns:
            context = p.get("execution_context", "")
            template = p.get("response_template", "")
            if template:
                base_prompt += f"\n\nContext: {context}\n{template}"

    # Inject user preferences if provided
    if user_preferences:
        return user_preferences + "\n\n" + base_prompt
    
    return base_prompt


def get_finalizer_response_prompt(
    query: str,
    thought: str,
    steps_summary: str,
    user_preferences: str = ""
) -> str:
    
    base_prompt = f"""**User Query**: {query}

**Synthesis**:
{thought}

**Execution Summary**:
{steps_summary}

**Your Task**:
Generate a clear, direct final response to the user's query in markdown format.

Requirements:
- Answer the query directly based on execution results
- Include specific data and facts
- Use proper markdown formatting (follow the examples in system prompt)
- Be concise but complete
- Do NOT include next queries or follow-up suggestions in final response (handled separately in next_queries)

**Next Queries Requirements**:
- Suggest 3 natural language follow-up queries that users can ask
- **CRITICAL**: Base suggestions ONLY on the actual execution context above
  - Use column names that actually exist (check the Execution Summary)
  - Reference values that were actually seen in the data
  - Suggest operations similar to what was just done
- Use plain English only - NO tool names (e.g., 'data_exploration_tool', 'large_plotting_tool')
- Make them actionable commands, not questions

**Agent Capabilities** (use these to inform suggestions, but DON'T mention tool names):
The agent can:
- Query and filter database data (e.g., "Show me paintings from the Renaissance period")
- Sort and find specific records (e.g., "Find the oldest paintings in the collection")
- Analyze data with calculations (e.g., "Calculate the average inception year by movement")
- Create visualizations and charts (e.g., "Create a bar chart showing paintings by genre")
- Analyze images for visual content (e.g., "Find paintings depicting war scenes")
- Transform and manipulate data (e.g., "Group paintings by century")

**Examples of GOOD suggestions** (grounded in actual data):
  ✓ "Show me paintings from other art movements in the database" (if movement column exists)
  ✓ "Create a chart showing paintings by genre" (if genre column exists)
  ✓ "Find paintings depicting both war and swords" (if both columns were created)
  ✓ "List the earliest paintings in the collection" (if inception column exists)

**Examples of BAD suggestions** (hallucinated):
  ✗ "Show me paintings from the Baroque period" (if Baroque wasn't in the data)
  ✗ "List the most famous Renaissance artists" (if there's no 'famous' field)
  ✗ "Analyze the color palette of paintings" (if no image analysis was done)

**Error Handling**:
If execution failed or resulted in an error:
- Provide 3 helpful alternative suggestions based on what IS available
- Suggest simpler queries or different approaches
- Examples for error scenarios:
  ✓ "Show me all available data from the paintings table"
  ✓ "List the columns available in the database"
  ✓ "Find paintings from any art movement"
- DO NOT suggest the same query that just failed
- Make suggestions that are likely to succeed given the error context
"""

    # Inject user preferences if provided
    if user_preferences:
        return user_preferences + "\n\n" + base_prompt
    
    return base_prompt

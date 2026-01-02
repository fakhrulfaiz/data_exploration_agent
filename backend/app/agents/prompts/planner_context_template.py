# Database context - simple overview of what data exists
DATABASE_CONTEXT = """
**Available Data**:
- Paintings database containing artwork information
  - Fields: title, inception date, art movement, genre, image URLs
  - Contains historical paintings with metadata and images
"""

# Capabilities context - what the system can do (without mentioning specific tools)
CAPABILITIES_CONTEXT = """
**System Capabilities**:
- Query and retrieve data from the database
- Analyze images to extract visual information and answer questions about artwork
- Create visualizations to display data patterns and insights
"""

# Combined context for intent generation
def get_planner_context(user_preferences: str = "") -> str:
    """
    Get the full context for planner intent generation.
    
    Args:
        user_preferences: Optional user preference prompt from get_user_preference_prompt()
    """
    context_parts = [DATABASE_CONTEXT, CAPABILITIES_CONTEXT]
    
    # Add user preferences if provided
    if user_preferences:
        context_parts.insert(0, f"**User Preferences**:\n{user_preferences}\n")
    
    context_parts.append("Use this information to understand what's possible and plan accordingly.")
    
    return "\n\n".join(context_parts)

# Intent generation system prompt
INTENT_SYSTEM_PROMPT = """You are an intent understanding agent.
Your goal is to provide a "Thinking Process" narrative for the user's query.

{context}

Instructions:
1. Analyze the user's request in the context of available data and capabilities.
2. If user preferences are provided, tailor your response to match their communication style and needs.
3. Output a single, coherent paragraph written in first-person ("I need to...", "The goal is...").
4. Think about what data you'll need and what you'll do with it.
5. Explain the constraints, approach, and logical steps.
6. DO NOT mention specific tool names - focus on what needs to be done, not how.
7. DO NOT use bullet points or lists. Just a clear, flowing thought process.

Answer with Thought: [Your thought process here]
"""

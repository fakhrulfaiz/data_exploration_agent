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
def get_planner_context() -> str:
    """Get the full context for planner intent generation"""
    return f"""{DATABASE_CONTEXT}

{CAPABILITIES_CONTEXT}

Use this information to understand what's possible and plan accordingly.
"""

# Intent generation system prompt
INTENT_SYSTEM_PROMPT = """You are an intent understanding agent.
Your goal is to provide a "Thinking Process" narrative for the user's query.

{context}

Instructions:
1. Analyze the user's request in the context of available data and capabilities.
2. Output a single, coherent paragraph written in first-person ("I need to...", "The goal is...").
3. Think about what data you'll need and what you'll do with it.
4. Explain the constraints, approach, and logical steps.
5. DO NOT mention specific tool names - focus on what needs to be done, not how.
6. DO NOT use bullet points or lists. Just a clear, flowing thought process.

Answer with Thought: [Your thought process here]
"""

from langgraph.prebuilt import create_react_agent
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class AssistantAgent:
    def __init__(self, llm, transfer_tools: list):
        self.llm = llm
        self.transfer_tools = transfer_tools
        self._use_planning = None
        self._use_explainer = None
        self.base_agent = create_react_agent(
            model=llm,
            tools=transfer_tools,
            prompt=(
                "You are a helpful and intelligent assistant for a paintings database system.\n\n"
                "YOUR RESPONSIBILITIES:\n"
                "1. General Chat: You are a smart AI capable of engaging in normal conversation. If the user greets you, asks general knowledge questions, or discusses topics NOT related to the paintings database, ANSWER DIRECTLY. Do NOT transfer to the data tool.\n"
    
                "2. Database Access & Analysis: If the user asks ANY question that requires accessing, loading, viewing, querying, or analyzing data from the paintings database, transfer to the main agent.\n"
                "   - The database contains a 'paintings' table with: title, inception (date), movement, genre, image_url, img_path.\n"
                "   - Example: 'Show me Renaissance religious art' -> [Transfer]\n"
                "   - Example: 'Count the paintings by Van Gogh' -> [Transfer]\n"
                "   - Example: 'Load all data from paintings table' -> [Transfer]\n"
                "   - Example: 'Show me the data' -> [Transfer]\n"
                "   - Example: 'Analyze the color distribution of the images' -> [Transfer]\n\n"
                "RULES:\n"
                "- Transfer whenever the user wants to access, load, view, query, or analyze database data.\n"
                "- ONE transfer per message with full task description.\n"
                "- If transferring, do NOT generate any text response yourself. Just call the tool.\n"
                "- If NOT transferring, provide a helpful, complete text response."
            ),
            name="assistant"
        )
        
        logger.info("AssistantAgent initialized")
    
    def __call__(self, state):
        use_planning = state.get("use_planning", True)
        use_explainer = state.get("use_explainer", True)
        agent_type = state.get("agent_type", "data_exploration_tool")
        query = state.get("query", "")
        user_id = state.get("user_id")
        
        self._use_planning = use_planning
        self._use_explainer = use_explainer
        
        # Fetch user preferences and rebuild prompt if user_id is available
        personalized_prompt = None
        if user_id:
            try:
                from app.services.dependencies import get_redis_profile_service, get_profile_service
                from app.agents.prompts.user_preferences import get_user_preference_prompt_safe
                from app.agents.prompts.assistant_prompts import get_assistant_prompt
                
                redis_service = get_redis_profile_service()
                profile_service = get_profile_service()
                user_preferences = get_user_preference_prompt_safe(
                    user_id,
                    redis_service,
                    profile_service
                )
                
                if user_preferences:
                    personalized_prompt = get_assistant_prompt(user_preferences)
                    logger.info(f"Using personalized prompt for assistant agent (user: {user_id})")
            except Exception as e:
                logger.warning(f"Failed to fetch user preferences for assistant: {e}")
        
        # If we have a personalized prompt, create a new agent instance for this call
        if personalized_prompt:
            from langgraph.prebuilt import create_react_agent
            personalized_agent = create_react_agent(
                model=self.llm,
                tools=self.transfer_tools,
                prompt=personalized_prompt,
                name="assistant"
            )
            result = personalized_agent.invoke(state)
        else:
            # Use base agent with default prompt
            result = self.base_agent.invoke(state)
        
        if isinstance(result, dict):
            result["use_planning"] = use_planning
            result["use_explainer"] = use_explainer
            result["agent_type"] = agent_type
            result["query"] = query
        
        return result
    
    def get_planning_flag(self) -> Optional[bool]:
        """Get the current use_planning flag value."""
        return self._use_planning
    
    def get_explainer_flag(self) -> Optional[bool]:
        """Get the current use_explainer flag value."""
        return self._use_explainer

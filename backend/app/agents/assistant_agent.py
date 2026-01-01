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
                "You are a routing assistant for a paintings database system.\n\n"
                "DATABASE CONTEXT:\n"
                "The database contains a paintings table with columns: title, inception (date), movement, genre, image_url, img_path.\n"
                "Example data: Renaissance religious art from 1438, with images and metadata.\n\n"
                "ROUTING:\n"
                "- Database/data queries → Transfer to data_exploration_tool\n"
                "- General chat → Respond directly\n\n"
                "RULES:\n"
                "- Only transfer on NEW user messages\n"
                "- ONE transfer per message with full task\n"
                "- Don't say anything when transferring, just transfer\n"
            ),
            name="assistant"
        )
        
        logger.info("AssistantAgent initialized")
    
    def __call__(self, state):
        use_planning = state.get("use_planning", True)
        use_explainer = state.get("use_explainer", True)
        agent_type = state.get("agent_type", "data_exploration_tool")
        query = state.get("query", "")
        
        self._use_planning = use_planning
        self._use_explainer = use_explainer
        
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

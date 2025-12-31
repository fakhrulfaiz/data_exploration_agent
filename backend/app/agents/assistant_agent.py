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
                "You are an assistant that routes tasks to specialized agents.\n\n"
                "AVAILABLE AGENTS:\n"
                "- data_exploration_tool: Handles database queries and visualizations, SQL analysis, and data exploration\n"
                "  Use this for: SQL queries, database analysis, table inspection, data queries, schema questions, visualizations\n\n"
                "ROUTING LOGIC:\n"
                "- For DATA EXPLORATION queries: Transfer to data_exploration_tool\n"
                "- For general conversation: Respond normally without transferring\n\n"
                "TRANSFER RULES:\n"
                "- IMPORTANT: Only route to agents when you receive a NEW user message, not for agent responses\n"
                "- **CRITICAL: ONLY USE ONE TOOL CALL PER USER MESSAGE for transfers. PASS THE FULL TASK IN A SINGLE CALL.**\n"
                "- **CRITICAL: DO NOT SAY ANYTHING WHEN TRANSFERRING. JUST TRANSFER.**\n"
                "- **Example: If user asks for '3 different charts', call the transfer tool ONCE with the full request**\n\n"
                "EXAMPLES:\n"
                "- 'Show me sales data' → Transfer to data_exploration_tool\n"
                "- 'What tables are in the database?' → Transfer to data_exploration_tool\n"
                "- 'Hello, how are you?' → Respond directly\n"
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

import unittest
from unittest.mock import MagicMock, patch
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from app.agents.nodes.planner_node import PlannerNode

class TestPlannerSuppression(unittest.TestCase):
    def setUp(self):
        # Mock LLM and Tools
        self.mock_llm = MagicMock()
        self.mock_tools = []
        
        # Initialize Planner
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'fake-key'}):
            with patch('langchain_openai.ChatOpenAI') as MockChatOpenAI:
                 self.planner = PlannerNode(self.mock_llm, self.mock_tools)
                 # We need to mock the planning_llm specially since it's initialized inside __init__
                 self.planner.planning_llm = MagicMock()

    def test_first_turn_generates_intent(self):
        """Test that intent IS generated on the first turn (History = 1 Human Message)"""
        state = {
            "messages": [HumanMessage(content="Hello")],
            "use_explainer": True
        }
        
        # Mock _generate_intent_understanding to return a dummy value
        self.planner._generate_intent_understanding = MagicMock(return_value="Thought: Thinking...")
        self.planner._build_intent_context = MagicMock(return_value="")
        
        # Mock _format_dynamic_plan to avoid downstream errors
        self.planner._format_dynamic_plan = MagicMock(return_value="Plan")
        
        # Mock the structured output invocation
        mock_response = MagicMock()
        mock_response.steps = []
        mock_llm_structure = MagicMock()
        mock_llm_structure.invoke.return_value = mock_response
        self.planner.planning_llm.with_structured_output.return_value = mock_llm_structure

        try:
            self.planner._handle_dynamic_planning(state, state["messages"], "query")
        except Exception:
            pass # We only care about the call to _generate_intent_understanding

        # ASSERT: Intent generation SHOULD be called
        self.planner._generate_intent_understanding.assert_called_once()
        print("\n✅ PASS: First turn generated intent.")

    def test_continuation_skips_intent(self):
        """Test that intent is SKIPPED on subsequent turns (History > 1 Message)"""
        state = {
            "messages": [
                HumanMessage(content="Hello"), 
                AIMessage(content="Plan"), 
                HumanMessage(content="Feedback")
            ],
            "use_explainer": True
        }
        
        # Mock _generate_intent_understanding
        self.planner._generate_intent_understanding = MagicMock(return_value="Thought: Thinking...")
        self.planner._build_intent_context = MagicMock(return_value="")
        self.planner._format_dynamic_plan = MagicMock(return_value="Plan")
        
        mock_response = MagicMock()
        mock_response.steps = []
        mock_llm_structure = MagicMock()
        mock_llm_structure.invoke.return_value = mock_response
        self.planner.planning_llm.with_structured_output.return_value = mock_llm_structure

        try:
            self.planner._handle_dynamic_planning(state, state["messages"], "query")
        except Exception:
            pass

        # ASSERT: Intent generation should NOT be called
        self.planner._generate_intent_understanding.assert_not_called()
        print("\n✅ PASS: Continuation skipped intent.")

if __name__ == '__main__':
    unittest.main()

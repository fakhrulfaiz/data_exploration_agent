# data_exploration_test.py - Test suite for data_exploration_sub.py

"""
Test script for the enhanced data_exploration_sub.py module.
Tests:
1. Database connection and setup
2. Toolkit creation
3. Agent building with different LLM models
4. Full agent execution with sample tasks
"""

import sys
from pathlib import Path
from pprint import pprint

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage


# ============================================================================
# TEST 1: Database Connection
# ============================================================================

def test_database_connection(db_path: str = None):
    """Test database connection and basic info retrieval."""
    print("=" * 80)
    print("TEST 1: Database Connection")
    print("=" * 80)
    
    from agent.data_exploration_sub import setup_database, get_database_info
    
    try:
        db_info = get_database_info(db_path)
        print(f"Database dialect: {db_info['dialect']}")
        print(f"Database path: {db_info['db_path']}")
        print(f"Tables available: {db_info['tables']}")
        print("✅ Database connection test passed!\n")
        return db_info
    except Exception as e:
        print(f"❌ Database connection failed: {e}\n")
        return None


# ============================================================================
# TEST 2: Toolkit Setup
# ============================================================================

def test_toolkit_setup(model_name: str = "gpt-4o", db_path: str = None):
    """Test SQL toolkit creation."""
    print("=" * 80)
    print(f"TEST 2: Toolkit Setup (model={model_name})")
    print("=" * 80)
    
    from agent.data_exploration_sub import setup_database, setup_toolkit
    from langchain.chat_models import init_chat_model
    
    try:
        db = setup_database(db_path)
        llm = init_chat_model(model_name)
        tools = setup_toolkit(db, llm)
        
        print(f"Number of tools created: {len(tools)}")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description[:60]}...")
        
        print("✅ Toolkit setup test passed!\n")
        return tools
    except Exception as e:
        print(f"❌ Toolkit setup failed: {e}\n")
        return None


# ============================================================================
# TEST 3: Agent Building with Different LLMs
# ============================================================================

def test_agent_building(model_name: str = "gpt-4o", db_path: str = None):
    """Test building the agent with different LLM models."""
    print("=" * 80)
    print(f"TEST 3: Agent Building (model={model_name})")
    print("=" * 80)
    
    from agent.data_exploration_sub import build_data_exploration_agent
    
    try:
        agent = build_data_exploration_agent(model_name=model_name, db_path=db_path)
        print(f"Agent type: {type(agent)}")
        print("✅ Agent building test passed!\n")
        return agent
    except Exception as e:
        print(f"❌ Error building agent: {e}\n")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# TEST 4: Full Agent Execution
# ============================================================================

def test_agent_execution(agent, task: str):
    """Test full agent execution with a sample task."""
    print("=" * 80)
    print("TEST 4: Full Agent Execution")
    print("=" * 80)
    print(f"Task: {task}")
    print("-" * 80)
    
    # Prepare initial state
    initial_state = {
        "messages": [HumanMessage(content=task)],
        "original_task": task,
        "query_history": [],
        "tables_queried": [],
        "exploration_complete": False,
        "ready_for_export": False
    }
    
    try:
        result = agent.invoke(initial_state)
        
        # Print results
        print("\n📊 Execution Results:")
        print("-" * 40)
        
        # Print messages (last few only)
        messages = result.get("messages", [])
        print(f"\nTotal messages: {len(messages)}")
        
        # Show last 3 messages
        for i, msg in enumerate(messages[-3:]):
            msg_type = type(msg).__name__
            content_preview = str(msg.content)[:300] if hasattr(msg, 'content') else str(msg)[:300]
            print(f"  [{len(messages) - 3 + i}] {msg_type}: {content_preview}...")
        
        # Print query history
        query_history = result.get("query_history", [])
        print(f"\nQuery history: {len(query_history)} queries")
        for i, query in enumerate(query_history[:3]):  # First 3 queries
            if hasattr(query, 'to_summary'):
                print(f"  {i+1}. {query.to_summary()}")
            else:
                print(f"  {i+1}. {str(query)[:100]}...")
        
        # Print tables queried
        print(f"\nTables queried: {result.get('tables_queried', [])}")
        print(f"Exploration complete: {result.get('exploration_complete', False)}")
        print(f"Ready for export: {result.get('ready_for_export', False)}")
        
        # Print result summary if available
        result_summary = result.get("result_summary", "")
        if result_summary:
            print(f"\nResult Summary (first 500 chars):\n{result_summary[:500]}...")
        
        print("\n✅ Agent execution test passed!\n")
        return result
        
    except Exception as e:
        print(f"❌ Error during execution: {e}\n")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# TEST 5: Streaming Execution
# ============================================================================

def test_agent_streaming(agent, task: str, max_steps: int = 10):
    """Test agent execution with streaming output."""
    print("=" * 80)
    print("TEST 5: Streaming Execution")
    print("=" * 80)
    print(f"Task: {task}")
    print(f"Max steps: {max_steps}")
    print("-" * 80)
    
    # Prepare initial state
    initial_state = {
        "messages": [HumanMessage(content=task)],
        "original_task": task,
        "query_history": [],
        "tables_queried": [],
        "exploration_complete": False,
        "ready_for_export": False
    }
    
    try:
        step_count = 0
        final_step = None
        
        for step in agent.stream(initial_state, stream_mode="values"):
            step_count += 1
            final_step = step
            
            if "messages" in step and step["messages"]:
                last_msg = step["messages"][-1]
                msg_type = type(last_msg).__name__
                print(f"\n[Step {step_count}] {msg_type}")
                
                if hasattr(last_msg, 'content') and last_msg.content:
                    content_preview = str(last_msg.content)[:200]
                    print(f"  Content: {content_preview}...")
                
                if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                    print(f"  Tool calls: {len(last_msg.tool_calls)}")
            
            if step_count >= max_steps:
                print(f"\n⚠️ Stopped after {max_steps} steps (limit reached)")
                break
        
        print(f"\n📊 Streaming completed in {step_count} steps")
        
        if final_step:
            print(f"Final state keys: {list(final_step.keys())}")
            if final_step.get("result_summary"):
                print(f"Result summary available: Yes")
        
        print("\n✅ Streaming execution test passed!\n")
        return final_step
        
    except Exception as e:
        print(f"❌ Error during streaming: {e}\n")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# TEST 6: Supervisor Tool Creation
# ============================================================================

def test_supervisor_tool(model_name: str = "gpt-4o", db_path: str = None):
    """Test creating the data exploration tool for supervisor agents."""
    print("=" * 80)
    print(f"TEST 6: Supervisor Tool Creation (model={model_name})")
    print("=" * 80)
    
    from agent.data_exploration_sub import create_data_exploration_tool_for_supervisor
    
    try:
        tool = create_data_exploration_tool_for_supervisor(
            model_name=model_name,
            db_path=db_path
        )
        print(f"Tool name: {tool.name}")
        print(f"Tool description: {tool.description[:100]}...")
        print("✅ Supervisor tool creation test passed!\n")
        return tool
    except Exception as e:
        print(f"❌ Error creating supervisor tool: {e}\n")
        return None


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests(
    model_name: str = "gpt-4o",
    db_path: str = None,
    run_execution_test: bool = False,
    run_streaming_test: bool = False,
    test_task: str = None
):
    """
    Run all tests for data_exploration_sub.py.
    
    Args:
        model_name: LLM model to use for testing
        db_path: Path to the database (uses default if None)
        run_execution_test: Whether to run the full agent execution test (takes time and API calls)
        run_streaming_test: Whether to run the streaming test
        test_task: Task description for execution test
    """
    print("\n" + "🚀 " * 20)
    print("DATA EXPLORATION SUB TEST SUITE")
    print("🚀 " * 20 + "\n")
    
    # Test 1: Database connection
    db_info = test_database_connection(db_path)
    
    # Test 2: Toolkit setup
    if db_info:
        test_toolkit_setup(model_name=model_name, db_path=db_path)
    
    # Test 3: Agent building
    agent = test_agent_building(model_name=model_name, db_path=db_path)
    
    # Default test task
    if test_task is None:
        test_task = "Which genre has the most paintings? Show all genres with their painting counts."
    
    # Test 4: Full execution (optional)
    if run_execution_test and agent:
        test_agent_execution(agent, test_task)
    else:
        print("=" * 80)
        print("TEST 4: Full Agent Execution - SKIPPED")
        print("(Set run_execution_test=True to enable)")
        print("=" * 80 + "\n")
    
    # Test 5: Streaming execution (optional)
    if run_streaming_test and agent:
        test_agent_streaming(agent, test_task, max_steps=15)
    else:
        print("=" * 80)
        print("TEST 5: Streaming Execution - SKIPPED")
        print("(Set run_streaming_test=True to enable)")
        print("=" * 80 + "\n")
    
    # Test 6: Supervisor tool (optional - creates new agent)
    # Uncomment to test:
    # test_supervisor_tool(model_name=model_name, db_path=db_path)
    print("=" * 80)
    print("TEST 6: Supervisor Tool Creation - SKIPPED")
    print("(Uncomment in code to enable)")
    print("=" * 80 + "\n")
    
    print("\n" + "✅ " * 20)
    print("ALL TESTS COMPLETED")
    print("✅ " * 20 + "\n")


# ============================================================================
# QUICK TEST FUNCTIONS
# ============================================================================

def quick_test():
    """Quick test - just database connection and agent building."""
    test_database_connection()
    test_agent_building()


def full_test(model_name: str = "gpt-4o"):
    """Full test including agent execution."""
    run_all_tests(
        model_name=model_name,
        run_execution_test=True,
        run_streaming_test=False,
        test_task="Which genre has the most paintings? Show all genres with their painting counts."
    )


def streaming_test(model_name: str = "gpt-4o"):
    """Test with streaming output."""
    run_all_tests(
        model_name=model_name,
        run_execution_test=False,
        run_streaming_test=True,
        test_task="List the top 5 paintings with the earliest inception dates."
    )


def test_specific_task(task: str, model_name: str = "gpt-4o"):
    """Test with a specific task."""
    from agent.data_exploration_sub import build_data_exploration_agent
    
    agent = build_data_exploration_agent(model_name=model_name)
    return test_agent_execution(agent, task)


# ============================================================================
# EXAMPLE TASKS FOR TESTING
# ============================================================================

EXAMPLE_TASKS = [
    "Which genre has the most paintings? Show all genres with their painting counts.",
    "List the top 5 paintings with the earliest inception dates.",
    "How many paintings are in each century (1400s, 1500s, etc.)?",
    "What are the different art movements represented and how many paintings in each?",
    "Find paintings that have both movement and genre information available.",
]


def list_example_tasks():
    """Print example tasks for testing."""
    print("=" * 80)
    print("EXAMPLE TASKS FOR TESTING")
    print("=" * 80)
    for i, task in enumerate(EXAMPLE_TASKS, 1):
        print(f"{i}. {task}")
    print("=" * 80)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test data_exploration_sub.py")
    parser.add_argument("--model", type=str, default="gpt-4o", help="LLM model name")
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite database")
    parser.add_argument("--full", action="store_true", help="Run full test including execution")
    parser.add_argument("--quick", action="store_true", help="Run quick test only")
    parser.add_argument("--stream", action="store_true", help="Run streaming test")
    parser.add_argument("--task", type=str, default=None, help="Custom task to test")
    parser.add_argument("--examples", action="store_true", help="List example tasks")
    
    args = parser.parse_args()
    
    if args.examples:
        list_example_tasks()
    elif args.quick:
        quick_test()
    elif args.full:
        full_test(model_name=args.model)
    elif args.stream:
        streaming_test(model_name=args.model)
    elif args.task:
        test_specific_task(args.task, model_name=args.model)
    else:
        run_all_tests(
            model_name=args.model,
            db_path=args.db,
            run_execution_test=False,
            run_streaming_test=False
        )

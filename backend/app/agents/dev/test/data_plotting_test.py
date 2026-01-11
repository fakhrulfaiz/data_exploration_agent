# data_plotting_test.py - Test suite for data_plotting_sub.py

"""
Test script for the enhanced data_plotting_sub.py module.
Tests:
1. REPL utilities
2. Tool functions
3. Agent building with different LLM models
4. Full agent execution with sample tasks
"""

import sys
import os
from pathlib import Path
from pprint import pprint

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage


# ============================================================================
# WORKSPACE PATHS
# ============================================================================

WORKSPACE_DIR = "/home/afiq/fyp/fafa-repo/backend/app/agents/dev/workspace"
PLOT_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "plot")
DATA_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "outputs")


# ============================================================================
# TEST 1: REPL Utilities
# ============================================================================

def test_repl_utilities():
    """Test Python REPL utilities."""
    print("=" * 80)
    print("TEST 1: REPL Utilities")
    print("=" * 80)
    
    from agent.data_plotting_sub import PythonREPL, _extract_code_from_block
    
    # Test code extraction
    test_code_block = """```python
print("Hello World")
```"""
    
    extracted = _extract_code_from_block(test_code_block)
    print(f"Code extraction test:")
    print(f"  Input: {test_code_block[:50]}...")
    print(f"  Extracted: {extracted.strip()}")
    
    # Test REPL execution
    repl = PythonREPL()
    result = repl.run('print("REPL test successful")')
    print(f"REPL execution test: {result}")
    
    # Test error handling
    error_result = repl.run('1/0')
    print(f"Error handling test: {'Error' in error_result}")
    
    print("✅ REPL utilities test passed!\n")
    return True


# ============================================================================
# TEST 2: Tool Functions
# ============================================================================

def test_read_csv_tool():
    """Test the read_csv_file tool."""
    print("=" * 80)
    print("TEST 2: Read CSV Tool")
    print("=" * 80)
    
    from agent.data_plotting_sub import read_csv_file
    
    # Check if any CSV files exist in workspace
    csv_files = list(Path(DATA_OUTPUT_DIR).glob("*.csv"))
    
    if not csv_files:
        print("⚠️ No CSV files found in workspace/outputs")
        print("  Creating a test CSV file...")
        
        # Create a simple test CSV
        test_csv_path = os.path.join(DATA_OUTPUT_DIR, "test_data.csv")
        os.makedirs(DATA_OUTPUT_DIR, exist_ok=True)
        
        with open(test_csv_path, "w") as f:
            f.write("category,count,value\n")
            f.write("A,10,100\n")
            f.write("B,20,200\n")
            f.write("C,15,150\n")
            f.write("D,25,250\n")
        
        csv_files = [Path(test_csv_path)]
        print(f"  Created: {test_csv_path}")
    
    # Test reading the first CSV file
    test_file = str(csv_files[0])
    print(f"\nReading file: {test_file}")
    
    result = read_csv_file.invoke({"file_path": test_file})
    
    if "Error" in result:
        print(f"❌ Read CSV failed: {result}")
        return None
    else:
        print(f"Result preview:\n{result[:500]}...")
        print("\n✅ Read CSV tool test passed!\n")
        return test_file


# ============================================================================
# TEST 3: Agent Building with Different LLMs
# ============================================================================

def test_agent_building(model_name: str = "gpt-4o"):
    """Test building the agent with different LLM models."""
    print("=" * 80)
    print(f"TEST 3: Agent Building (model={model_name})")
    print("=" * 80)
    
    from agent.data_plotting_sub import build_plotting_agent
    
    try:
        agent = build_plotting_agent(model_name=model_name)
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

def test_agent_execution(agent, task: str, file_path: str):
    """Test full agent execution with a sample task."""
    print("=" * 80)
    print("TEST 4: Full Agent Execution")
    print("=" * 80)
    print(f"Task: {task}")
    print(f"File: {file_path}")
    print("-" * 80)
    
    # Prepare initial state
    initial_state = {
        "messages": [HumanMessage(content=f"Create plots for: {task}\nData file: {file_path}")],
        "original_task": task,
        "files_to_plot": [file_path],
        "plot_records": [],
        "plots_generated": [],
        "tools_complete": False,
        "result_summary": ""
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
        
        # Print plot records
        plot_records = result.get("plot_records", [])
        print(f"\nPlot records: {len(plot_records)}")
        for record in plot_records:
            status = "✅" if record.success else "❌"
            print(f"  {status} {record.plot_type}: {record.output_path or record.error_message}")
        
        # Print generated plots
        plots_generated = result.get("plots_generated", [])
        print(f"\nGenerated plot files: {plots_generated}")
        
        # Print file info
        file_info = result.get("file_info")
        if file_info:
            print(f"\nFile analyzed: {file_info.file_path}")
            print(f"  Columns: {file_info.columns}")
            print(f"  Rows: {file_info.row_count}")
        
        # Print result summary
        result_summary = result.get("result_summary", "")
        if result_summary:
            print(f"\nResult Summary:\n{result_summary[:500]}...")
        
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

def test_agent_streaming(agent, task: str, file_path: str, max_steps: int = 10):
    """Test agent execution with streaming output."""
    print("=" * 80)
    print("TEST 5: Streaming Execution")
    print("=" * 80)
    print(f"Task: {task}")
    print(f"File: {file_path}")
    print(f"Max steps: {max_steps}")
    print("-" * 80)
    
    # Prepare initial state
    initial_state = {
        "messages": [HumanMessage(content=f"Create plots for: {task}\nData file: {file_path}")],
        "original_task": task,
        "files_to_plot": [file_path],
        "plot_records": [],
        "plots_generated": [],
        "tools_complete": False,
        "result_summary": ""
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
                    for tc in last_msg.tool_calls:
                        print(f"  Tool: {tc['name']}")
            
            if step_count >= max_steps:
                print(f"\n⚠️ Stopped after {max_steps} steps (limit reached)")
                break
        
        print(f"\n📊 Streaming completed in {step_count} steps")
        
        if final_step:
            print(f"Final state keys: {list(final_step.keys())}")
            plots = final_step.get("plots_generated", [])
            if plots:
                print(f"Generated plots: {plots}")
        
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

def test_supervisor_tool(model_name: str = "gpt-4o"):
    """Test creating the plotting tool for supervisor agents."""
    print("=" * 80)
    print(f"TEST 6: Supervisor Tool Creation (model={model_name})")
    print("=" * 80)
    
    from agent.data_plotting_sub import create_plotting_tool_for_supervisor
    
    try:
        tool = create_plotting_tool_for_supervisor(model_name=model_name)
        print(f"Tool name: {tool.name}")
        print(f"Tool description: {tool.description[:100]}...")
        print("✅ Supervisor tool creation test passed!\n")
        return tool
    except Exception as e:
        print(f"❌ Error creating supervisor tool: {e}\n")
        return None


# ============================================================================
# TEST 7: Execute Plotting Task Helper
# ============================================================================

def test_execute_plotting_task(task: str, file_path: str, model_name: str = "gpt-4o"):
    """Test the execute_plotting_task helper function."""
    print("=" * 80)
    print(f"TEST 7: Execute Plotting Task Helper")
    print("=" * 80)
    print(f"Task: {task}")
    print(f"File: {file_path}")
    print(f"Model: {model_name}")
    print("-" * 80)
    
    from agent.data_plotting_sub import execute_plotting_task
    
    try:
        result, summary = execute_plotting_task(task, file_path, model_name)
        
        print(f"\nResult type: {type(result)}")
        print(f"Summary:\n{summary[:500] if summary else 'No summary'}")
        
        plots = result.get("plots_generated", [])
        if plots:
            print(f"\nGenerated plots: {plots}")
        
        print("\n✅ Execute plotting task test passed!\n")
        return result, summary
        
    except Exception as e:
        print(f"❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
        return None, None


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests(
    model_name: str = "gpt-4o",
    run_execution_test: bool = False,
    run_streaming_test: bool = False,
    test_task: str = None,
    test_file: str = None
):
    """
    Run all tests for data_plotting_sub.py.
    
    Args:
        model_name: LLM model to use for testing
        run_execution_test: Whether to run the full agent execution test (takes time and API calls)
        run_streaming_test: Whether to run the streaming test
        test_task: Task description for execution test
        test_file: CSV file path for execution test
    """
    print("\n" + "🚀 " * 20)
    print("DATA PLOTTING SUB TEST SUITE")
    print("🚀 " * 20 + "\n")
    
    # Test 1: REPL utilities
    test_repl_utilities()
    
    # Test 2: Read CSV tool
    csv_file = test_read_csv_tool()
    if test_file is None:
        test_file = csv_file
    
    # Test 3: Agent building
    agent = test_agent_building(model_name=model_name)
    
    # Default test task
    if test_task is None:
        test_task = "Create a bar chart showing category vs count"
    
    # Test 4: Full execution (optional)
    if run_execution_test and agent and test_file:
        test_agent_execution(agent, test_task, test_file)
    else:
        print("=" * 80)
        print("TEST 4: Full Agent Execution - SKIPPED")
        print("(Set run_execution_test=True to enable)")
        print("=" * 80 + "\n")
    
    # Test 5: Streaming execution (optional)
    if run_streaming_test and agent and test_file:
        test_agent_streaming(agent, test_task, test_file, max_steps=10)
    else:
        print("=" * 80)
        print("TEST 5: Streaming Execution - SKIPPED")
        print("(Set run_streaming_test=True to enable)")
        print("=" * 80 + "\n")
    
    # Test 6 & 7: Supervisor tool and helper (optional)
    print("=" * 80)
    print("TEST 6 & 7: Supervisor Tool & Helper - SKIPPED")
    print("(Uncomment in code to enable)")
    print("=" * 80 + "\n")
    
    print("\n" + "✅ " * 20)
    print("ALL TESTS COMPLETED")
    print("✅ " * 20 + "\n")


# ============================================================================
# QUICK TEST FUNCTIONS
# ============================================================================

def quick_test():
    """Quick test - just REPL and agent building."""
    test_repl_utilities()
    test_read_csv_tool()
    test_agent_building()


def full_test(model_name: str = "gpt-4o", file_path: str = None):
    """Full test including agent execution."""
    run_all_tests(
        model_name=model_name,
        run_execution_test=True,
        run_streaming_test=False,
        test_task="Create a bar chart showing category distribution",
        test_file=file_path
    )


def streaming_test(model_name: str = "gpt-4o", file_path: str = None):
    """Test with streaming output."""
    run_all_tests(
        model_name=model_name,
        run_execution_test=False,
        run_streaming_test=True,
        test_task="Create a pie chart showing the value distribution",
        test_file=file_path
    )


def test_specific_plot(task: str, file_path: str, model_name: str = "gpt-4o"):
    """Test with a specific plotting task."""
    from agent.data_plotting_sub import build_plotting_agent
    
    agent = build_plotting_agent(model_name=model_name)
    return test_agent_execution(agent, task, file_path)


# ============================================================================
# EXAMPLE TASKS FOR TESTING
# ============================================================================

EXAMPLE_TASKS = [
    ("Create a bar chart showing category vs count", "test_data.csv"),
    ("Create a pie chart showing value distribution", "test_data.csv"),
    ("Create a line plot showing trends", "test_data.csv"),
    ("Create a scatter plot of count vs value", "test_data.csv"),
    ("Create a histogram of the count column", "test_data.csv"),
]


def list_example_tasks():
    """Print example tasks for testing."""
    print("=" * 80)
    print("EXAMPLE TASKS FOR TESTING")
    print("=" * 80)
    for i, (task, file) in enumerate(EXAMPLE_TASKS, 1):
        print(f"{i}. Task: {task}")
        print(f"   File: {file}")
    print("=" * 80)


def list_available_csv_files():
    """List available CSV files in workspace."""
    print("=" * 80)
    print("AVAILABLE CSV FILES")
    print("=" * 80)
    
    for dir_path in [DATA_OUTPUT_DIR, WORKSPACE_DIR]:
        csv_files = list(Path(dir_path).glob("*.csv"))
        if csv_files:
            print(f"\nIn {dir_path}:")
            for f in csv_files:
                print(f"  - {f.name}")
    
    print("=" * 80)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test data_plotting_sub.py")
    parser.add_argument("--model", type=str, default="gpt-4o", help="LLM model name")
    parser.add_argument("--file", type=str, default=None, help="Path to CSV file for testing")
    parser.add_argument("--full", action="store_true", help="Run full test including execution")
    parser.add_argument("--quick", action="store_true", help="Run quick test only")
    parser.add_argument("--stream", action="store_true", help="Run streaming test")
    parser.add_argument("--task", type=str, default=None, help="Custom plotting task to test")
    parser.add_argument("--examples", action="store_true", help="List example tasks")
    parser.add_argument("--list-files", action="store_true", help="List available CSV files")
    
    args = parser.parse_args()
    
    if args.examples:
        list_example_tasks()
    elif args.list_files:
        list_available_csv_files()
    elif args.quick:
        quick_test()
    elif args.full:
        full_test(model_name=args.model, file_path=args.file)
    elif args.stream:
        streaming_test(model_name=args.model, file_path=args.file)
    elif args.task and args.file:
        test_specific_plot(args.task, args.file, model_name=args.model)
    else:
        run_all_tests(
            model_name=args.model,
            test_file=args.file,
            run_execution_test=False,
            run_streaming_test=False
        )

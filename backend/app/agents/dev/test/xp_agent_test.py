# xp_agent_test.py - Test suite for XpAgent.py

"""
Test script for the XpAgent (main supervisor agent).
Tests:
1. Subagent factory creation
2. Agent building with different LLM models
3. Individual subagent execution
4. Full agent execution with sample tasks
5. Streaming execution
6. Tool wrapper creation
"""

import sys
import time
import argparse
from pathlib import Path
from pprint import pprint

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage, AIMessage


# ============================================================================
# TEST 1: Subagent Factory
# ============================================================================

def test_subagent_factory(model_name: str = "gpt-4o-mini"):
    """Test SubagentFactory creation and configuration."""
    print("=" * 80)
    print(f"TEST 1: Subagent Factory (model={model_name})")
    print("=" * 80)
    
    from agent.XpAgent import SubagentFactory, DEFAULT_DB_PATH
    
    try:
        factory = SubagentFactory(
            model_name=model_name,
            db_path=DEFAULT_DB_PATH,
            use_gpu=None  # Auto-detect
        )
        
        print(f"✅ Factory created successfully")
        print(f"   Model: {factory.model_name}")
        print(f"   DB Path: {factory.db_path}")
        print(f"   GPU: {factory.use_gpu}")
        
        return factory
        
    except Exception as e:
        print(f"❌ Factory creation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# TEST 2: Agent Building
# ============================================================================

def test_agent_building(model_name: str = "gpt-4o-mini"):
    """Test building the XP agent with different LLM models."""
    print("=" * 80)
    print(f"TEST 2: Agent Building (model={model_name})")
    print("=" * 80)
    
    from agent.XpAgent import build_xp_agent
    
    try:
        agent = build_xp_agent(model_name=model_name)
        print(f"✅ Agent built successfully")
        print(f"   Agent type: {type(agent)}")
        return agent
        
    except Exception as e:
        print(f"❌ Agent building failed: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# TEST 3: Individual Subagent Execution
# ============================================================================

def test_subagent_execution(model_name: str = "gpt-4o-mini"):
    """Test individual subagent execution through the factory."""
    print("=" * 80)
    print(f"TEST 3: Individual Subagent Execution (model={model_name})")
    print("=" * 80)
    
    from agent.XpAgent import SubagentFactory, execute_data_exploration
    
    try:
        factory = SubagentFactory(model_name=model_name)
        
        # Test data exploration
        print("\n📊 Testing Data Exploration Subagent...")
        query = "SELECT COUNT(*) as count FROM paintings"
        
        result, context = execute_data_exploration(query, factory)
        
        print(f"   Success: {result.success}")
        print(f"   Result preview: {result.result_content[:200]}...")
        print(f"   Output file: {result.output_file}")
        
        print("\n✅ Subagent execution test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Subagent execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


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
    
    initial_state = {
        "messages": [HumanMessage(content=task)],
        "original_query": task,
        "plan_steps": [],
        "step_results": [],
        "tool_context": "",
        "current_step_index": 0,
        "total_steps": 0,
        "completed_steps": 0,
        "replan_count": 0,
        "max_replans": 3,
        "execution_complete": False,
        "generated_files": []
    }
    
    try:
        start_time = time.time()
        result = agent.invoke(initial_state)
        elapsed = time.time() - start_time
        
        print(f"\n📊 Execution Results:")
        print(f"   Elapsed time: {elapsed:.2f}s")
        print("-" * 40)
        
        # Print plan steps
        plan_steps = result.get("plan_steps", [])
        print(f"\n📋 Plan Steps: {len(plan_steps)}")
        for step in plan_steps:
            status_icon = {"completed": "✅", "failed": "❌", "pending": "⏳", "in_progress": "🔄"}.get(step.status, "❓")
            print(f"   {status_icon} Step {step.step_number}: {step.description}")
            print(f"      Tool: {step.tool_name}")
        
        # Print step results
        step_results = result.get("step_results", [])
        print(f"\n📈 Step Results: {len(step_results)}")
        for r in step_results:
            status = "✅" if r.success else "❌"
            print(f"   {status} Step {r.step_number}: {r.result_content[:150]}...")
            if r.output_file:
                print(f"      Output: {r.output_file}")
        
        # Print final answer
        final_answer = result.get("final_answer", "")
        print(f"\n💬 Final Answer:")
        print("-" * 40)
        print(final_answer[:500] if final_answer else "No final answer generated")
        
        # Print generated files
        generated_files = result.get("generated_files", [])
        if generated_files:
            print(f"\n📁 Generated Files:")
            for f in generated_files:
                print(f"   - {f}")
        
        print("\n✅ Agent execution test passed!")
        return result
        
    except Exception as e:
        print(f"\n❌ Execution failed: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# TEST 5: Streaming Execution
# ============================================================================

def test_streaming_execution(model_name: str = "gpt-4o-mini", task: str = None):
    """Test streaming execution of the agent."""
    print("=" * 80)
    print(f"TEST 5: Streaming Execution (model={model_name})")
    print("=" * 80)
    
    from agent.XpAgent import run_task
    
    task = task or "How many paintings are there in the database?"
    print(f"Task: {task}")
    print("-" * 80)
    
    try:
        stream = run_task(task, model_name=model_name, stream=True)
        
        step_count = 0
        for step in stream:
            step_count += 1
            
            # Print step info
            current_idx = step.get("current_step_index", 0)
            total = step.get("total_steps", 0)
            complete = step.get("execution_complete", False)
            
            print(f"\n📍 Stream Step {step_count} | Progress: {current_idx}/{total} | Complete: {complete}")
            
            # Print last message if available
            messages = step.get("messages", [])
            if messages:
                last_msg = messages[-1]
                msg_type = type(last_msg).__name__
                content = last_msg.content[:200] if hasattr(last_msg, 'content') else str(last_msg)[:200]
                print(f"   [{msg_type}] {content}...")
            
            # Print plan steps on first appearance
            if step_count == 2:  # After planning
                plan_steps = step.get("plan_steps", [])
                if plan_steps:
                    print(f"\n   📋 Plan ({len(plan_steps)} steps):")
                    for s in plan_steps:
                        print(f"      - {s.description} ({s.tool_name})")
        
        # Final result
        print(f"\n" + "=" * 40)
        print("📊 Final Result:")
        print(step.get("final_answer", "No answer")[:500])
        
        print("\n✅ Streaming test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Streaming failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# TEST 6: Tool Wrapper
# ============================================================================

def test_tool_wrapper(model_name: str = "gpt-4o-mini"):
    """Test creating the XP agent as a tool for supervisors."""
    print("=" * 80)
    print(f"TEST 6: Tool Wrapper (model={model_name})")
    print("=" * 80)
    
    from agent.XpAgent import create_xp_tool_for_supervisor
    
    try:
        xp_tool = create_xp_tool_for_supervisor(model_name=model_name)
        
        print(f"✅ Tool created successfully")
        print(f"   Tool name: {xp_tool.name}")
        print(f"   Description: {xp_tool.description[:100]}...")
        
        return xp_tool
        
    except Exception as e:
        print(f"❌ Tool creation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# TEST 7: Multiple Model Comparison
# ============================================================================

def test_model_comparison(task: str = None):
    """Test the agent with different LLM models."""
    print("=" * 80)
    print("TEST 7: Multiple Model Comparison")
    print("=" * 80)
    
    from agent.XpAgent import build_xp_agent
    
    models = ["gpt-4o-mini", "gpt-4o"]
    task = task or "How many paintings are in the Renaissance movement?"
    
    print(f"Task: {task}")
    print("-" * 80)
    
    results = {}
    
    for model in models:
        print(f"\n🤖 Testing model: {model}")
        try:
            agent = build_xp_agent(model_name=model)
            
            initial_state = {
                "messages": [HumanMessage(content=task)],
                "original_query": task,
                "plan_steps": [],
                "step_results": [],
                "tool_context": "",
                "current_step_index": 0,
                "total_steps": 0,
                "execution_complete": False,
                "generated_files": []
            }
            
            start = time.time()
            result = agent.invoke(initial_state)
            elapsed = time.time() - start
            
            results[model] = {
                "success": True,
                "time": elapsed,
                "steps": len(result.get("step_results", [])),
                "answer_preview": result.get("final_answer", "")[:200]
            }
            
            print(f"   ✅ Completed in {elapsed:.2f}s")
            print(f"   Steps: {results[model]['steps']}")
            
        except Exception as e:
            results[model] = {"success": False, "error": str(e)}
            print(f"   ❌ Failed: {e}")
    
    # Summary
    print("\n" + "=" * 40)
    print("📊 Comparison Summary:")
    for model, data in results.items():
        if data["success"]:
            print(f"   {model}: {data['time']:.2f}s, {data['steps']} steps")
        else:
            print(f"   {model}: FAILED - {data['error']}")
    
    return results


# ============================================================================
# RUN ALL TESTS
# ============================================================================

def run_all_tests(model_name: str = "gpt-4o-mini", full: bool = False):
    """Run all tests."""
    print("\n" + "=" * 80)
    print("🧪 XP AGENT TEST SUITE")
    print(f"   Model: {model_name}")
    print(f"   Full tests: {full}")
    print("=" * 80 + "\n")
    
    results = {}
    
    # Test 1: Factory
    print("\n" + "🔹" * 40 + "\n")
    factory = test_subagent_factory(model_name)
    results["factory"] = factory is not None
    
    # Test 2: Agent Building
    print("\n" + "🔹" * 40 + "\n")
    agent = test_agent_building(model_name)
    results["building"] = agent is not None
    
    if not full:
        # Quick tests only
        print("\n" + "🔹" * 40 + "\n")
        print("ℹ️  Quick test mode. Use --full for complete tests.\n")
        
        # Summary
        print("\n" + "=" * 80)
        print("📋 TEST SUMMARY (Quick Mode)")
        print("=" * 80)
        for test, passed in results.items():
            status = "✅" if passed else "❌"
            print(f"   {status} {test}")
        
        return results
    
    # Full tests
    # Test 3: Subagent Execution
    print("\n" + "🔹" * 40 + "\n")
    results["subagent"] = test_subagent_execution(model_name)
    
    # Test 4: Full Execution
    if agent:
        print("\n" + "🔹" * 40 + "\n")
        task = "How many paintings are in the database?"
        exec_result = test_agent_execution(agent, task)
        results["execution"] = exec_result is not None
    
    # Test 5: Streaming
    print("\n" + "🔹" * 40 + "\n")
    results["streaming"] = test_streaming_execution(model_name)
    
    # Test 6: Tool Wrapper
    print("\n" + "🔹" * 40 + "\n")
    tool = test_tool_wrapper(model_name)
    results["tool_wrapper"] = tool is not None
    
    # Summary
    print("\n" + "=" * 80)
    print("📋 TEST SUMMARY")
    print("=" * 80)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"   Passed: {passed}/{total}")
    print("-" * 40)
    for test, result in results.items():
        status = "✅" if result else "❌"
        print(f"   {status} {test}")
    
    return results


# ============================================================================
# EXAMPLE TASKS
# ============================================================================

EXAMPLE_TASKS = [
    # Simple database queries
    "How many paintings are in the database?",
    "What is the oldest painting in the database?",
    "How many paintings are there in each genre?",
    "List all art movements in the database",
    
    # Multi-step tasks
    "Find the 3 oldest Renaissance paintings and show their details",
    "What are the top 5 genres by painting count?",
    
    # Image analysis tasks
    "Find 2 Renaissance paintings and describe their visual content",
    "Analyze the colors in the oldest painting",
    
    # Plotting tasks
    "Create a bar chart showing paintings per genre",
]


def show_examples():
    """Show example tasks."""
    print("\n" + "=" * 80)
    print("📋 EXAMPLE TASKS")
    print("=" * 80)
    for i, task in enumerate(EXAMPLE_TASKS, 1):
        print(f"   {i}. {task}")
    print()


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="XP Agent Test Suite")
    parser.add_argument(
        "--model", "-m",
        default="gpt-4o-mini",
        help="LLM model to use (default: gpt-4o-mini)"
    )
    parser.add_argument(
        "--full", "-f",
        action="store_true",
        help="Run full test suite (including execution tests)"
    )
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Run quick tests only (building, factory)"
    )
    parser.add_argument(
        "--stream", "-s",
        action="store_true",
        help="Test streaming execution"
    )
    parser.add_argument(
        "--task", "-t",
        type=str,
        help="Custom task to execute"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare multiple models"
    )
    parser.add_argument(
        "--examples",
        action="store_true",
        help="Show example tasks"
    )
    
    args = parser.parse_args()
    
    if args.examples:
        show_examples()
        return
    
    if args.compare:
        test_model_comparison(args.task)
        return
    
    if args.stream:
        test_streaming_execution(args.model, args.task)
        return
    
    if args.task:
        # Run single task
        agent = test_agent_building(args.model)
        if agent:
            test_agent_execution(agent, args.task)
        return
    
    # Run test suite
    run_all_tests(args.model, full=args.full and not args.quick)


if __name__ == "__main__":
    main()

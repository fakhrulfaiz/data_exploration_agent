# image_qna_test.py - Test suite for image_qna_sub.py

"""
Test script for the enhanced image_qna_sub.py module.
Tests:
1. Device detection and GPU utilities
2. Tool building with different GPU configurations
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
# TEST 1: Device Detection
# ============================================================================

def test_device_detection():
    """Test GPU/device detection utilities."""
    print("=" * 80)
    print("TEST 1: Device Detection")
    print("=" * 80)
    
    from agent.image_qna_sub import get_device, get_memory_info
    
    device, device_info = get_device()
    print(f"Detected device: {device}")
    print(f"Device info: {device_info}")
    
    mem_info = get_memory_info()
    if mem_info:
        print(f"GPU Memory Info: {mem_info}")
    else:
        print("No GPU memory info available (CPU mode)")
    
    print("✅ Device detection test passed!\n")
    return device


# ============================================================================
# TEST 2: Tool Building with GPU Options
# ============================================================================

def test_tool_building(use_gpu: bool = None):
    """Test building the image QnA tool with different GPU configurations."""
    print("=" * 80)
    print(f"TEST 2: Tool Building (use_gpu={use_gpu})")
    print("=" * 80)
    
    from agent.image_qna_sub import build_image_qna_tool
    
    try:
        tool = build_image_qna_tool(use_gpu=use_gpu)
        print(f"Tool name: {tool.name}")
        print(f"Tool description: {tool.description[:100]}...")
        print("✅ Tool building test passed!\n")
        return tool
    except RuntimeError as e:
        print(f"❌ Expected error (GPU not available): {e}\n")
        return None


# ============================================================================
# TEST 3: Agent Building with Different LLMs
# ============================================================================

def test_agent_building(model_name: str = "gpt-4o", use_gpu: bool = None):
    """Test building the agent with different LLM models."""
    print("=" * 80)
    print(f"TEST 3: Agent Building (model={model_name}, use_gpu={use_gpu})")
    print("=" * 80)
    
    from agent.image_qna_sub import build_image_qna_agent
    
    try:
        agent = build_image_qna_agent(model_name=model_name, use_gpu=use_gpu)
        print(f"Agent type: {type(agent)}")
        print("✅ Agent building test passed!\n")
        return agent
    except Exception as e:
        print(f"❌ Error building agent: {e}\n")
        return None


# ============================================================================
# TEST 4: Full Agent Execution
# ============================================================================

def test_agent_execution(agent, task: str, images: list):
    """Test full agent execution with a sample task."""
    print("=" * 80)
    print("TEST 4: Full Agent Execution")
    print("=" * 80)
    print(f"Task: {task}")
    print(f"Images: {images}")
    print("-" * 80)
    
    # Prepare initial state
    initial_state = {
        "messages": [HumanMessage(content=task)],
        "original_task": task,
        "images_to_process": images,
        "images_processed": [],
        "analysis_records": [],
        "tools_complete": False
    }
    
    try:
        result = agent.invoke(initial_state)
        
        # Print results
        print("\n📊 Execution Results:")
        print("-" * 40)
        
        # Print messages
        print(f"\nTotal messages: {len(result.get('messages', []))}")
        for i, msg in enumerate(result.get("messages", [])):
            msg_type = type(msg).__name__
            content_preview = str(msg.content)[:200] if hasattr(msg, 'content') else str(msg)[:200]
            print(f"  [{i}] {msg_type}: {content_preview}...")
        
        # Print analysis records
        records = result.get("analysis_records", [])
        print(f"\nAnalysis records: {len(records)}")
        for record in records:
            if hasattr(record, 'to_string'):
                print(f"  - {record.to_string()}")
            else:
                print(f"  - {record}")
        
        # Print processed images
        print(f"\nImages processed: {result.get('images_processed', [])}")
        print(f"Tools complete: {result.get('tools_complete', False)}")
        
        print("\n✅ Agent execution test passed!\n")
        return result
        
    except Exception as e:
        print(f"❌ Error during execution: {e}\n")
        import traceback
        traceback.print_exc()
        return None


# ============================================================================
# TEST 5: Supervisor Tool Creation
# ============================================================================

def test_supervisor_tool(model_name: str = "gpt-4o", use_gpu: bool = None):
    """Test creating the image analysis tool for supervisor agents."""
    print("=" * 80)
    print(f"TEST 5: Supervisor Tool Creation (model={model_name})")
    print("=" * 80)
    
    from agent.image_qna_sub import create_image_analysis_tool_for_supervisor
    
    try:
        tool = create_image_analysis_tool_for_supervisor(
            model_name=model_name, 
            use_gpu=use_gpu
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
    use_gpu: bool = None,
    run_execution_test: bool = False,
    test_images: list = None,
    test_task: str = None
):
    """
    Run all tests for image_qna_sub.py.
    
    Args:
        model_name: LLM model to use for testing
        use_gpu: GPU configuration (None=auto, True=require, False=force CPU)
        run_execution_test: Whether to run the full agent execution test (takes time)
        test_images: List of image paths for execution test
        test_task: Task description for execution test
    """
    print("\n" + "🚀 " * 20)
    print("IMAGE QNA SUB TEST SUITE")
    print("🚀 " * 20 + "\n")
    
    # Test 1: Device detection
    device = test_device_detection()
    
    # Test 2: Tool building
    # Test with auto-detect
    tool = test_tool_building(use_gpu=None)
    
    # Test with CPU forced (if not already on CPU)
    if device != "cpu":
        test_tool_building(use_gpu=False)
    
    # Test 3: Agent building
    agent = test_agent_building(model_name=model_name, use_gpu=use_gpu)
    
    # Test 4: Full execution (optional - takes time and API calls)
    if run_execution_test and agent:
        if test_images is None:
            test_images = ["images/img_0.jpg", "images/img_1.jpg"]
        if test_task is None:
            test_task = "Analyze the art style and main subjects in each image."
        
        test_agent_execution(agent, test_task, test_images)
    else:
        print("=" * 80)
        print("TEST 4: Full Agent Execution - SKIPPED")
        print("(Set run_execution_test=True to enable)")
        print("=" * 80 + "\n")
    
    # Test 5: Supervisor tool (optional - creates new agent)
    # Uncomment to test:
    # test_supervisor_tool(model_name=model_name, use_gpu=use_gpu)
    
    print("\n" + "✅ " * 20)
    print("ALL TESTS COMPLETED")
    print("✅ " * 20 + "\n")


# ============================================================================
# QUICK TEST FUNCTIONS
# ============================================================================

def quick_test():
    """Quick test - just device detection and tool building."""
    test_device_detection()
    test_tool_building(use_gpu=None)


def full_test(model_name: str = "gpt-4o"):
    """Full test including agent execution."""
    run_all_tests(
        model_name=model_name,
        use_gpu=None,
        run_execution_test=True,
        test_images=["images/img_0.jpg", "images/img_1.jpg"],
        test_task="Analyze the art style and count the number of people in each painting."
    )


def test_specific_task(task: str, images: list, model_name: str = "gpt-4o"):
    """Test with a specific task and images."""
    from agent.image_qna_sub import build_image_qna_agent
    
    agent = build_image_qna_agent(model_name=model_name, use_gpu=None)
    return test_agent_execution(agent, task, images)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test image_qna_sub.py")
    parser.add_argument("--model", type=str, default="gpt-4o", help="LLM model name")
    parser.add_argument("--gpu", type=str, default="auto", choices=["auto", "true", "false"],
                       help="GPU usage: auto, true, or false")
    parser.add_argument("--full", action="store_true", help="Run full test including execution")
    parser.add_argument("--quick", action="store_true", help="Run quick test only")
    
    args = parser.parse_args()
    
    # Parse GPU option
    use_gpu = None if args.gpu == "auto" else (args.gpu == "true")
    
    if args.quick:
        quick_test()
    elif args.full:
        full_test(model_name=args.model)
    else:
        run_all_tests(
            model_name=args.model,
            use_gpu=use_gpu,
            run_execution_test=False
        )

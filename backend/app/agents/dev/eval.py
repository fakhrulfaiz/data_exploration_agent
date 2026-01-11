"""
Evaluation Script for XP Agent

This script reads tasks from complex_task.csv and evaluates the XP Agent
by running each task with a fresh checkpointer (memory) instance.

Usage:
    python eval.py
    python eval.py --output results.json
    python eval.py --limit 5  # Run only first 5 tasks
"""

import os
import sys
import csv
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agent.XpAgent import build_xp_agent

# Configuration
# MODEL_NAME = "gpt-4o"
# TASKS_FILE = Path(__file__).parent / "workspace" / "tasks" / "complex_task.csv"
MODEL_NAME = "gpt-4o-mini"
TASKS_FILE = Path(__file__).parent / "workspace" / "tasks" / "database_specific.csv"
OUTPUT_DIR = Path(__file__).parent / "workspace" / "outputs"
RESULTS_FILE = OUTPUT_DIR / f"eval_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def load_tasks(file_path: Path) -> List[str]:
    """
    Load tasks from CSV file.
    The CSV file is expected to have one task per line with no header.
    
    Args:
        file_path: Path to the CSV file containing tasks
        
    Returns:
        List of task strings
    """
    tasks = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0].strip():  # Skip empty rows
                tasks.append(row[0].strip())
    return tasks


def run_task_with_fresh_memory(
    task: str, 
    task_id: int,
    model_name: str = MODEL_NAME
) -> Dict[str, Any]:
    """
    Run a single task with a fresh checkpointer instance.
    
    Args:
        task: The task/query to execute
        task_id: Unique identifier for this task
        model_name: LLM model to use
        
    Returns:
        Dictionary containing task results and metadata
    """
    result = {
        "task_id": task_id,
        "task": task,
        "model": model_name,
        "start_time": datetime.now().isoformat(),
        "end_time": None,
        "duration_seconds": None,
        "success": False,
        "final_answer": None,
        "generated_files": [],
        "error": None,
        "step_results": [],
    }
    
    start_time = time.time()
    
    try:
        # Create fresh checkpointer for each task
        checkpointer = MemorySaver()
        
        # Build agent with fresh checkpointer
        agent = build_xp_agent(
            model_name=model_name,
            checkpointer=checkpointer
        )
        
        # Create unique thread_id for this task
        thread_id = f"eval_task_{task_id}_{int(time.time())}"
        
        # Initial state
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
        
        # Run the agent
        config = {"configurable": {"thread_id": thread_id}}
        final_state = agent.invoke(initial_state, config)
        
        # Extract results
        result["success"] = True
        result["final_answer"] = final_state.get("final_answer", "")
        result["generated_files"] = final_state.get("generated_files", [])
        
        # Serialize step results
        step_results = final_state.get("step_results", [])
        result["step_results"] = [
            {
                "step_number": sr.step_number,
                "success": sr.success,
                "result_content": sr.result_content[:1000] if sr.result_content else "",  # Truncate
                "output_file": sr.output_file,
                "error_message": sr.error_message
            }
            for sr in step_results
        ]
        
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        import traceback
        result["traceback"] = traceback.format_exc()
        
    finally:
        end_time = time.time()
        result["end_time"] = datetime.now().isoformat()
        result["duration_seconds"] = round(end_time - start_time, 2)
    
    return result


def run_evaluation(
    tasks: List[str],
    model_name: str = MODEL_NAME,
    limit: Optional[int] = None,
    verbose: bool = True
) -> List[Dict[str, Any]]:
    """
    Run evaluation on all tasks.
    
    Args:
        tasks: List of tasks to evaluate
        model_name: LLM model to use
        limit: Optional limit on number of tasks to run
        verbose: Whether to print progress
        
    Returns:
        List of result dictionaries
    """
    if limit:
        tasks = tasks[:limit]
    
    results = []
    total_tasks = len(tasks)
    
    print("=" * 80)
    print(f"🚀 Starting Evaluation")
    print(f"   Model: {model_name}")
    print(f"   Total Tasks: {total_tasks}")
    print("=" * 80)
    
    for idx, task in enumerate(tasks, start=1):
        print(f"\n{'='*60}")
        print(f"📋 Task {idx}/{total_tasks}")
        print(f"   Query: {task[:100]}{'...' if len(task) > 100 else ''}")
        print(f"{'='*60}")
        
        result = run_task_with_fresh_memory(task, idx, model_name)
        results.append(result)
        
        # Print summary
        status = "✅" if result["success"] else "❌"
        print(f"\n{status} Task {idx} completed in {result['duration_seconds']}s")
        
        if result["success"]:
            answer_preview = result["final_answer"][:200] if result["final_answer"] else "No answer"
            print(f"   Answer: {answer_preview}...")
            if result["generated_files"]:
                print(f"   Files: {result['generated_files']}")
        else:
            print(f"   Error: {result['error']}")
    
    return results


def save_results(results: List[Dict[str, Any]], output_path: Path):
    """
    Save evaluation results to JSON file.
    
    Args:
        results: List of result dictionaries
        output_path: Path to save the JSON file
    """
    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Calculate summary statistics
    total = len(results)
    successful = sum(1 for r in results if r["success"])
    failed = total - successful
    total_duration = sum(r["duration_seconds"] or 0 for r in results)
    avg_duration = total_duration / total if total > 0 else 0
    
    output = {
        "evaluation_metadata": {
            "timestamp": datetime.now().isoformat(),
            "model": MODEL_NAME,
            "total_tasks": total,
            "successful_tasks": successful,
            "failed_tasks": failed,
            "success_rate": round(successful / total * 100, 2) if total > 0 else 0,
            "total_duration_seconds": round(total_duration, 2),
            "average_duration_seconds": round(avg_duration, 2),
        },
        "results": results
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n📁 Results saved to: {output_path}")


def print_summary(results: List[Dict[str, Any]]):
    """Print evaluation summary."""
    total = len(results)
    successful = sum(1 for r in results if r["success"])
    failed = total - successful
    total_duration = sum(r["duration_seconds"] or 0 for r in results)
    
    print("\n" + "=" * 80)
    print("📊 EVALUATION SUMMARY")
    print("=" * 80)
    print(f"   Model: {MODEL_NAME}")
    print(f"   Total Tasks: {total}")
    print(f"   Successful: {successful} ({successful/total*100:.1f}%)")
    print(f"   Failed: {failed} ({failed/total*100:.1f}%)")
    print(f"   Total Duration: {total_duration:.2f}s")
    print(f"   Average Duration: {total_duration/total:.2f}s per task")
    print("=" * 80)
    
    # Print failed tasks
    if failed > 0:
        print("\n❌ Failed Tasks:")
        for r in results:
            if not r["success"]:
                print(f"   Task {r['task_id']}: {r['task'][:60]}...")
                print(f"      Error: {r['error'][:100]}...")


def main():
    """Main entry point."""
    # Initialize global model name if specified
    global MODEL_NAME
    
    parser = argparse.ArgumentParser(description="Evaluate XP Agent on complex tasks")
    parser.add_argument("--tasks", type=str, default=str(TASKS_FILE),
                       help="Path to tasks CSV file")
    parser.add_argument("--output", type=str, default=str(RESULTS_FILE),
                       help="Path to save results JSON")
    parser.add_argument("--limit", type=int, default=None,
                       help="Limit number of tasks to run")
    parser.add_argument("--model", type=str, default=MODEL_NAME,
                       help="LLM model to use")
    
    args = parser.parse_args()
    
    # Update global model name
    MODEL_NAME = args.model
    
    # Load tasks
    tasks_path = Path(args.tasks)
    if not tasks_path.exists():
        print(f"❌ Tasks file not found: {tasks_path}")
        sys.exit(1)
    
    tasks = load_tasks(tasks_path)
    print(f"📄 Loaded {len(tasks)} tasks from {tasks_path}")
    
    # Run evaluation
    results = run_evaluation(
        tasks=tasks,
        model_name=args.model,
        limit=args.limit,
        verbose=True
    )
    
    # Save results
    output_path = Path(args.output)
    save_results(results, output_path)
    
    # Print summary
    print_summary(results)
    
    print("\n✅ Evaluation complete!")


if __name__ == "__main__":
    main()

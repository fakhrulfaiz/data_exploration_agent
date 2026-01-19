
import json
import pathlib
import sys

def main():
    base_dir = pathlib.Path(__file__).parent
    
    # Input files
    results_file = base_dir / "outputs" / "rag_ab_test_20260118_063615.json"
    expected_file = base_dir / "expected_results.json"
    
    if not results_file.exists():
        print(f"Error: Results file not found at {results_file}")
        sys.exit(1)
        
    if not expected_file.exists():
        print(f"Error: Expected results file not found at {expected_file}")
        sys.exit(1)
        
    # Load data
    with open(results_file, "r", encoding="utf-8") as f:
        results_data = json.load(f)
        
    with open(expected_file, "r", encoding="utf-8") as f:
        expected_data = json.load(f)
        
    per_query_results = results_data.get("per_query_comparison", [])
    
    print("-" * 120)
    print(f"{'Query':<50} | {'Exp':<3} | {'With (S/T)':<10} | {'Without (S/T)':<12}")
    print("-" * 120)
    
    correct_steps_with = 0
    correct_tools_with = 0
    correct_all_with = 0
    
    correct_steps_without = 0
    correct_tools_without = 0
    correct_all_without = 0
    
    total = 0
    
    display_results = []
    
    for res in per_query_results:
        query = res["query"]
        expected = expected_data.get(query)
        if not expected:
            print(f"Warning: No expected data for query: {query}")
            continue
            
        expected_steps = expected["expected_steps"]
        expected_tools = expected["expected_tools"]
        
        # --- With Explainer ---
        steps_with = res["with_explainer"]["steps_generated"] if res["with_explainer"] else 0
        tools_with = res["with_explainer"]["suggested_tools"] if res["with_explainer"] else []
        
        step_match_with = (steps_with == expected_steps)
        # Use SET comparison for tools to ignore order
        tool_match_with = (set(tools_with) == set(expected_tools))
        
        if step_match_with: correct_steps_with += 1
        if tool_match_with: correct_tools_with += 1
        if step_match_with and tool_match_with: correct_all_with += 1
        
        # --- Without Explainer ---
        steps_without = res["without_explainer"]["steps_generated"] if res["without_explainer"] else 0
        tools_without = res["without_explainer"]["suggested_tools"] if res["without_explainer"] else []
        
        step_match_without = (steps_without == expected_steps)
        # Use SET comparison for tools to ignore order
        tool_match_without = (set(tools_without) == set(expected_tools))
        
        if step_match_without: correct_steps_without += 1
        if tool_match_without: correct_tools_without += 1
        if step_match_without and tool_match_without: correct_all_without += 1
        
        total += 1
        
        # Display Logic
        display_query = (query[:47] + "...") if len(query) > 47 else query
        
        # Format: S=✅/❌ T=✅/❌
        def fmt_check(is_step, is_tool):
            s = "✅" if is_step else "❌"
            t = "✅" if is_tool else "❌"
            return f"{s}/{t}"
            
        print(f"{display_query:<50} | {expected_steps:<3} | {fmt_check(step_match_with, tool_match_with):<10} | {fmt_check(step_match_without, tool_match_without):<12}")

    print("-" * 120)
    print(f"Total Queries: {total}")
    print("\nAccuracy Metrics (Strict: Steps AND Tools [Set] match):")
    if total > 0:
        print(f"WITH Explainer:    {correct_all_with}/{total} ({correct_all_with/total*100:.1f}%)")
        print(f"WITHOUT Explainer: {correct_all_without}/{total} ({correct_all_without/total*100:.1f}%)")
        
        print("\nPartial Accuracy:")
        print(f"Step Count Match:  With={correct_steps_with}/{total}  Without={correct_steps_without}/{total}")
        print(f"Tool Set Match:    With={correct_tools_with}/{total}  Without={correct_tools_without}/{total}")
    
    # Generate JSON Report
    report = {
        "metadata": {
            "total_queries": total,
            "overall_accuracy_with": f"{correct_all_with/total*100:.1f}%" if total else "0.0%",
            "overall_accuracy_without": f"{correct_all_without/total*100:.1f}%" if total else "0.0%",
            "metrics": {
                "with_explainer": {"steps_correct": correct_steps_with, "tools_correct": correct_tools_with, "all_correct": correct_all_with},
                "without_explainer": {"steps_correct": correct_steps_without, "tools_correct": correct_tools_without, "all_correct": correct_all_without}
            }
        },
        "query_details": []
    }
    
    for res in per_query_results:
        query = res["query"]
        expected = expected_data.get(query)
        if not expected: continue
        
        steps_with = res["with_explainer"]["steps_generated"] if res["with_explainer"] else 0
        tools_with = res["with_explainer"]["suggested_tools"] if res["with_explainer"] else []
        
        steps_without = res["without_explainer"]["steps_generated"] if res["without_explainer"] else 0
        tools_without = res["without_explainer"]["suggested_tools"] if res["without_explainer"] else []
        
        report["query_details"].append({
            "query": query,
            "expected_steps": expected["expected_steps"],
            "expected_tools": expected["expected_tools"],
            "with_explainer": {
                "steps": steps_with,
                "tools": tools_with,
                "matches_steps": (steps_with == expected["expected_steps"]),
                "matches_tools": (set(tools_with) == set(expected["expected_tools"]))
            },
            "without_explainer": {
                "steps": steps_without,
                "tools": tools_without,
                "matches_steps": (steps_without == expected["expected_steps"]),
                "matches_tools": (set(tools_without) == set(expected["expected_tools"]))
            }
        })
        
    output_json_file = base_dir / "outputs" / "rag_analysis_report.json"
    with open(output_json_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        
    print(f"\nJSON report saved to: {output_json_file}")

if __name__ == "__main__":
    main()

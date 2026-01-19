"""
RAG Effectiveness Evaluation - A/B Test

Tests 10 queries TWICE:
- First run: use_explainer=True (with RAG)
- Second run: use_explainer=False (without RAG)

Compares: Number of steps generated in dynamic plan
Result: Shows if RAG helps generate better plans
"""

import asyncio
import httpx
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

# Configuration
BASE_URL = "http://localhost:8080"  # Nginx on port 80, proxies /api to backend
AUTH_TOKEN = "Bearer eyJhbGciOiJIUzI1NiIsImtpZCI6IjhKR25ua1VlQnBidHdlSE8iLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL2J1cmd2Y3NpZ2l5Ym9lemRmb2d1LnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiJmZjU5Zjg3Yy1hNzc3LTQ5MDQtYWUxOS1iYTkyZWRhYWQ3NzIiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzY4NjgxMDM0LCJpYXQiOjE3Njg2Nzc0MzQsImVtYWlsIjoiZmFraHJ1bGZhaXoyMDFAZ21haWwuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJlbWFpbCI6ImZha2hydWxmYWl6MjAxQGdtYWlsLmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJwaG9uZV92ZXJpZmllZCI6ZmFsc2UsInN1YiI6ImZmNTlmODdjLWE3NzctNDkwNC1hZTE5LWJhOTJlZGFhZDc3MiJ9LCJyb2xlIjoiYXV0aGVudGljYXRlZCIsImFhbCI6ImFhbDEiLCJhbXIiOlt7Im1ldGhvZCI6InBhc3N3b3JkIiwidGltZXN0YW1wIjoxNzY4Njc3NDM0fV0sInNlc3Npb25faWQiOiI2MWU4MjU4Zi03NjkxLTRkZWQtYWNjMS01ODVlOWJmYmU1OTAiLCJpc19hbm9ueW1vdXMiOmZhbHNlfQ.XEQ2ucpAepBefgk4SAAQgAVPCJRR0499mjxzQwUgHcc"

HEADERS = {
    "Authorization": AUTH_TOKEN,
    "Content-Type": "application/json",
    "Accept": "text/event-stream",  # Explicitly accept SSE
    "Cache-Control": "no-cache",      # Prevent buffering
    "X-Accel-Buffering": "no"         # Explicit Nginx no-buffering
}

# 10 Test queries (will be tested twice: with and without explainer)
TEST_QUERIES = [
    "What is the oldest impressionist artwork in the database?",
    "What is the newest painting in the database?",
    "What is the movement of the painting that depicts the highest number of swords?",
    "What is the movement of the painting that depicts the highest number of babies?",
    "What is the genre of the oldest painting in the database?",
    "What is the genre of the newest painting in the database?",
    "What is depicted on the oldest Renaissance painting in the database?",
    "What is depicted on the oldest religious artwork in the database?",
    "Plot the year of the oldest painting per movement",
    "Plot the year of the oldest painting per genre",
    "Plot the number of paintings that depict War for each year",
    "Plot the number of paintings that depict War for each century",
    "Plot the number of paintings for each year",
    "Plot the number of paintings for each century",
    "Plot the lowest number of swords depicted in each year",
    "Plot the lowest number of swords depicted in each genre",
    "Get the number of paintings that depict Fruit for each century",
    "Get the number of paintings that depict Animals for each movement",
    "Get the number of paintings for each year",
    "Get the number of paintings for each century",
    "Get the highest number of swords depicted in paintings of each movement",
    "Get the highest number of swords depicted in paintings of each genre",
    "Get the century of the newest painting per movement",
    "Get the century of the newest painting per genre"
]


class RAGEffectivenessEvaluator:
    """A/B test: Compare plan generation with and without explainer"""
    
    def __init__(self):
        self.results = []
        self.threads_created = []
        
        # Debug file for plans
        output_dir = Path(__file__).parent / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        self.debug_plan_file = output_dir / f"debug_plans_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        # Write header
        with open(self.debug_plan_file, "w", encoding="utf-8") as f:
            f.write("# RAG Evaluation - Generated Plans\n\n")
    
    async def test_query(self, query: str, use_explainer: bool, test_id: str) -> Optional[Dict]:
        """Test single query with explainer on/off by consuming SSE stream"""
        # Use longer timeout and force HTTP/1.1
        async with httpx.AsyncClient(timeout=120.0, http2=False) as client:
            try:
                # Step 0: Create Conversation Thread explicitly to satisfy DB constraints
                # We can't use 'test_id' (dev1) as the DB ID, so we get a real UUID
                create_response = await client.post(
                    f"{BASE_URL}/api/v1/conversation",
                    headers=HEADERS,
                    json={"title": f"RAG Test {test_id}"}
                )
                
                if create_response.status_code != 200:
                    return {
                        "query": query,
                        "use_explainer": use_explainer,
                        "thread_id": None,
                        "success": False,
                        "error": f"Create thread failed: {create_response.status_code} - {create_response.text}"
                    }
                
                # Get the REAL thread_id from the backend
                create_data = create_response.json()
                real_thread_id = create_data.get("data", {}).get("thread_id")
                
                if not real_thread_id:
                     return {
                        "query": query,
                        "use_explainer": use_explainer,
                        "thread_id": None,
                        "success": False,
                        "error": "No thread_id returned from create endpoint"
                    }
                
                self.threads_created.append(real_thread_id)

                # Step 1: Initialize graph run (POST /start)
                start_response = await client.post(
                    f"{BASE_URL}/api/v1/graph/stream/start",
                    headers=HEADERS,
                    json={
                        "human_request": query,
                        "use_planning": True,
                        "use_explainer": use_explainer,
                        "thread_id": real_thread_id
                    }
                )
                
                if start_response.status_code != 200:
                    return {
                        "query": query,
                        "use_explainer": use_explainer,
                        "thread_id": real_thread_id,
                        "success": False,
                        "error": f"Start failed: {start_response.status_code} - {start_response.text}"
                    }

                dynamic_plan = None
                
                # Give backend a moment to initialize the stream handler
                await asyncio.sleep(1.0)

                plan_json = ""
                plan_found = False
                
                # Step 2: Consume SSE stream (GET /stream/{real_thread_id})
                print(f"  → DEBUG: Stream initialized for {test_id} (using DB ID: {real_thread_id})...")
                
                async with client.stream(
                    "GET",
                    f"{BASE_URL}/api/v1/graph/stream/{real_thread_id}",
                    headers=HEADERS
                ) as response:
                    
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        
                        try:
                            # Parse SSE data - we only process 'data:' lines here
                            data = json.loads(line[6:])
                            
                            # DEBUG: Verify event content
                            # Note: The 'event: ...' line is skipped, so we rely on payload content
                            event_type_in_payload = data.get("type")
                            block_type = data.get("block_type")
                            
                            if block_type or event_type_in_payload:
                               print(f"    Payload: block_type={block_type}, type={event_type_in_payload}")
                               pass

                            # Accumulate plan content
                            # PlanHandler sends: {"block_type": "plan", "content": "..."}
                            if block_type == "plan":
                                content_data = data.get("content", {})
                                # In chunked mode, content might be directly in 'content' field or inside 'dynamic_plan'
                                # Based on handler, it's in 'content' field of the inner JSON
                                chunk = data.get("content", "")
                                if isinstance(chunk, dict):
                                    # Fallback if it somehow sends dict
                                    chunk = chunk.get("dynamic_plan", "") or chunk.get("plan", "")
                                
                                # If it's a string, append it
                                if isinstance(chunk, str):
                                    plan_json += chunk
                                    plan_found = True
                            
                            # If we started finding plan and then switch to another block type, stop
                            # But we must be careful: streaming might interleave? No, usually sequential.
                            # Step 1: Plan chunks. Step 2: Text chunks.
                            elif plan_found and block_type and block_type != "plan":
                                # Found a new block type (e.g. "text"), so plan is definitely done
                                break

                            # Check for stream completion/error
                            if event_type_in_payload == "status" and data.get("status") in ["finished", "error"]:
                                if data.get("status") == "error":
                                    return {
                                        # ... error return ...
                                        "query": query,
                                        "use_explainer": use_explainer,
                                        "thread_id": real_thread_id,
                                        "success": False,
                                        "error": f"Stream error: {data.get('error')}"
                                    }
                                break
                        
                        except json.JSONDecodeError:
                            continue

                if not plan_found or not plan_json:
                    return {
                        "query": query,
                        "use_explainer": use_explainer,
                        "thread_id": real_thread_id,
                        "success": False,
                        "error": "No dynamic_plan in stream"
                    }
                
                # Save captured plan to debug file
                try:
                    with open(self.debug_plan_file, "a", encoding="utf-8") as f:
                        f.write(f"## Query: {query}\n")
                        f.write(f"**Condition**: {'With Explainer' if use_explainer else 'Without Explainer'}\n")
                        f.write(f"**Thread ID**: {real_thread_id}\n")
                        f.write("```markdown\n")
                        f.write(plan_json)
                        f.write("\n```\n")
                        f.write("-" * 50 + "\n\n")
                except Exception as e:
                    print(f"Failed to write to debug file: {e}")

                # Check if we have valid content
                import re
                
                # Check if we have valid content
                if not plan_json or len(plan_json) < 10:
                     return {
                        "query": query,
                        "use_explainer": use_explainer,
                        "thread_id": real_thread_id,
                        "success": False,
                        "error": f"Plan content too short or empty: {plan_json}"
                    }

                # Extract steps count
                # Look for **Step X**: patterns
                step_matches = re.findall(r"\*\*Step\s+\d+\*\*:", plan_json)
                steps_generated = len(step_matches)
                
                if steps_generated == 0:
                     return {
                        "query": query,
                        "use_explainer": use_explainer,
                        "thread_id": real_thread_id,
                        "success": False,
                        "error": f"0 steps found in markdown plan. Content: {plan_json[:100]}..."
                    }

                # Extract suggested tools
                # Look for numbered list items under Tool Options like "  1. tool_name:"
                # Pattern: space(s) + digit + dot + space + tool_name + colon
                tool_matches = re.findall(r"\s+\d+\.\s+([a-zA-Z0-9_]+):", plan_json)
                # Preserve order while deduplicating
                suggested_tools = list(dict.fromkeys(tool_matches))
                
                if not suggested_tools:
                    suggested_tools = ["unknown_tool"]

                return {
                    "query": query,
                    "use_explainer": use_explainer,
                    "thread_id": real_thread_id,
                    "steps_generated": steps_generated,
                    "suggested_tools": suggested_tools,
                    "success": True
                }

                return {
                    "query": query,
                    "use_explainer": use_explainer,
                    "thread_id": real_thread_id,
                    "steps_generated": steps_generated,
                    "suggested_tools": suggested_tools,
                    "success": True
                }

            except Exception as e:
                return {
                    "query": query,
                    "use_explainer": use_explainer,
                    "thread_id": test_id, # Use test_id here as real_thread_id might not be available
                    "success": False,
                    "error": f"Exception: {str(e)}"
                }
    
    async def cleanup_threads(self) -> Dict:
        """Delete all created threads"""
        cleanup_results = {
            "total_threads": len(self.threads_created),
            "deleted": 0,
            "failed": 0
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for thread_id in self.threads_created:
                try:
                    response = await client.delete(
                        f"{BASE_URL}/api/v1/conversation/{thread_id}",
                        headers=HEADERS
                    )
                    
                    if response.status_code in [200, 404]:
                        cleanup_results["deleted"] += 1
                    else:
                        cleanup_results["failed"] += 1
                        
                except Exception:
                    cleanup_results["failed"] += 1
        
        return cleanup_results
    
    async def run_ab_test(self, test_cleanup: bool = True) -> Dict:
        """Run A/B test: 10 queries × 2 conditions = 20 tests"""
        start_time = datetime.now()
        
        print(f"Starting RAG A/B Test: {len(TEST_QUERIES)} queries × 2 conditions = {len(TEST_QUERIES) * 2} tests")
        
        # Test each query twice: with and without explainer
        test_counter = 1
        for i, query in enumerate(TEST_QUERIES, 1):
            print(f"[{i}/{len(TEST_QUERIES)}] Testing: {query[:60]}...")
            
            # Test WITH explainer (RAG ON)
            print(f"  → WITH explainer...", end=" ")
            result_with = await self.test_query(query, use_explainer=True, test_id=f"dev{test_counter}")
            test_counter += 1
            if result_with:
                self.results.append(result_with)
                if result_with.get('success'):
                    print(f"✓ {result_with.get('steps_generated', 0)} steps")
                else:
                    print(f"✗ Failed: {result_with.get('error', 'Unknown error')}")
            else:
                print("✗ Failed: No response")
            
            # Test WITHOUT explainer (RAG OFF)
            print(f"  → WITHOUT explainer...", end=" ")
            result_without = await self.test_query(query, use_explainer=False, test_id=f"dev{test_counter}")
            test_counter += 1
            if result_without:
                self.results.append(result_without)
                if result_without.get('success'):
                    print(f"✓ {result_without.get('steps_generated', 0)} steps")
                else:
                    print(f"✗ Failed: {result_without.get('error', 'Unknown error')}")
            else:
                print("✗ Failed: No response")
        
        # Split results by condition
        with_explainer = [r for r in self.results if r.get("use_explainer") and r.get("success")]
        without_explainer = [r for r in self.results if not r.get("use_explainer") and r.get("success")]
        
        print(f"\nBuilding comparison for {len(TEST_QUERIES)} queries...")
        
        # Build per-query comparison
        per_query_results = []
        for query in TEST_QUERIES:
            with_result = next((r for r in with_explainer if r["query"] == query), None)
            without_result = next((r for r in without_explainer if r["query"] == query), None)
            
            per_query_results.append({
                "query": query,
                "with_explainer": {
                    "steps_generated": with_result["steps_generated"] if with_result else 0,
                    "suggested_tools": with_result["suggested_tools"] if with_result else [],
                    "thread_id": with_result.get("thread_id", "") if with_result else ""
                },
                "without_explainer": {
                    "steps_generated": without_result["steps_generated"] if without_result else 0,
                    "suggested_tools": without_result["suggested_tools"] if without_result else [],
                    "thread_id": without_result.get("thread_id", "") if without_result else ""
                },
                "difference": (with_result["steps_generated"] if with_result else 0) - (without_result["steps_generated"] if without_result else 0)
            })
        
        # Calculate summary stats
        avg_steps_with = sum(r["with_explainer"]["steps_generated"] for r in per_query_results) / len(per_query_results) if per_query_results else 0
        avg_steps_without = sum(r["without_explainer"]["steps_generated"] for r in per_query_results) / len(per_query_results) if per_query_results else 0
        
        improvement = 0.0
        if avg_steps_without > 0:
            improvement = ((avg_steps_with - avg_steps_without) / avg_steps_without) * 100
        
        # Cleanup
        cleanup_results = None
        if test_cleanup:
            print(f"\nCleaning up {len(self.threads_created)} test threads...")
            cleanup_results = await self.cleanup_threads()
            print(f"Deleted: {cleanup_results['deleted']}, Failed: {cleanup_results['failed']}")
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Show overall status
        successful_tests = len(with_explainer) + len(without_explainer)
        total_tests = len(self.results)
        
        if successful_tests == 0:
            print(f"\n❌ TEST FAILED: 0/{total_tests} tests succeeded")
        elif successful_tests < total_tests:
            print(f"\n⚠️  PARTIAL SUCCESS: {successful_tests}/{total_tests} tests succeeded")
        else:
            print(f"\n✅ ALL TESTS PASSED: {successful_tests}/{total_tests} succeeded")
        
        print(f"Test completed in {duration:.1f}s")
        
        return {
            "metadata": {
                "timestamp": start_time.isoformat(),
                "duration_seconds": duration,
                "total_tests": len(self.results),
                "queries_tested": len(TEST_QUERIES)
            },
            "summary": {
                "accuracy_with_explainer": f"{accuracy_with:.1f}%",
                "accuracy_without_explainer": f"{accuracy_without:.1f}%",
                "total_queries": total_queries
            },
            "per_query_comparison": per_query_results,
            "cleanup": cleanup_results
        }



async def main():
    """Run RAG effectiveness A/B test"""
    evaluator = RAGEffectivenessEvaluator()
    print(f"Starting RAG A/B Test: {len(TEST_QUERIES)} queries × 2 conditions = {len(TEST_QUERIES)*2} tests")
    
    try:
        results = await evaluator.run_ab_test(test_cleanup=False) # Manual cleanup below
        
        # Save to JSON file
        output_dir = Path(__file__).parent / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f"rag_ab_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        

        
        # Output summary to console (minimal)
        summary = {
            "status": "complete",
            "output_file": str(output_file),
            "total_tests": results["metadata"]["total_tests"],
            "queries_tested": results["metadata"]["queries_tested"],
            "queries_tested": results["metadata"]["queries_tested"],
            "accuracy_with": results["summary"]["accuracy_with_explainer"],
            "accuracy_without": results["summary"]["accuracy_without_explainer"],
        }
        
        print(json.dumps(summary, indent=2))

    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user!")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
    finally:
        # Guarantee cleanup
        if evaluator.threads_created:
            print(f"\nCleaning up {len(evaluator.threads_created)} test threads...")
            cleanup_results = await evaluator.cleanup_threads()
            print(f"Cleanup summary: {cleanup_results}")
            
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass # Handled inside main

#!/usr/bin/env python
"""Script to run tests with various configurations."""

import sys
import subprocess
from pathlib import Path


def run_command(cmd: list[str]) -> int:
    """Run a command and return exit code."""
    print(f"\n{'='*60}")
    print(f"Running: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    
    result = subprocess.run(cmd)
    return result.returncode


def main():
    """Main test runner."""
    if len(sys.argv) < 2:
        print("Usage: python run_tests.py [command]")
        print("\nAvailable commands:")
        print("  all          - Run all tests")
        print("  unit         - Run only unit tests")
        print("  integration  - Run only integration tests")
        print("  coverage     - Run tests with coverage report")
        print("  fast         - Run tests excluding slow ones")
        print("  agent        - Run agent endpoint tests")
        print("  conversation - Run conversation endpoint tests")
        print("  data         - Run data endpoint tests")
        print("  graph        - Run graph endpoint tests")
        print("  streaming    - Run streaming graph endpoint tests")
        print("  verbose      - Run all tests with verbose output")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    # Base pytest command
    base_cmd = ["pytest"]
    
    # Command mappings
    commands = {
        "all": base_cmd,
        "unit": base_cmd + ["-m", "unit"],
        "integration": base_cmd + ["-m", "integration"],
        "coverage": base_cmd + ["--cov=app", "--cov-report=html", "--cov-report=term"],
        "fast": base_cmd + ["-m", "not slow"],
        "agent": base_cmd + ["tests/test_agent_endpoints.py"],
        "conversation": base_cmd + ["tests/test_conversation_endpoints.py"],
        "data": base_cmd + ["tests/test_data_endpoints.py"],
        "graph": base_cmd + ["tests/test_graph_endpoints.py"],
        "streaming": base_cmd + ["tests/test_streaming_graph_endpoints.py"],
        "verbose": base_cmd + ["-v"],
    }
    
    if command not in commands:
        print(f"Unknown command: {command}")
        print("Run without arguments to see available commands.")
        sys.exit(1)
    
    # Run the command
    exit_code = run_command(commands[command])
    
    # Print summary
    print(f"\n{'='*60}")
    if exit_code == 0:
        print("✅ Tests passed!")
    else:
        print("❌ Tests failed!")
    print(f"{'='*60}\n")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

"""
Script to generate LangGraph visualization for the data exploration agent.
Run this inside the Docker container to create agent_graph.png
"""
import os
import sys

# Add the backend directory to the path
sys.path.insert(0, '/app/backend')

from app.agents.data_exploration_agent import DataExplorationAgent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

def main():
    print("Initializing agent...")
    
    # Create a simple LLM instance
    llm = ChatOpenAI(model='gpt-4o-mini', temperature=0)
    
    # Create agent with memory checkpointer (no database needed for graph generation)
    # Use a dummy database path - we just need the graph structure
    db_path = '/app/backend/data/Chinook.db'
    
    try:
        agent = DataExplorationAgent(
            llm=llm,
            db_path=db_path,
            use_postgres_checkpointer=False,
            checkpointer=MemorySaver()
        )
        
        print("✅ Agent initialized successfully!")
        print(f"📊 Graph visualization saved to: /app/backend/logs/agent_graph.png")
        print("   (Accessible on host at: backend/logs/agent_graph.png)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nNote: Graph structure can still be generated even if database is not accessible.")
        print("The graph visualization shows the agent's workflow, not database content.")

if __name__ == "__main__":
    main()

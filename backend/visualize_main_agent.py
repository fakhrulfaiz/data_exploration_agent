"""
Simple script to visualize the MainAgent graph.
Run this from the backend directory with: python -m visualize_main_agent
"""

if __name__ == "__main__":
    import os
    os.environ.setdefault("OPENAI_API_KEY", "dummy-key-for-visualization")
    
    from langchain_openai import ChatOpenAI
    from app.agents.main_agent import MainAgent
    
    # Initialize with dummy LLM (just for graph structure)
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key="dummy")
    
    # Use a placeholder database path
    db_path = "dummy.db"
    
    print("Initializing MainAgent for visualization...")
    
    try:
        agent = MainAgent(
            llm=llm,
            db_path=db_path,
            use_postgres_checkpointer=False
        )
        
        print("\n✅ MainAgent initialized successfully!")
        print(f"📁 Graph visualization saved to: {agent.logs_dir}/main_agent_graph.png")
        
        # Print graph structure
        print("\n" + "="*60)
        print("MAIN AGENT GRAPH STRUCTURE")
        print("="*60)
        
        graph = agent.graph.get_graph()
        
        print("\n📍 Nodes:")
        for node in graph.nodes:
            print(f"   • {node}")
        
        print("\n� Edges:")
        for edge in graph.edges:
            print(f"   • {edge.source} → {edge.target}")
        
        print("\n" + "="*60)
        print("\n✨ Visualization complete!")
        print(f"\n💡 Check the PNG file at: {agent.logs_dir}/main_agent_graph.png")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

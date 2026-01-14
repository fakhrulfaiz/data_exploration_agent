import os
import sys
import re
from pathlib import Path
from langchain_core.documents import Document
from typing import List, Dict, Any
import json

# Add backend to path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.rag_service import get_rag_service

def parse_thought_process_patterns(file_path: str) -> List[Document]:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    documents = []
    
    # Split by category sections
    category_pattern = r'### (Category \d+: [^\n]+)\n\n\*\*Pattern\*\*: "([^"]+)"'
    categories = re.finditer(category_pattern, content)
    
    for match in categories:
        category_name = match.group(1)
        pattern_description = match.group(2)
        
        # Extract the section content
        start_pos = match.end()
        # Find next category or end of file
        next_match = re.search(r'### Category \d+:', content[start_pos:])
        if next_match:
            end_pos = start_pos + next_match.start()
        else:
            # Look for next major section
            next_section = re.search(r'\n## [^#]', content[start_pos:])
            if next_section:
                end_pos = start_pos + next_section.start()
            else:
                end_pos = len(content)
        
        section_content = content[start_pos:end_pos]
        
        # Extract examples
        example_queries = re.findall(r'- "([^"]+)"', section_content)
        
        # Extract thought process template
        template_match = re.search(r'\*\*Thought Process Template\*\*:\n```\n(.*?)\n```', section_content, re.DOTALL)
        template = template_match.group(1) if template_match else ""
        
        # Determine complexity based on category
        complexity_map = {
            "Category 1": "simple",
            "Category 2": "medium",
            "Category 3": "medium",
            "Category 4": "complex",
            "Category 5": "complex",
            "Category 6": "simple"
        }
        complexity = complexity_map.get(category_name.split(':')[0], "medium")
        
        # Create a document for each example query
        for example_query in example_queries:
            doc = Document(
                page_content=template,  # The template is the main content
                metadata={
                    "pattern_type": category_name,
                    "pattern_description": pattern_description,
                    "complexity": complexity,
                    "example_query": example_query,
                    "template": template,
                    "source": "thought_process_patterns.md"
                }
            )
            documents.append(doc)
    
    # Also extract the concrete example thought processes
    example_section_pattern = r'### (Example \d+: "[^"]+").*?\*\*Thought Process\*\*:\n```\n(.*?)\n```'
    examples = re.finditer(example_section_pattern, content, re.DOTALL)
    
    for match in examples:
        example_title = match.group(1)
        thought_process = match.group(2)
        
        # Extract query from title
        query_match = re.search(r'"([^"]+)"', example_title)
        example_query = query_match.group(1) if query_match else ""
        
        # Determine pattern type and complexity based on query
        if "oldest" in example_query.lower() or "newest" in example_query.lower():
            if "depicted" in example_query.lower():
                pattern_type = "Category 2: Visual Analysis with Metadata Filtering"
                complexity = "medium"
            else:
                pattern_type = "Category 1: Simple Metadata Retrieval"
                complexity = "simple"
        elif "plot" in example_query.lower():
            if "depict" in example_query.lower():
                pattern_type = "Category 4: Visual Counting with Aggregation"
                complexity = "complex"
            else:
                pattern_type = "Category 3: Temporal Aggregation & Visualization"
                complexity = "medium"
        elif "highest" in example_query.lower() or "lowest" in example_query.lower():
            if "depict" in example_query.lower():
                pattern_type = "Category 5: Visual Extremes with Grouping"
                complexity = "complex"
            else:
                pattern_type = "Category 6: Simple Aggregation"
                complexity = "simple"
        elif "depict" in example_query.lower() and ("number" in example_query.lower() or "count" in example_query.lower()):
            pattern_type = "Category: Multi-step Visual Analysis"
            complexity = "complex"
        else:
            pattern_type = "Category 6: Simple Aggregation"
            complexity = "simple"
        
        doc = Document(
            page_content=thought_process,  # The actual thought process
            metadata={
                "pattern_type": pattern_type,
                "complexity": complexity,
                "example_query": example_query,
                "template": "",  # Concrete examples don't have templates
                "source": "thought_process_patterns.md",
                "is_concrete_example": True
            }
        )
        documents.append(doc)
    
    return documents


def parse_finalizer_response_patterns(file_path: str) -> List[Document]:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    documents = []
    
    # Extract pattern categories (e.g., "### 1. Data Retrieval & Display")
    category_pattern = r'### (\d+\. [^\n]+)\n\n#### ([^\n]+)\n\*\*Execution Context\*\*: ([^\n]+)'
    categories = re.finditer(category_pattern, content)
    
    for match in categories:
        category_name = match.group(1)
        subcategory = match.group(2)
        execution_context = match.group(3)
        
        # Extract the section content
        start_pos = match.end()
        # Find next subcategory or category
        next_match = re.search(r'####|###', content[start_pos:])
        if next_match:
            end_pos = start_pos + next_match.start()
        else:
            end_pos = len(content)
        
        section_content = content[start_pos:end_pos]
        
        # Extract response pattern
        response_match = re.search(r'\*\*Response Pattern\*\*:\n(.*?)\n\n\*\*Actions\*\*:', section_content, re.DOTALL)
        response_pattern = response_match.group(1).strip() if response_match else ""
        
        # Extract actions
        actions_match = re.search(r'\*\*Actions\*\*:\n(.*?)(?:\n\n\*\*|$)', section_content, re.DOTALL)
        actions_text = actions_match.group(1).strip() if actions_match else ""
        
        # Parse action rules
        action_rules = {}
        if "export_dataframe:" in actions_text:
            export_match = re.search(r'export_dataframe: (.+)', actions_text)
            if export_match:
                action_rules["export_dataframe"] = export_match.group(1).strip()
        if "download_images:" in actions_text:
            download_match = re.search(r'download_images: (.+)', actions_text)
            if download_match:
                action_rules["download_images"] = download_match.group(1).strip()
        if "next_queries:" in actions_text:
            action_rules["next_queries"] = "always_provide"
        
        example_match = re.search(r'\*\*Example\*\*:\n(.*?)(?:\n---|\n###|$)', section_content, re.DOTALL)
        example = example_match.group(1).strip() if example_match else ""
        
        # Create document
        # Include execution context in page_content for semantic search matches
        content_text = f"Execution Context: {execution_context}\n\nResponse Pattern:\n{response_pattern}"
        if example:
            content_text += f"\n\nExample:\n{example}"
        
        doc = Document(
            page_content=content_text,
            metadata={
                "pattern_category": category_name,
                "subcategory": subcategory,
                "execution_context": execution_context,
                "action_rules": json.dumps(action_rules), 
                "source": "finalizer_response_patterns.md"
            }
        )
        documents.append(doc)
    
    return documents





def initialize_rag_kb():
    """Initialize the RAG knowledge base with thought process patterns and finalizer response patterns."""
    print("=" * 60)
    print("Initializing RAG Knowledge Base")
    print("=" * 60)
    
    # Get RAG service
    rag_service = get_rag_service()
    
    # Get knowledge base directory
    kb_dir = backend_dir / "app" / "knowledge_base"
    thought_patterns_file = kb_dir / "thought_process_patterns.md"
    finalizer_patterns_file = kb_dir / "finalizer_response_patterns.md"
    
    if not thought_patterns_file.exists():
        print(f"Error: {thought_patterns_file} not found!")
        return
    
    # Parse thought process patterns
    print(f"\nParsing {thought_patterns_file.name}...")
    thought_docs = parse_thought_process_patterns(str(thought_patterns_file))
    print(f"   ✓ Extracted {len(thought_docs)} pattern examples")
    
    # Clear existing collection and add new documents
    print(f"\nInitializing thought_process_kb collection...")
    try:
        # Delete existing collection
        rag_service.thought_process_kb.delete_collection()
        print("   ✓ Cleared existing collection")
    except Exception as e:
        print(f"   ℹ No existing collection to clear: {e}")
    
    # Recreate collection
    from langchain_chroma import Chroma
    rag_service.thought_process_kb = Chroma(
        collection_name="thought_process_kb",
        embedding_function=rag_service.embeddings,
        persist_directory=f"{rag_service.persist_directory}/thought_process_kb"
    )
    
    # Add documents
    if thought_docs:
        rag_service.thought_process_kb.add_documents(thought_docs)
        print(f"   ✓ Added {len(thought_docs)} documents to thought_process_kb")
    
    # Parse and load finalizer response patterns
    finalizer_docs = []
    if finalizer_patterns_file.exists():
        print(f"\nParsing {finalizer_patterns_file.name}...")
        finalizer_docs = parse_finalizer_response_patterns(str(finalizer_patterns_file))
        print(f"   ✓ Extracted {len(finalizer_docs)} response patterns")
        
        # Clear existing finalizer collection
        print(f"\n🔄 Initializing finalizer_response_kb collection...")
        try:
            rag_service.finalizer_response_kb.delete_collection()
            print("   ✓ Cleared existing collection")
        except Exception as e:
            print(f"   ℹ No existing collection to clear: {e}")
        
        # Recreate collection
        rag_service.finalizer_response_kb = Chroma(
            collection_name="finalizer_response_kb",
            embedding_function=rag_service.embeddings,
            persist_directory=f"{rag_service.persist_directory}/finalizer_response_kb"
        )
        
        # Add documents
        if finalizer_docs:
            rag_service.finalizer_response_kb.add_documents(finalizer_docs)
            print(f"   ✓ Added {len(finalizer_docs)} documents to finalizer_response_kb")
    else:
        print(f"\n⚠ Warning: {finalizer_patterns_file} not found, skipping finalizer KB initialization")
    
    # Summary
    print("\n" + "=" * 60)
    print("RAG Initialization Complete!")
    print("=" * 60)
    print(f"\nCollections initialized:")
    print(f"  • thought_process_kb: {len(thought_docs)} documents")
    print(f"  • finalizer_response_kb: {len(finalizer_docs)} documents")
    print(f"  • feedback_kb: (populated dynamically from user feedback)")
    print("\nReady to use!")


if __name__ == "__main__":
    initialize_rag_kb()


import os
import re
import logging
from pathlib import Path
from langchain_core.documents import Document
from app.services.rag_service import get_rag_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_tool_selection_md(file_path: str) -> list[Document]:
 
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by tool sections (## tool_name)
    tool_sections = re.split(r'\n## ([a-z_]+)\n', content)[1:]  # Skip intro
    
    documents = []
    
    # Process pairs of (tool_name, tool_content)
    for i in range(0, len(tool_sections), 2):
        tool_name = tool_sections[i]
        tool_content = tool_sections[i + 1] if i + 1 < len(tool_sections) else ""
        
        # Extract sections
        category_match = re.search(r'\*\*Category:\*\* (.+)', tool_content)
        description_match = re.search(r'\*\*Description:\*\* (.+)', tool_content)
        
        when_to_use_match = re.search(r'### When to Use\n(.+?)(?=\n###|$)', tool_content, re.DOTALL)
        when_not_to_use_match = re.search(r'### When NOT to Use\n(.+?)(?=\n###|$)', tool_content, re.DOTALL)
        alternatives_match = re.search(r'### Alternatives\n(.+?)(?=\n###|$)', tool_content, re.DOTALL)
        
        # Extract example scenarios
        scenarios = re.findall(r'#### Scenario \d+: (.+?)\n\*\*User Query:\*\* "(.+?)"\n\*\*Why This Tool:\*\*\n(.+?)\n\*\*Explanation Template:\*\*\n"(.+?)"', tool_content, re.DOTALL)
        
        # Create searchable content
        page_content = f"""
Tool: {tool_name}
Category: {category_match.group(1) if category_match else 'Unknown'}
Description: {description_match.group(1) if description_match else ''}

When to Use:
{when_to_use_match.group(1).strip() if when_to_use_match else ''}

When NOT to Use:
{when_not_to_use_match.group(1).strip() if when_not_to_use_match else ''}

Alternatives:
{alternatives_match.group(1).strip() if alternatives_match else ''}

Example Scenarios:
{chr(10).join([f"- {scenario[0]}: {scenario[1]}" for scenario in scenarios])}
"""
        
        # Create metadata
        metadata = {
            "tool_name": tool_name,
            "category": category_match.group(1) if category_match else "Unknown",
            "description": description_match.group(1) if description_match else "",
            "type": "tool_knowledge"
        }
        
        documents.append(Document(page_content=page_content, metadata=metadata))
        
        # Also create documents for each example scenario (for better retrieval)
        for scenario_name, user_query, reasoning, explanation_template in scenarios:
            scenario_content = f"""
Tool: {tool_name}
Scenario: {scenario_name}
User Query: {user_query}
Reasoning: {reasoning.strip()}
Explanation: {explanation_template}
"""
            scenario_metadata = {
                "tool_name": tool_name,
                "scenario": scenario_name,
                "user_query": user_query,
                "type": "tool_example"
            }
            documents.append(Document(page_content=scenario_content, metadata=scenario_metadata))
    
    logger.info(f"Parsed {len(documents)} documents from tool_selection.md")
    return documents


def parse_error_explanations_md(file_path: str) -> list[Document]:
    """
    Parse error_explanations.md and create documents for each error type.
    
    Returns:
        List of Document objects for the error KB
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by error sections (## error_type)
    error_sections = re.split(r'\n## ([a-z_]+)\n', content)[1:]  # Skip intro
    
    documents = []
    
    # Process pairs of (error_type, error_content)
    for i in range(0, len(error_sections), 2):
        error_type = error_sections[i]
        error_content = error_sections[i + 1] if i + 1 < len(error_sections) else ""
        
        # Extract sections
        tool_match = re.search(r'\*\*Tool:\*\* (.+)', error_content)
        pattern_match = re.search(r'\*\*Error Pattern:\*\* `(.+?)`', error_content)
        
        explanation_match = re.search(r'### User-Friendly Explanation\n(.+?)(?=\n###|$)', error_content, re.DOTALL)
        actions_match = re.search(r'### Suggested Actions\n(.+?)(?=\n###|$)', error_content, re.DOTALL)
        example_match = re.search(r'### Example\n(.+?)(?=\n##|$)', error_content, re.DOTALL)
        
        # Create searchable content
        page_content = f"""
Error Type: {error_type}
Tool: {tool_match.group(1) if tool_match else 'any'}
Pattern: {pattern_match.group(1) if pattern_match else ''}

User-Friendly Explanation:
{explanation_match.group(1).strip() if explanation_match else ''}

Suggested Actions:
{actions_match.group(1).strip() if actions_match else ''}

Example:
{example_match.group(1).strip() if example_match else ''}
"""
        
        # Extract suggested actions as list
        suggested_actions = []
        if actions_match:
            actions_text = actions_match.group(1)
            suggested_actions = [line.strip('- ').strip() for line in actions_text.split('\n') if line.strip().startswith('-')]
        
        # Create metadata
        metadata = {
            "error_type": error_type,
            "tool_name": tool_match.group(1) if tool_match else "any",
            "error_pattern": pattern_match.group(1) if pattern_match else "",
            "user_friendly_explanation": explanation_match.group(1).strip() if explanation_match else "",
            "suggested_actions": suggested_actions,
            "type": "error_knowledge"
        }
        
        documents.append(Document(page_content=page_content, metadata=metadata))
    
    logger.info(f"Parsed {len(documents)} documents from error_explanations.md")
    return documents


def parse_domain_knowledge_md(file_path: str) -> list[Document]:
    """
    Parse domain_knowledge.md and create documents for each topic.
    
    Returns:
        List of Document objects for the domain KB
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by category sections (## Category: ...)
    category_sections = re.split(r'\n## Category: (.+?)\n', content)[1:]  # Skip intro
    
    documents = []
    
    # Process pairs of (category, category_content)
    for i in range(0, len(category_sections), 2):
        category = category_sections[i]
        category_content = category_sections[i + 1] if i + 1 < len(category_sections) else ""
        
        # Split by topics within category (### Topic: ...)
        topic_sections = re.split(r'\n### Topic: (.+?)\n', category_content)
        
        # Process pairs of (topic, topic_content)
        for j in range(1, len(topic_sections), 2):
            topic = topic_sections[j]
            topic_content = topic_sections[j + 1] if j + 1 < len(topic_sections) else ""
            
            # Extract content
            content_match = re.search(r'\*\*Content:\*\*\n(.+?)(?=\n###|$)', topic_content, re.DOTALL)
            
            # Extract examples
            examples = re.findall(r'\*\*Scenario:\*\* (.+?)\n\*\*Recommendation:\*\* (.+?)\n\*\*Reasoning:\*\* (.+?)(?=\n\n---|\n\*\*Scenario|\n##|$)', topic_content, re.DOTALL)
            
            # Create searchable content
            page_content = f"""
Category: {category}
Topic: {topic}

Content:
{content_match.group(1).strip() if content_match else ''}

Examples:
{chr(10).join([f"- Scenario: {ex[0]}{chr(10)}  Recommendation: {ex[1]}{chr(10)}  Reasoning: {ex[2].strip()}" for ex in examples])}
"""
            
            # Create metadata
            metadata = {
                "category": category,
                "topic": topic,
                "content": content_match.group(1).strip() if content_match else "",
                "examples": [
                    {
                        "scenario": ex[0],
                        "recommendation": ex[1],
                        "reasoning": ex[2].strip()
                    }
                    for ex in examples
                ],
                "type": "domain_knowledge"
            }
            
            documents.append(Document(page_content=page_content, metadata=metadata))
    
    logger.info(f"Parsed {len(documents)} documents from domain_knowledge.md")
    return documents


def parse_explanation_patterns_dir(dir_path: Path) -> list[Document]:
    documents = []
    
    if not dir_path.exists() or not dir_path.is_dir():
        logger.warning(f"Explanation patterns directory not found: {dir_path}")
        return []
    
    # Iterate through all .md files in the directory
    for file_path in dir_path.glob("*.md"):
        logger.info(f"Parsing explanation pattern file: {file_path.name}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Extract layer name from the file content (# Layer: ...) or filename
        layer_match = re.search(r'# Layer: (.+?)\n', content)
        layer_name_clean = layer_match.group(1).strip() if layer_match else file_path.stem.capitalize()
        
        # Extract layer key from filename
        layer_key = file_path.stem.lower()
        
        # Split by patterns (### Pattern X: ...)
        pattern_sections = re.split(r'\n### Pattern \d+: (.+?)\n', content)
        
        # Check if there is introductory text before the first pattern
        start_index = 1 if len(pattern_sections) > 1 else 0
        
        # Process pairs of (pattern_name, pattern_content)
        for j in range(start_index, len(pattern_sections), 2):
            pattern_name = pattern_sections[j]
            pattern_content = pattern_sections[j + 1] if j + 1 < len(pattern_sections) else ""
            
            # Extract content
            context_match = re.search(r'\*\*Context:\*\* (.+?)(\n|$)', pattern_content)
            template_match = re.search(r'\*\*Template:\*\* "(.+?)"', pattern_content)
            
            # Extract example
            example_match = re.search(r'\*\*Example:\*\*\n(.+?)(?=\n###|$)', pattern_content, re.DOTALL)
            
            # Extract sub-components of example if possible
            example_text = example_match.group(1).strip() if example_match else ""
            user_ex_match = re.search(r'- \*\*User:\*\* "(.+?)"', example_text)
            explanation_ex_match = re.search(r'- \*\*Explanation:\*\* "(.+?)"', example_text)
            
            user_ex = user_ex_match.group(1) if user_ex_match else ""
            explanation_ex = explanation_ex_match.group(1) if explanation_ex_match else ""
            
            # Create searchable content
            page_content = f"""
Layer: {layer_name_clean}
Pattern: {pattern_name}
Context: {context_match.group(1) if context_match else ''}

Template:
"{template_match.group(1) if template_match else ''}"

Example:
User: "{user_ex}"
Explanation: "{explanation_ex}"
"""
            
            # Create metadata
            metadata = {
                "layer": layer_key,
                "layer_full": layer_name_clean,
                "pattern_name": pattern_name,
                "context": context_match.group(1) if context_match else "",
                "template": template_match.group(1) if template_match else "",
                "example": {
                    "user": user_ex,
                    "explanation": explanation_ex
                },
                "type": "explanation_pattern",
                "source_file": file_path.name
            }
            
            documents.append(Document(page_content=page_content, metadata=metadata))
            
    logger.info(f"Total parsed {len(documents)} documents from explanation_patterns directory")
    return documents


def initialize_knowledge_bases():
    """
    Initialize all RAG knowledge bases from markdown files.
    """
    logger.info("Starting RAG knowledge base initialization from markdown files...")
    
    # Get paths to markdown files
    backend_dir = Path(__file__).parent.parent.parent
    kb_dir = backend_dir / "knowledge_base"
    
    tool_selection_path = kb_dir / "tool_selection.md"
    error_explanations_path = kb_dir / "error_explanations.md"
    domain_knowledge_path = kb_dir / "domain_knowledge.md"
    explanation_patterns_dir = kb_dir / "explanation_patterns"
    
    # Check if files exist
    if not tool_selection_path.exists():
        logger.error(f"Tool selection file not found: {tool_selection_path}")
        return
    if not error_explanations_path.exists():
        logger.error(f"Error explanations file not found: {error_explanations_path}")
        return
    if not domain_knowledge_path.exists():
        logger.error(f"Domain knowledge file not found: {domain_knowledge_path}")
        return
    if not explanation_patterns_dir.exists():
        logger.error(f"Explanation patterns directory not found: {explanation_patterns_dir}")
        return
    
    # Get RAG service
    rag_service = get_rag_service()
    
    # Parse and load tool selection knowledge
    logger.info("Loading tool selection knowledge...")
    tool_docs = parse_tool_selection_md(str(tool_selection_path))
    rag_service.tool_kb.add_documents(tool_docs)
    logger.info(f"✓ Loaded {len(tool_docs)} tool knowledge documents")
    
    # Parse and load error explanations
    logger.info("Loading error explanations...")
    error_docs = parse_error_explanations_md(str(error_explanations_path))
    rag_service.error_kb.add_documents(error_docs)
    logger.info(f"✓ Loaded {len(error_docs)} error explanation documents")
    
    # Parse and load domain knowledge
    logger.info("Loading domain knowledge...")
    domain_docs = parse_domain_knowledge_md(str(domain_knowledge_path))
    rag_service.domain_kb.add_documents(domain_docs)
    logger.info(f"✓ Loaded {len(domain_docs)} domain knowledge documents")
    
    # Parse and load explanation patterns
    logger.info("Loading explanation patterns from directory...")
    pattern_docs = parse_explanation_patterns_dir(explanation_patterns_dir)
    rag_service.explanation_kb.add_documents(pattern_docs)
    logger.info(f"✓ Loaded {len(pattern_docs)} explanation pattern documents")
    
    logger.info("=" * 60)
    logger.info("RAG knowledge base initialization complete!")
    logger.info(f"Total documents loaded: {len(tool_docs) + len(error_docs) + len(domain_docs) + len(pattern_docs)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    initialize_knowledge_bases()

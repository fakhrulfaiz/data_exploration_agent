# Test Syntax

## Xp Agent (Main agent)

```python
# Quick test (factory + building only)
python test/xp_agent_test.py --quick

# Full test suite
python test/xp_agent_test.py --full

# Test with specific model
python test/xp_agent_test.py --model gpt-4o --full

# Run custom task
python test/xp_agent_test.py --task "How many paintings are there?"

# Test streaming
python test/xp_agent_test.py --stream

# Compare models
python test/xp_agent_test.py --compare

# Show example tasks
python test/xp_agent_test.py --examples
```

## Data Exploration SubAgent (wrapped as Tools)

```python
# Quick test (no API calls)
python test/data_exploration_test.py --quick

# Full test with execution
python test/data_exploration_test.py --full

# With different model
python test/data_exploration_test.py --model claude-3-5-sonnet-20241022 --full

# Streaming test
python test/data_exploration_test.py --stream

# Custom task
python test/data_exploration_test.py --task "List all painting movements"

# List example tasks
python test/data_exploration_test.py --examples
```

## Image QnA SubAgent (wrapped as Tools)

```python
# Quick test (device detection + tool building only)
python test/image_qna_test.py --quick

# Standard test (no execution, no API calls)
python test/image_qna_test.py

# Full test including agent execution (uses API)
python test/image_qna_test.py --full

# With different model
python test/image_qna_test.py --model claude-3-5-sonnet-20241022 --full

# Force CPU
python test/image_qna_test.py --gpu false
```

## Data Plotting SubAgent (wrapped as Tools)

```python
# Quick test (no API calls)
python test/data_plotting_test.py --quick

# Full test with execution
python test/data_plotting_test.py --full

# With specific file
python test/data_plotting_test.py --full --file outputs/genre_counts.csv

# Custom task
python test/data_plotting_test.py --task "Create pie chart" --file test_data.csv

# List available CSV files
python test/data_plotting_test.py --list-files
```

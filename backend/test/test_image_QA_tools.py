import pytest
from PIL import Image
from unittest.mock import MagicMock

from app.agents.tools.image_QA_tools import ImageQATool
from app.agents.tools.custom_toolkit import VisualQA

# Define a fixture to share the model across tests
@pytest.fixture(scope="module")
def vqa_tester():
    return VisualQA()

# Helper to create a dummy image in memory
@pytest.fixture
def dummy_image(tmp_path):
    img_path = tmp_path / "test_image.jpg"
    img = Image.new('RGB', (224, 224), color='red')
    img.save(img_path)
    return str(img_path)

# --- THE TESTS ---

def test_initialization(vqa_tester):
    """Check if model and processor are loaded correctly."""
    assert vqa_tester.model is not None
    assert vqa_tester.processor is not None

def test_answer_questions_batching(vqa_tester, dummy_image):
    """Test if the batching logic and return length are correct."""
    # Arrange: 3 images, batch_size of 2 (forces two loops)
    image_paths = [dummy_image] * 3
    query = "What is in the image?"
    
    # Act
    results = vqa_tester.answer_questions(image_paths, query, batch_size=2)
    
    # Assert
    assert isinstance(results, list)
    assert len(results) == 3  # Should return one answer per image
    assert all(isinstance(res, str) for res in results)

def test_empty_input(vqa_tester):
    """Edge case: what happens with no images?"""
    results = vqa_tester.answer_questions([], "query")
    assert results == []

# Testing the Image QA Tool wrapper for VQA model
def test_image_qa_tool_logic():
    """
    Test that the tool correctly formats paths, calls the model, 
    and merges the results back into the context.
    """
    mock_vqa = MagicMock()
    
    # simulate the model returning two different answers
    expected_answers = ["a fluffy cat", "a red hydrant"]
    mock_vqa.answer_questions.return_value = expected_answers
    
    # Initialize tool with the fake model
    tool = ImageQATool(vqa=mock_vqa)
    
    # Input data
    test_question = "What is in this?"
    test_context = [
        {"img_path": "img1.jpg"},
        {"img_path": "img2.jpg"}
    ]

    # Run the tool
    results = tool._run(question=test_question, context=test_context)

    # A. Check if the model was called with the right data
    # This verifies the tool added the prefix to the paths correctly
    mock_vqa.answer_questions.assert_called_once()
    called_paths, called_query = mock_vqa.answer_questions.call_args[0]
    
    # If your IMAGE_PATH is "images/", it checks if it became "images/img1.jpg"
    assert "img1.jpg" in called_paths[0]
    assert called_query == test_question

    # B. Check if the output is correctly structured
    assert len(results) == 2
    assert results[0]["question_answer"] == "a fluffy cat"
    assert results[1]["question_answer"] == "a red hydrant"
    
    # C. Check if the original context keys are still there
    assert results[0]["img_path"] == "img1.jpg"

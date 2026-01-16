import gradio as gr
import uuid
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Define workspace directories
WORKSPACE_DIR = Path(__file__).parent / "workspace"
PLOT_DIR = WORKSPACE_DIR / "plot"
OUTPUTS_DIR = WORKSPACE_DIR / "outputs"

# Add agent directory to path
sys.path.append(str(Path(__file__).parent / "agent"))

# Import from XpAgent (the latest supervisor implementation)
from agent.XpAgent import build_xp_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

# Initialize the LangGraph agent with checkpointer (once at module level)
print("Initializing XpAgent...")
checkpointer = MemorySaver()
agent = build_xp_agent(checkpointer=checkpointer)
print("XpAgent initialized successfully!")


def create_thread_config(thread_id: str) -> dict:
    """Create a configuration dictionary for a specific thread."""
    return {"configurable": {"thread_id": thread_id}}


# Global session storage (for persistence across requests)
# Key: session_id, Value: {"thread_id": uuid}
session_storage = {}


def respond(
    message: str,
    history: list[dict[str, str]],
    session_id: str,
):
    """
    Respond function for Gradio ChatInterface with LangGraph agent integration.

    This function handles:
    - Session management with unique thread_id per user
    - Streaming responses from the LangGraph agent
    - Detection of interrupts (agent pauses for approval)

    Args:
        message: User's input message
        history: Chat history (managed by Gradio)
        session_id: Unique session identifier from gr.State

    Yields:
        str: Streaming response content from the agent
    """
    # ============================================================
    # 1. SESSION INITIALIZATION - Generate or retrieve thread_id
    # ============================================================
    # Initialize session_id if None
    if session_id is None or session_id == "":
        session_id = str(uuid.uuid4())
        print(f"🆕 New session_id created: {session_id}")

    # Get or create thread_id for this session
    if session_id not in session_storage:
        thread_id = str(uuid.uuid4())
        session_storage[session_id] = {"thread_id": thread_id}
        print(f"🆕 New thread_id created: {thread_id}")
    else:
        thread_id = session_storage[session_id]["thread_id"]
        print(f"📌 Using existing thread_id: {thread_id}")

    # Create configuration for this thread
    config = create_thread_config(thread_id)

    # ============================================================
    # 2. STATE INSPECTION - Check if agent is at interrupt_for_replan
    # ============================================================
    try:
        current_state = agent.get_state(config)

        # Only block if specifically at interrupt_for_replan node
        if current_state.next and "interrupt_for_replan" in current_state.next:
            print(f"⏸️  Agent is at interrupt_for_replan - waiting for approval.")
            print(f"   User should use Approve/Reject buttons in the popup.")
            yield "⚠️ **Agent needs your approval to proceed with replanning.** Please use the Approve/Reject buttons in the popup."
            return

    except Exception as e:
        print(f"⚠️  Error getting state: {e}")

    # ============================================================
    # 3. STREAMING LOOP - Stream response from agent
    # ============================================================
    print(f"▶️  Starting agent stream for new query...")
    response = ""

    try:
        # Simple message passing - the agent handles context internally via checkpointer
        initial_state = {
            "messages": [{"role": "user", "content": message}],
        }
        
        for chunk in agent.stream(
            initial_state,
            config=config,
            stream_mode="values"
        ):
            # Extract the last message from the chunk
            if "messages" in chunk and len(chunk["messages"]) > 0:
                last_message = chunk["messages"][-1]

                # Check if message has content attribute
                if hasattr(last_message, 'content') and last_message.content:
                    response = last_message.content
                    yield response

        # After streaming completes, check if agent is now at interrupt_for_replan
        print(f"✅ Stream completed.")
        final_state = agent.get_state(config)

        if final_state.next and "interrupt_for_replan" in final_state.next:
            print(f"🔔 Agent reached interrupt_for_replan! Modal will appear.")
            # Yield a special message to indicate interrupt - this will trigger the modal check
            yield response + "\n\n⏸️ **Agent paused - awaiting your approval...**"
        elif final_state.next:
            print(f"⏸️ Agent paused at: {final_state.next}")
        else:
            print(f"✅ Agent completed successfully")

    except Exception as e:
        error_msg = f"❌ Error during agent execution: {str(e)}"
        print(error_msg)
        yield error_msg


def check_interrupt_status(session_id: str):
    """
    Check if the agent is at the interrupt_for_replan node and waiting for approval.

    Only shows the modal when specifically at the 'interrupt_for_replan' node.

    Args:
        session_id: Current session identifier

    Returns:
        tuple: (is_interrupted: bool, interrupt_data: dict, modal_visible: bool, question: str)
    """
    if not session_id or session_id not in session_storage:
        return False, {}, gr.update(visible=False), ""

    thread_id = session_storage[session_id]["thread_id"]
    config = create_thread_config(thread_id)

    try:
        current_state = agent.get_state(config)

        # Check if agent is paused at interrupt_for_replan node specifically
        if current_state.next and "interrupt_for_replan" in current_state.next:
            print(f"🔔 Replan interrupt detected! Next nodes: {current_state.next}")

            # Default question for replanning
            question = "Do you want to proceed with replanning?"
            interrupt_data = {"question": question}

            # Try to extract the actual question from the interrupt data
            if hasattr(current_state, 'tasks') and current_state.tasks:
                for task in current_state.tasks:
                    if hasattr(task, 'interrupts') and task.interrupts:
                        for interrupt_info in task.interrupts:
                            if hasattr(interrupt_info, 'value') and isinstance(interrupt_info.value, dict):
                                interrupt_data = interrupt_info.value
                                question = interrupt_data.get("question", question)
                                print(f"   Extracted question: {question}")
                                break

            print(f"   Showing modal with question: {question}")
            return True, interrupt_data, gr.update(visible=True), question
        else:
            # Not at interrupt_for_replan - hide modal
            return False, {}, gr.update(visible=False), ""

    except Exception as e:
        print(f"⚠️  Error checking interrupt status: {e}")
        import traceback
        traceback.print_exc()
        return False, {}, gr.update(visible=False), ""


def handle_approval(session_id: str, approved: bool, current_history: list):
    """
    Handle user's approval/rejection of the interrupt.

    Args:
        session_id: Current session identifier
        approved: Whether user approved (True) or rejected (False)
        current_history: Current chat history

    Returns:
        tuple: (updated_history, modal_visible, status_message)
    """
    if not session_id or session_id not in session_storage:
        return current_history, gr.update(visible=False), "⚠️ No active session"

    thread_id = session_storage[session_id]["thread_id"]
    config = create_thread_config(thread_id)

    decision = "approved" if approved else "rejected"
    print(f"{'✅' if approved else '❌'} User {decision} the action")

    # Add user's decision to chat history
    decision_msg = f"{'✅ Approved' if approved else '❌ Rejected'}"
    current_history.append({
        "role": "user",
        "content": decision_msg
    })

    try:
        # Resume the agent with the approval decision
        response = ""
        for chunk in agent.stream(
            Command(resume=approved),
            config=config,
            stream_mode="values"
        ):
            if "messages" in chunk and len(chunk["messages"]) > 0:
                last_message = chunk["messages"][-1]
                if hasattr(last_message, 'content') and last_message.content:
                    response = last_message.content

        # Add agent's response to history
        if response:
            current_history.append({
                "role": "assistant",
                "content": response
            })

        status = f"✅ Action {decision} - continuing..." if approved else f"❌ Action {decision}"

        return current_history, gr.update(visible=False), status

    except Exception as e:
        error_msg = f"❌ Error handling approval: {str(e)}"
        print(error_msg)
        current_history.append({
            "role": "assistant",
            "content": error_msg
        })
        return current_history, gr.update(visible=False), "⚠️ Error occurred"


def reset_conversation(session_id: str):
    """
    Reset the conversation by clearing the session from storage.
    This will generate a new thread_id on the next message.

    Args:
        session_id: Current session identifier

    Returns:
        tuple: (new_session_id, status_message)
    """
    print(f"🔄 Resetting conversation for session: {session_id}")

    # Remove old session from storage
    if session_id and session_id in session_storage:
        del session_storage[session_id]
        print(f"   Deleted thread_id for session: {session_id}")

    # Generate new session_id
    new_session_id = str(uuid.uuid4())
    print(f"   New session_id: {new_session_id}")

    return new_session_id, "🆕 New session started — Ready for your questions!"


def get_agent_status(session_id: str):
    """
    Get the current status of the agent for display.

    Args:
        session_id: Current session identifier

    Returns:
        str: Status message
    """
    if not session_id or session_id not in session_storage:
        return "🆕 Ready to start — Send a message to begin!"

    thread_id = session_storage[session_id]["thread_id"]
    config = create_thread_config(thread_id)

    try:
        current_state = agent.get_state(config)
        if current_state.next and "interrupt_for_replan" in current_state.next:
            return f"⏸️ Waiting for approval — Please respond to the popup"
        elif current_state.next:
            return f"🔄 Processing... | Step: {', '.join(current_state.next)}"
        else:
            return f"✅ Ready | Session: {session_id[:8]}..."
    except Exception as e:
        return f"⚠️ Status unavailable: {str(e)}"


def get_plot_images():
    """
    Get all plot images from the workspace/plot directory, sorted by modification time.
    
    Returns:
        list: List of tuples (image_path, caption) sorted by most recent first
    """
    if not PLOT_DIR.exists():
        PLOT_DIR.mkdir(parents=True, exist_ok=True)
        return []
    
    # Get all PNG files in the plot directory
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    images = []
    
    for file_path in PLOT_DIR.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in image_extensions:
            # Get modification time
            mod_time = file_path.stat().st_mtime
            # Create caption with filename and timestamp
            from datetime import datetime
            timestamp = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M:%S")
            caption = f"{file_path.stem} ({timestamp})"
            images.append((str(file_path), mod_time, caption))
    
    # Sort by modification time (most recent first)
    images.sort(key=lambda x: x[1], reverse=True)
    
    # Return as list of (path, caption) tuples for Gradio Gallery
    return [(img[0], img[2]) for img in images]


def refresh_plots():
    """
    Refresh the plot gallery with latest images.
    
    Returns:
        list: Updated list of plot images
    """
    return get_plot_images()


def get_output_files():
    """
    Get all CSV output files from the workspace/outputs directory, sorted by modification time.
    
    Returns:
        list: List of filenames sorted by most recent first
    """
    if not OUTPUTS_DIR.exists():
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        return []
    
    csv_files = []
    for file_path in OUTPUTS_DIR.iterdir():
        if file_path.is_file() and file_path.suffix.lower() == '.csv':
            mod_time = file_path.stat().st_mtime
            csv_files.append((file_path.name, mod_time))
    
    # Sort by modification time (most recent first)
    csv_files.sort(key=lambda x: x[1], reverse=True)
    
    return [f[0] for f in csv_files]


def load_csv_file(filename: str):
    """
    Load a CSV file and return its content as a pandas DataFrame.
    
    Args:
        filename: Name of the CSV file to load
        
    Returns:
        tuple: (DataFrame or None, status message)
    """
    import pandas as pd
    
    if not filename or filename.strip() == "":
        return None, "📭 Enter a filename to display its contents."
    
    filename = filename.strip()
    
    # Add .csv extension if not present
    if not filename.lower().endswith('.csv'):
        filename = filename + '.csv'
    
    file_path = OUTPUTS_DIR / filename
    
    if not file_path.exists():
        available = get_output_files()
        available_str = ", ".join(available[:5]) if available else "None"
        return None, f"❌ File '{filename}' not found. Available files: {available_str}{'...' if len(available) > 5 else ''}"
    
    try:
        df = pd.read_csv(file_path)
        return df, f"✅ Loaded '{filename}' ({len(df)} rows, {len(df.columns)} columns)"
    except Exception as e:
        return None, f"❌ Error loading '{filename}': {str(e)}"


# ============================================================
# GRADIO UI SETUP
# ============================================================

"""
LangGraph v2 + Gradio Integration with Human-in-the-Loop (HITL)

This interface integrates the redesigned LangGraph supervisor agent 
with interrupt capabilities into a Gradio ChatInterface for multi-user deployment.

Features:
- Session-based state management with unique thread_id per user
- Interrupt handling for replan approval (HITL)
- Streaming responses from LangGraph agent
- Reset functionality to start fresh conversations
- Clean, modern UI design
"""

# Custom CSS for a polished look
CUSTOM_CSS = """
/* Main container styling */
.gradio-container {
    max-width: 1200px !important;
    margin: auto !important;
}

/* Header styling */
.header-container {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 1.5rem;
    border-radius: 12px;
    margin-bottom: 1rem;
    color: white;
}

.header-container h1 {
    margin: 0 !important;
    color: white !important;
}

.header-container p {
    margin: 0.5rem 0 0 0 !important;
    opacity: 0.9;
}

/* Status bar styling */
.status-bar {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    padding: 0.75rem 1rem;
}

/* Chat container */
.chatbot-container {
    border: 1px solid #e0e0e0 !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
}

/* ============================================
   MODERN INTERRUPT MODAL STYLING
   ============================================ */

/* Modal backdrop overlay */
.modal-backdrop {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    background: rgba(0, 0, 0, 0.6) !important;
    backdrop-filter: blur(4px) !important;
    z-index: 999 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}

/* Modal container */
.interrupt-modal {
    position: fixed !important;
    top: 50% !important;
    left: 50% !important;
    transform: translate(-50%, -50%) !important;
    z-index: 1000 !important;
    background: linear-gradient(145deg, #ffffff 0%, #f8f9ff 100%) !important;
    padding: 0 !important;
    border-radius: 20px !important;
    box-shadow: 
        0 25px 50px -12px rgba(0, 0, 0, 0.25),
        0 0 0 1px rgba(102, 126, 234, 0.1),
        inset 0 1px 0 rgba(255, 255, 255, 0.8) !important;
    max-width: 440px !important;
    width: 90% !important;
    overflow: hidden !important;
    animation: modalSlideIn 0.3s ease-out !important;
}

@keyframes modalSlideIn {
    from {
        opacity: 0;
        transform: translate(-50%, -48%) scale(0.96);
    }
    to {
        opacity: 1;
        transform: translate(-50%, -50%) scale(1);
    }
}

/* Modal header with gradient */
.modal-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    padding: 1.5rem 1.75rem !important;
    text-align: center !important;
}

.modal-header h2 {
    color: white !important;
    margin: 0 !important;
    font-size: 1.25rem !important;
    font-weight: 600 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 0.5rem !important;
}

/* Modal body */
.modal-body {
    padding: 1.75rem !important;
    background: white !important;
}

.modal-body p {
    color: #4a5568 !important;
    font-size: 0.95rem !important;
    line-height: 1.6 !important;
    margin: 0 0 1rem 0 !important;
}

/* Question/Reason box */
.modal-reason {
    background: linear-gradient(135deg, #f7f8ff 0%, #eef1ff 100%) !important;
    border: 1px solid rgba(102, 126, 234, 0.2) !important;
    border-radius: 12px !important;
    padding: 1rem 1.25rem !important;
    margin: 1rem 0 !important;
}

.modal-reason p {
    color: #5a67d8 !important;
    font-weight: 500 !important;
    margin: 0 !important;
    font-size: 0.9rem !important;
}

/* Modal footer with buttons */
.modal-footer {
    padding: 0 1.75rem 1.75rem 1.75rem !important;
    background: white !important;
    display: flex !important;
    gap: 0.75rem !important;
}

/* Button base styling */
.modal-btn {
    flex: 1 !important;
    padding: 0.875rem 1.5rem !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    border: none !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 0.5rem !important;
}

/* Approve button */
.approve-btn {
    background: linear-gradient(135deg, #48bb78 0%, #38a169 100%) !important;
    color: white !important;
    box-shadow: 0 4px 14px rgba(72, 187, 120, 0.35) !important;
}

.approve-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(72, 187, 120, 0.45) !important;
}

/* Reject button */
.reject-btn {
    background: linear-gradient(135deg, #fc8181 0%, #f56565 100%) !important;
    color: white !important;
    box-shadow: 0 4px 14px rgba(245, 101, 101, 0.35) !important;
}

.reject-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(245, 101, 101, 0.45) !important;
}

/* Pulse animation for the icon */
.pulse-icon {
    animation: pulse 2s infinite !important;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}

/* Hide default Gradio group styling */
.interrupt-modal > .gr-group {
    border: none !important;
    background: transparent !important;
    padding: 0 !important;
}

/* ============================================
   OTHER BUTTON STYLING
   ============================================ */

.primary-btn {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    transition: transform 0.2s, box-shadow 0.2s !important;
}

.primary-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
}

.danger-btn {
    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
}

.reset-btn {
    background: #6c757d !important;
    border: none !important;
    color: white !important;
}

.check-btn {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 500 !important;
}

/* Feature cards */
.feature-badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    background: rgba(102, 126, 234, 0.1);
    color: #667eea;
    border-radius: 20px;
    font-size: 0.85rem;
    margin: 0.25rem;
}

/* ============================================
   PLOT GALLERY SECTION
   ============================================ */

.plot-section {
    background: linear-gradient(145deg, #ffffff 0%, #f8f9ff 100%) !important;
    border: 1px solid rgba(102, 126, 234, 0.2) !important;
    border-radius: 12px !important;
    padding: 1rem !important;
    margin-top: 1rem !important;
}

.plot-header {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    margin-bottom: 0.75rem !important;
    padding-bottom: 0.5rem !important;
    border-bottom: 1px solid rgba(102, 126, 234, 0.1) !important;
}

.plot-header h3 {
    margin: 0 !important;
    color: #4a5568 !important;
    font-size: 1rem !important;
    font-weight: 600 !important;
}

.plot-gallery {
    border-radius: 8px !important;
    overflow: hidden !important;
}

.plot-gallery .gallery-item {
    border-radius: 8px !important;
    transition: transform 0.2s ease !important;
}

.plot-gallery .gallery-item:hover {
    transform: scale(1.02) !important;
}

.refresh-plots-btn {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 500 !important;
    padding: 0.5rem 1rem !important;
    border-radius: 8px !important;
    font-size: 0.85rem !important;
}

.empty-plots {
    text-align: center !important;
    padding: 2rem !important;
    color: #718096 !important;
    font-style: italic !important;
}

/* ============================================
   TASK OUTPUTS SECTION
   ============================================ */

.outputs-section {
    background: linear-gradient(145deg, #ffffff 0%, #f0fff4 100%) !important;
    border: 1px solid rgba(72, 187, 120, 0.2) !important;
    border-radius: 12px !important;
    padding: 1rem !important;
    margin-top: 1rem !important;
}

.outputs-header {
    margin-bottom: 0.75rem !important;
    padding-bottom: 0.5rem !important;
    border-bottom: 1px solid rgba(72, 187, 120, 0.1) !important;
}

.outputs-header h3 {
    margin: 0 !important;
    color: #276749 !important;
    font-size: 1rem !important;
    font-weight: 600 !important;
}

.file-input-row {
    display: flex !important;
    gap: 0.5rem !important;
    align-items: flex-end !important;
    margin-bottom: 0.75rem !important;
}

.load-csv-btn {
    background: linear-gradient(135deg, #48bb78 0%, #38a169 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 500 !important;
    padding: 0.5rem 1rem !important;
    border-radius: 8px !important;
    font-size: 0.85rem !important;
}

.output-status {
    font-size: 0.9rem !important;
    padding: 0.5rem !important;
    border-radius: 6px !important;
    background: #f7fafc !important;
}

.output-table {
    border-radius: 8px !important;
    overflow: hidden !important;
    max-height: 400px !important;
    overflow-y: auto !important;
}

.available-files {
    font-size: 0.8rem !important;
    color: #718096 !important;
    margin-top: 0.25rem !important;
}
"""

with gr.Blocks(title="🎨 Art Analysis Agent", css=CUSTOM_CSS) as demo:
    # Session state to store session_id (which maps to thread_id in session_storage)
    session_id_state = gr.State(value=str(uuid.uuid4()))

    # State to track interrupt status
    interrupt_state = gr.State(value={})

    # Header Section
    with gr.Row(elem_classes="header-container"):
        gr.Markdown(
            """
            # 🎨 Art Analysis Agent
            **Powered by LangGraph v2 with Human-in-the-Loop**
            
            Explore artwork data, analyze paintings visually, and generate visualizations with an intelligent multi-step agent.
            """
        )

    # Feature badges
    with gr.Row():
        gr.Markdown(
            """
            <div style="text-align: center; margin-bottom: 1rem;">
                <span class="feature-badge">📊 Data Exploration</span>
                <span class="feature-badge">🖼️ Image Analysis</span>
                <span class="feature-badge">📈 Plot Generation</span>
                <span class="feature-badge">🤝 Human Approval</span>
            </div>
            """,
            elem_classes="features"
        )

    # Status Bar
    with gr.Row():
        with gr.Column(scale=3):
            status_display = gr.Textbox(
                label="🔄 Agent Status",
                value="🆕 Ready to start — Send a message to begin!",
                interactive=False,
                elem_classes="status-bar"
            )
        with gr.Column(scale=1):
            check_interrupt_btn = gr.Button(
                "🔍 Check Approval",
                variant="secondary",
                elem_classes="check-btn"
            )
        with gr.Column(scale=1):
            reset_btn = gr.Button(
                "🔄 New Chat",
                variant="secondary",
                elem_classes="reset-btn"
            )

    # Interrupt Modal (Hidden by default) - Modern Design
    with gr.Group(visible=False, elem_classes="interrupt-modal") as interrupt_modal:
        # Modal Header
        gr.HTML("""
            <div class="modal-header">
                <h2>⚡ Approval Required</h2>
            </div>
        """)
        
        # Modal Body
        with gr.Column(elem_classes="modal-body"):
            gr.HTML("""
                <p style="text-align: center; color: #4a5568; margin-bottom: 0.5rem;">
                    The agent has paused and needs your confirmation<br>before proceeding with the next action.
                </p>
            """)
            
            # Question/Reason display
            with gr.Group(elem_classes="modal-reason"):
                interrupt_question = gr.Markdown("Loading details...")
        
        # Modal Footer with Buttons
        with gr.Row(elem_classes="modal-footer"):
            approve_btn = gr.Button(
                "✅ Approve & Continue", 
                variant="primary", 
                scale=1,
                elem_classes="modal-btn approve-btn"
            )
            reject_btn = gr.Button(
                "❌ Reject & Stop", 
                variant="stop", 
                scale=1,
                elem_classes="modal-btn reject-btn"
            )

    # Main chat interface
    chatbot = gr.ChatInterface(
        respond,
        type="messages",
        additional_inputs=[session_id_state],
        chatbot=gr.Chatbot(
            height=500,
            elem_classes="chatbot-container",
            placeholder="💬 Ask me anything about the artwork database...\n\nExamples:\n• 'What is the oldest painting in the database?'\n• 'Plot paintings count by genre'\n• 'Analyze the colors in Renaissance paintings'",
            show_copy_button=True,
            type="messages",
        ),
    )

    # ============================================================
    # PLOT GALLERY SECTION
    # ============================================================
    with gr.Group(elem_classes="plot-section"):
        with gr.Row():
            gr.Markdown("### 📊 Generated Plots")
            refresh_plots_btn = gr.Button(
                "🔄 Refresh",
                size="sm",
                elem_classes="refresh-plots-btn"
            )
        
        # Gallery to display plot images
        plot_gallery = gr.Gallery(
            value=get_plot_images(),
            label="Plot Gallery",
            show_label=False,
            elem_classes="plot-gallery",
            columns=3,
            rows=2,
            height="auto",
            object_fit="contain",
            allow_preview=True,
            preview=True,
        )
        
        # Empty state message (shown when no plots)
        no_plots_msg = gr.Markdown(
            "<div class='empty-plots'>📭 No plots generated yet. Ask the agent to create visualizations!</div>",
            visible=len(get_plot_images()) == 0
        )
    
    # Refresh plots button click handler
    def update_plot_gallery():
        plots = get_plot_images()
        return plots, gr.update(visible=len(plots) == 0)
    
    refresh_plots_btn.click(
        update_plot_gallery,
        outputs=[plot_gallery, no_plots_msg]
    )

    # ============================================================
    # TASK OUTPUTS SECTION (CSV Display)
    # ============================================================
    with gr.Group(elem_classes="outputs-section"):
        gr.Markdown("### 📋 Task Outputs", elem_classes="outputs-header")
        
        # Get available files for hint
        available_files = get_output_files()
        available_hint = f"Available: {', '.join(available_files[:5])}{'...' if len(available_files) > 5 else ''}" if available_files else "No files yet"
        
        with gr.Row(elem_classes="file-input-row"):
            with gr.Column(scale=4):
                csv_filename_input = gr.Textbox(
                    label="📄 Enter CSV Filename",
                    placeholder="e.g., painting_count.csv or painting_count",
                    info=available_hint,
                    scale=4
                )
            with gr.Column(scale=1):
                load_csv_btn = gr.Button(
                    "📂 Load File",
                    elem_classes="load-csv-btn",
                    size="sm"
                )
            with gr.Column(scale=1):
                refresh_files_btn = gr.Button(
                    "🔄 Refresh List",
                    size="sm"
                )
        
        # Status message
        csv_status = gr.Markdown(
            "📭 Enter a filename to display its contents.",
            elem_classes="output-status"
        )
        
        # Table to display CSV content
        csv_table = gr.Dataframe(
            label="CSV Content",
            show_label=False,
            elem_classes="output-table",
            interactive=False,
            wrap=True,
            visible=False
        )
    
    # Load CSV button handler
    def on_load_csv(filename):
        df, status = load_csv_file(filename)
        if df is not None:
            return gr.update(value=df, visible=True), status
        else:
            return gr.update(visible=False), status
    
    load_csv_btn.click(
        on_load_csv,
        inputs=[csv_filename_input],
        outputs=[csv_table, csv_status]
    )
    
    # Also load on Enter key
    csv_filename_input.submit(
        on_load_csv,
        inputs=[csv_filename_input],
        outputs=[csv_table, csv_status]
    )
    
    # Refresh available files list
    def refresh_file_list():
        files = get_output_files()
        hint = f"Available: {', '.join(files[:5])}{'...' if len(files) > 5 else ''}" if files else "No files yet"
        return gr.update(info=hint)
    
    refresh_files_btn.click(
        refresh_file_list,
        outputs=[csv_filename_input]
    )

    # Hidden trigger for interrupt check (used to manually trigger modal after response)
    interrupt_check_trigger = gr.Textbox(visible=False, value="")

    # Wire up the reset button
    reset_btn.click(
        reset_conversation,
        inputs=[session_id_state],
        outputs=[session_id_state, status_display]
    )

    # Check for interrupts after each message
    def check_and_show_interrupt(session_id):
        """Check if agent is interrupted and show modal if needed."""
        is_interrupted, data, modal_update, question = check_interrupt_status(session_id)

        if is_interrupted:
            question_md = f"**Reason:** {question}"
            return modal_update, question_md, data
        else:
            return gr.update(visible=False), "", {}

    # Use a more reliable trigger mechanism
    # When the chatbot value changes after bot finishes, check for interrupts
    def delayed_interrupt_check(history, session_id):
        """Called after chatbot updates - check for interrupts."""
        # Check if the last message contains the interrupt indicator
        if history and len(history) > 0:
            last_msg = history[-1]
            if isinstance(last_msg, dict) and "awaiting your approval" in last_msg.get("content", ""):
                print(f"🔔 Interrupt indicator detected in message, showing modal...")
                is_interrupted, data, modal_update, question = check_interrupt_status(session_id)
                if is_interrupted:
                    question_md = f"**Reason:** {question}"
                    return modal_update, question_md, data
        
        # Also do a regular check
        is_interrupted, data, modal_update, question = check_interrupt_status(session_id)
        if is_interrupted:
            print(f"🔔 Modal trigger: Interrupt detected!")
            question_md = f"**Reason:** {question}"
            return modal_update, question_md, data
        return gr.update(visible=False), "", {}

    # Trigger interrupt check when chatbot changes (after each message)
    chatbot.chatbot.change(
        delayed_interrupt_check,
        inputs=[chatbot.chatbot, session_id_state],
        outputs=[interrupt_modal, interrupt_question, interrupt_state]
    )
    
    # Also refresh plots when chatbot changes (new messages might have generated plots)
    def refresh_plots_on_update():
        plots = get_plot_images()
        return plots, gr.update(visible=len(plots) == 0)
    
    chatbot.chatbot.change(
        refresh_plots_on_update,
        outputs=[plot_gallery, no_plots_msg]
    )

    # Handle approval
    def on_approve(session_id, history):
        updated_history, _, status = handle_approval(session_id, True, history)
        # Check again for new interrupts (in case there's a chain)
        is_interrupted, _, modal_visibility, question = check_interrupt_status(session_id)
        if is_interrupted:
            question_md = f"**Reason:** {question}"
            return updated_history, modal_visibility, question_md, status
        else:
            return updated_history, gr.update(visible=False), "", status

    approve_btn.click(
        on_approve,
        inputs=[session_id_state, chatbot.chatbot],
        outputs=[chatbot.chatbot, interrupt_modal, interrupt_question, status_display]
    )

    # Handle rejection
    def on_reject(session_id, history):
        updated_history, modal_visibility, status = handle_approval(session_id, False, history)
        return updated_history, modal_visibility, status

    reject_btn.click(
        on_reject,
        inputs=[session_id_state, chatbot.chatbot],
        outputs=[chatbot.chatbot, interrupt_modal, status_display]
    )

    # Manual interrupt check (for debugging)
    check_interrupt_btn.click(
        check_and_show_interrupt,
        inputs=[session_id_state],
        outputs=[interrupt_modal, interrupt_question, interrupt_state]
    )

    # Footer
    gr.Markdown(
        """
        ---
        <div style="text-align: center; color: #6c757d; font-size: 0.85rem;">
            🤖 Built with LangGraph + Gradio | Session-based memory with HITL support
        </div>
        """,
    )


if __name__ == "__main__":
    demo.launch()

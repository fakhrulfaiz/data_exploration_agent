import gradio as gr
import uuid
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add agent directory to path
sys.path.append(str(Path(__file__).parent / "agent"))

# Import from main_agent_v2 (the redesigned supervisor)
from agent.main_agent_v2 import initialize_agent_with_checkpointer, create_thread_config
from langgraph.types import Command

# Initialize the LangGraph agent with checkpointer (once at module level)
print("Initializing LangGraph Agent v2...")
agent, checkpointer = initialize_agent_with_checkpointer()
print("Agent v2 initialized successfully!")


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
        # Use the proper initial state format for main_agent_v2
        initial_state = {
            "messages": [{"role": "user", "content": message}],
            "original_query": message
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

/* Interrupt modal styling */
.interrupt-modal {
    position: fixed !important;
    top: 50% !important;
    left: 50% !important;
    transform: translate(-50%, -50%) !important;
    z-index: 1000 !important;
    background: white !important;
    padding: 2rem !important;
    border-radius: 16px !important;
    box-shadow: 0 12px 48px rgba(0,0,0,0.25) !important;
    max-width: 480px !important;
    width: 90% !important;
    border: 2px solid #667eea !important;
}

.interrupt-modal h2 {
    color: #667eea !important;
    margin-top: 0 !important;
}

/* Button styling */
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
        with gr.Column(scale=4):
            status_display = gr.Textbox(
                label="🔄 Agent Status",
                value="🆕 Ready to start — Send a message to begin!",
                interactive=False,
                elem_classes="status-bar"
            )
        with gr.Column(scale=1):
            reset_btn = gr.Button(
                "🔄 New Chat",
                variant="secondary",
                elem_classes="reset-btn"
            )

    # Interrupt Modal (Hidden by default)
    with gr.Group(visible=False, elem_classes="interrupt-modal") as interrupt_modal:
        gr.Markdown("## ⚠️ Approval Required")
        gr.Markdown("The agent needs your confirmation before proceeding with the next action.")
        
        interrupt_question = gr.Markdown("**Details:** Loading...")

        gr.Markdown("---")
        
        with gr.Row():
            approve_btn = gr.Button(
                "✅ Approve & Continue", 
                variant="primary", 
                scale=1,
                elem_classes="primary-btn"
            )
            reject_btn = gr.Button(
                "❌ Reject & Stop", 
                variant="stop", 
                scale=1,
                elem_classes="danger-btn"
            )

        gr.Markdown(
            "*The agent is paused and waiting for your decision to continue.*",
            elem_classes="modal-footer"
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

    # Hidden check button (for debugging)
    check_interrupt_btn = gr.Button("🔍 Check Status", visible=False)

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

    # Trigger interrupt check after bot responds
    chatbot.chatbot.change(
        check_and_show_interrupt,
        inputs=[session_id_state],
        outputs=[interrupt_modal, interrupt_question, interrupt_state]
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

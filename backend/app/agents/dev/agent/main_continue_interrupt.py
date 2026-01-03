from langgraph.types import Command 
config = {
    "thread_id" : "dev-fyp"
}

from main_agent import build_main_agent
supervisor_agent = build_main_agent()
interrupts = []
for step in supervisor_agent.stream(
    Command(resume=True), 
    config,
):
    for update in step.values():
        if isinstance(update, dict):
            for message in update.get("messages", []):
                message.pretty_print()
        else:
            interrupt_ = update[0]
            interrupts.append(interrupt_)
            print(f"\nINTERRUPTED: {interrupt_.id}")
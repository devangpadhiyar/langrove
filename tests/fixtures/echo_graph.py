"""Simple echo graph for testing."""

from typing import TypedDict

from langgraph.graph import StateGraph


class State(TypedDict):
    messages: list[dict]


def echo(state: State) -> dict:
    """Echo the last message back."""
    last = state["messages"][-1]
    return {"messages": [{"role": "assistant", "content": last["content"]}]}


builder = StateGraph(State)
builder.add_node("echo", echo)
builder.set_entry_point("echo")
builder.set_finish_point("echo")
graph = builder.compile()

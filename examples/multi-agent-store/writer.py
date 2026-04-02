"""Writer agent graph -- produces polished articles from research context.

Expects ``research_context`` in the input state, which is typically
retrieved from the Langrove store after a researcher run.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import AnyMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class WriterState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    research_context: str
    draft: str


model = ChatOpenAI(model="gpt-4o-mini")


async def write(state: WriterState) -> dict:
    """Write a polished article using the provided research context."""
    context = state.get("research_context", "")
    response = await model.ainvoke([
        SystemMessage(
            content=(
                "You are a professional writer. Use the following research to "
                "write a polished, engaging article.\n\n"
                f"Research:\n{context}"
            )
        ),
        *state["messages"],
    ])
    return {"messages": [response], "draft": response.content}


builder = StateGraph(WriterState)
builder.add_node("write", write)
builder.set_entry_point("write")
builder.set_finish_point("write")

graph = builder.compile()

"""Simple chatbot agent for the custom-auth example."""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import AnyMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


model = ChatOpenAI(model="gpt-4o-mini")


async def chatbot(state: State) -> dict:
    response = await model.ainvoke(
        [
            SystemMessage(content="You are a helpful assistant."),
            *state["messages"],
        ]
    )
    return {"messages": [response]}


builder = StateGraph(State)
builder.add_node("chatbot", chatbot)
builder.set_entry_point("chatbot")
builder.set_finish_point("chatbot")

graph = builder.compile()

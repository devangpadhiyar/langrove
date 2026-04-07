"""Research agent graph -- gathers information on a topic.

This graph has two nodes:
  1. research: LLM analyzes the topic and produces findings
  2. publish: Formats findings for output (can be interrupted for review)
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import AnyMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ResearchState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    topic: str
    findings: str


model = ChatOpenAI(model="gpt-4o-mini")


async def research(state: ResearchState) -> dict:
    """Analyze the topic and produce detailed findings."""
    _topic = state.get("topic", "")
    response = await model.ainvoke(
        [
            SystemMessage(
                content=(
                    "You are a research assistant. Provide thorough, factual findings "
                    "on the given topic. Structure your response with key points."
                )
            ),
            *state["messages"],
        ]
    )
    return {"messages": [response], "findings": response.content}


async def publish(state: ResearchState) -> dict:
    """Format findings for publication."""
    response = await model.ainvoke(
        [
            SystemMessage(
                content=(
                    "You are an editor. Take the research findings and produce a "
                    "concise, well-structured summary suitable for sharing."
                )
            ),
            *state["messages"],
        ]
    )
    return {"messages": [response], "findings": response.content}


builder = StateGraph(ResearchState)
builder.add_node("research", research)
builder.add_node("publish", publish)
builder.set_entry_point("research")
builder.add_edge("research", "publish")
builder.set_finish_point("publish")

graph = builder.compile()

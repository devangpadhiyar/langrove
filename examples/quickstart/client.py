"""SDK client demonstrating Langrove quickstart features.

Features shown:
  - Auto-created assistants and schema introspection
  - Persistent threads with checkpointed state
  - SSE streaming (messages and values modes)
  - Thread state inspection

Prerequisites:
  1. docker compose up postgres redis   (from project root)
  2. uv run alembic upgrade head        (from project root)
  3. cp .env.example .env && fill in OPENAI_API_KEY
  4. cd examples/quickstart && uv run langrove serve
"""

from __future__ import annotations

import asyncio

from langgraph_sdk import get_client


async def main():
    client = get_client(url="http://localhost:8123")

    # ----------------------------------------------------------------
    # 1. List auto-created assistants
    # ----------------------------------------------------------------
    # Langrove auto-creates an assistant for every graph in langgraph.json
    # on startup. No manual registration needed.
    assistants = await client.assistants.search()
    print("=== Assistants (auto-created from langgraph.json) ===")
    for a in assistants:
        print(f"  {a['name']}  graph_id={a['graph_id']}  id={a['assistant_id']}")

    # Get the graph's input/output/state schemas
    assistant_id = assistants[0]["assistant_id"]
    schemas = await client.assistants.get_schemas(assistant_id)
    print(f"\n=== Schemas for '{assistants[0]['name']}' ===")
    print(f"  input:  {list(schemas.get('input_schema', {}).get('properties', {}).keys())}")
    print(f"  output: {list(schemas.get('output_schema', {}).get('properties', {}).keys())}")

    # ----------------------------------------------------------------
    # 2. Create a persistent thread
    # ----------------------------------------------------------------
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    print(f"\n=== Created thread {thread_id} ===")

    # ----------------------------------------------------------------
    # 3. Stream a run (messages mode)
    # ----------------------------------------------------------------
    # "messages" mode streams individual message chunks as they are generated.
    print("\n=== Streaming (messages mode) ===")
    async for event in client.runs.stream(
        thread_id,
        "chatbot",
        input={"messages": [{"role": "user", "content": "What is Langrove?"}]},
        stream_mode=["messages"],
    ):
        if event.event == "messages":
            # Each chunk is [message_dict, metadata]
            msg = event.data[0] if isinstance(event.data, list) else event.data
            content = msg.get("content", "")
            if content:
                print(content, end="", flush=True)
        elif event.event == "metadata":
            print(f"  run_id: {event.data['run_id']}")
    print()

    # ----------------------------------------------------------------
    # 4. Continue conversation on the same thread (values mode)
    # ----------------------------------------------------------------
    # The previous message history is persisted via the PostgreSQL checkpointer.
    # "values" mode emits the full state after each node execution.
    print("\n=== Streaming (values mode) -- follow-up question ===")
    async for event in client.runs.stream(
        thread_id,
        "chatbot",
        input={"messages": [{"role": "user", "content": "Summarize that in one sentence."}]},
        stream_mode=["values"],
    ):
        if event.event == "values":
            messages = event.data.get("messages", [])
            if messages:
                last = messages[-1]
                print(f"  [{last.get('role', '?')}] {last.get('content', '')[:120]}")
    print()

    # ----------------------------------------------------------------
    # 5. Inspect thread state
    # ----------------------------------------------------------------
    state = await client.threads.get_state(thread_id)
    print("=== Thread state ===")
    print(f"  status: {thread.get('status', 'unknown')}")
    print(f"  message count: {len(state.get('values', {}).get('messages', []))}")
    print(f"  next: {state.get('next', [])}")

    # ----------------------------------------------------------------
    # 6. Search threads
    # ----------------------------------------------------------------
    threads = await client.threads.search()
    print(f"\n=== All threads ({len(threads)}) ===")
    for t in threads[:5]:
        print(f"  {t['thread_id']}  status={t.get('status', '?')}")


if __name__ == "__main__":
    asyncio.run(main())

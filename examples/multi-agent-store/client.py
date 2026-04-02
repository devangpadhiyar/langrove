"""SDK client demonstrating advanced Langrove features.

Features shown:
  - Multiple graphs in one deployment
  - Store API: put, get, search, list namespaces, delete
  - Cron API: create, update, search, delete scheduled runs
  - Interrupt/resume flow with request-time interrupt_before
  - Multitask strategies
  - Run search and management
  - Research -> Store -> Write pipeline

Prerequisites:
  1. docker compose up postgres redis   (from project root)
  2. uv run alembic upgrade head        (from project root)
  3. cp .env.example .env && fill in OPENAI_API_KEY
  4. cd examples/multi-agent-store && uv run langrove serve
"""

from __future__ import annotations

import asyncio

from langgraph_sdk import get_client


async def main():
    client = get_client(url="http://localhost:8123")

    # ----------------------------------------------------------------
    # 1. Multiple graphs -- both auto-registered as assistants
    # ----------------------------------------------------------------
    print("=== Assistants (multiple graphs) ===")
    assistants = await client.assistants.search()
    for a in assistants:
        print(f"  {a['graph_id']:15s}  id={a['assistant_id']}")

    # ----------------------------------------------------------------
    # 2. Run the researcher with interrupt_before
    # ----------------------------------------------------------------
    # The researcher graph has two nodes: "research" -> "publish".
    # We interrupt before "publish" so we can review findings first.
    print("\n=== Run researcher (interrupt before publish) ===")
    thread = await client.threads.create()
    tid = thread["thread_id"]

    async for event in client.runs.stream(
        tid,
        "researcher",
        input={
            "messages": [{"role": "user", "content": "Research the benefits of open-source AI"}],
            "topic": "open-source AI",
        },
        interrupt_before=["publish"],
        stream_mode=["values"],
    ):
        if event.event == "values":
            findings = event.data.get("findings", "")
            if findings:
                print(f"  Findings preview: {findings[:100]}...")

    # Check thread state -- should be interrupted before "publish"
    state = await client.threads.get_state(tid)
    print(f"  Thread status: interrupted")
    print(f"  Next node: {state.get('next', [])}")

    # Resume execution (approve the publish)
    print("\n=== Resume researcher (approve publish) ===")
    async for event in client.runs.stream(
        tid,
        "researcher",
        command={"resume": True},
        stream_mode=["values"],
    ):
        if event.event == "values":
            findings = event.data.get("findings", "")
            if findings:
                print(f"  Published: {findings[:100]}...")

    # Get final findings from thread state
    final_state = await client.threads.get_state(tid)
    research_findings = final_state.get("values", {}).get("findings", "")

    # ----------------------------------------------------------------
    # 3. Store API -- save research findings for cross-thread access
    # ----------------------------------------------------------------
    print("\n=== Store API ===")

    # Put: save findings to a namespaced key
    await client.store.put_item(
        namespace=["research", "ai"],
        key="open-source-benefits",
        value={
            "findings": research_findings,
            "topic": "open-source AI",
            "source_thread": tid,
        },
    )
    print("  Stored findings at namespace=['research', 'ai'] key='open-source-benefits'")

    # Get: retrieve by namespace + key
    item = await client.store.get_item(
        namespace=["research", "ai"],
        key="open-source-benefits",
    )
    print(f"  Retrieved item: key={item['key']}, created={item.get('created_at', '?')}")

    # Search: find items by namespace prefix
    results = await client.store.search_items(
        namespace_prefix=["research"],
        limit=10,
    )
    print(f"  Search results (prefix=['research']): {len(results)} item(s)")

    # List namespaces
    namespaces = await client.store.list_namespaces(
        prefix=["research"],
        max_depth=3,
    )
    print(f"  Namespaces under ['research']: {namespaces}")

    # ----------------------------------------------------------------
    # 4. Pipeline: feed research into the writer via store
    # ----------------------------------------------------------------
    print("\n=== Writer pipeline (using stored research) ===")
    writer_thread = await client.threads.create()

    # Read from store, pass as context to writer
    stored = await client.store.get_item(
        namespace=["research", "ai"],
        key="open-source-benefits",
    )
    research_context = stored["value"]["findings"]

    async for event in client.runs.stream(
        writer_thread["thread_id"],
        "writer",
        input={
            "messages": [{"role": "user", "content": "Write a blog post about this research."}],
            "research_context": research_context,
        },
        stream_mode=["messages"],
    ):
        if event.event == "messages":
            msg = event.data[0] if isinstance(event.data, list) else event.data
            content = msg.get("content", "")
            if content:
                print(content, end="", flush=True)
    print()

    # ----------------------------------------------------------------
    # 5. Cron API -- schedule periodic research
    # ----------------------------------------------------------------
    print("\n=== Cron API ===")

    # Create a cron: run researcher every 6 hours
    researcher_assistant = next(
        a for a in assistants if a["graph_id"] == "researcher"
    )
    cron = await client.crons.create(
        assistant_id=str(researcher_assistant["assistant_id"]),
        schedule="0 */6 * * *",
        payload={
            "messages": [{"role": "user", "content": "Research latest AI developments"}],
            "topic": "AI developments",
        },
    )
    print(f"  Created cron: {cron['cron_id']}")
    print(f"  Schedule: {cron['schedule']}")
    print(f"  Next run: {cron.get('next_run_date', 'N/A')}")

    # Search crons
    crons = await client.crons.search(
        assistant_id=researcher_assistant["assistant_id"],
    )
    print(f"  Found {len(crons)} cron(s) for researcher")

    # Update: change to every 12 hours
    updated = await client.crons.update(
        cron["cron_id"],
        schedule="0 */12 * * *",
    )
    print(f"  Updated schedule: {updated['schedule']}")

    # Disable
    await client.crons.update(cron["cron_id"], enabled=False)
    print("  Disabled cron")

    # Delete
    await client.crons.delete(cron["cron_id"])
    print("  Deleted cron")

    # ----------------------------------------------------------------
    # 6. Multitask strategies
    # ----------------------------------------------------------------
    print("\n=== Multitask strategies ===")
    mt_thread = await client.threads.create()

    # Default strategy is "reject" -- a second run on a busy thread
    # returns 409 Conflict. Other strategies:
    #   "interrupt" -- cancel the current run, start the new one
    #   "rollback"  -- rollback to last checkpoint, start new run
    #   "enqueue"   -- queue behind the current run
    print("  Available strategies: reject (default), interrupt, rollback, enqueue")

    # Example: enqueue strategy
    async for event in client.runs.stream(
        mt_thread["thread_id"],
        "researcher",
        input={
            "messages": [{"role": "user", "content": "Research quantum computing"}],
            "topic": "quantum computing",
        },
        multitask_strategy="enqueue",
        stream_mode=["values"],
    ):
        pass
    print("  Completed run with enqueue strategy")

    # ----------------------------------------------------------------
    # 7. Run search
    # ----------------------------------------------------------------
    print("\n=== Run search ===")
    runs = await client.runs.search(
        thread_id=tid,
    )
    print(f"  Runs on researcher thread: {len(runs)}")
    for r in runs:
        print(f"    {r['run_id']}  status={r['status']}")

    # ----------------------------------------------------------------
    # 8. Cleanup -- delete store item
    # ----------------------------------------------------------------
    await client.store.delete_item(
        namespace=["research", "ai"],
        key="open-source-benefits",
    )
    print("\n=== Cleaned up store item ===")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())

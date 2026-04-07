"""SDK client demonstrating the Helios Video Production Agent.

Features shown:
  - DeepAgents-powered tool-calling agent with VFS (StoreBackend)
  - Professional video composition generation
  - Streaming with tool call visibility
  - Human-in-the-loop review (interrupt/resume)
  - Composition retrieval from Langrove Store API
  - Iterative feedback loop

Prerequisites:
  1. docker compose up postgres redis   (from project root)
  2. uv run alembic upgrade head        (from project root)
  3. cp .env.example .env && fill in ANTHROPIC_API_KEY (or OPENAI_API_KEY)
  4. cd examples/helios-video-agent && uv run langrove serve
"""

from __future__ import annotations

import asyncio

from langgraph_sdk import get_client


async def main():
    client = get_client(url="http://localhost:8123")

    # ----------------------------------------------------------------
    # 1. Verify the video-agent is registered
    # ----------------------------------------------------------------
    print("=== Assistants ===")
    assistants = await client.assistants.search()
    for a in assistants:
        print(f"  {a['graph_id']:15s}  id={a['assistant_id']}")

    video_agent = next(
        (a for a in assistants if a["graph_id"] == "video-agent"),
        None,
    )
    if not video_agent:
        print("ERROR: video-agent not found. Is the server running?")
        return

    # ----------------------------------------------------------------
    # 2. Create a thread and start the video composition
    # ----------------------------------------------------------------
    print("\n=== Creating video composition ===")
    thread = await client.threads.create()
    tid = thread["thread_id"]
    print(f"  Thread: {tid}")

    # Creative brief
    brief = (
        "Create a 15-second product advertisement for premium wireless headphones. "
        "Cinematic dark theme with electric blue accents and subtle particle effects. "
        "Features: noise cancellation, 40-hour battery, spatial audio. "
        "Include kinetic typography, a product hero reveal with 3D rotation feel, "
        "and a call-to-action with the price $299. Resolution: 1920x1080, 30fps."
    )

    print(f"\n  Brief: {brief[:80]}...")
    print("\n=== Streaming (with interrupt before assemble_composition) ===\n")

    # Stream with interrupt at assemble_composition (HITL review)
    tool_calls_seen: list[str] = []
    async for event in client.runs.stream(
        tid,
        "video-agent",
        input={"messages": [{"role": "user", "content": brief}]},
        stream_mode=["messages", "values"],
    ):
        if event.event == "messages":
            msg = event.data[0] if isinstance(event.data, list) else event.data
            content = msg.get("content", "")

            # Show tool calls for visibility into the creative process
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("args", {})
                if name == "write_file":
                    path = args.get("path", args.get("file_path", ""))
                    tool_calls_seen.append(name)
                    print(f"  [tool] write_file → {path}")
                elif name == "write_todos":
                    tool_calls_seen.append(name)
                    print("  [tool] write_todos → Planning storyboard...")
                elif name == "edit_file":
                    path = args.get("path", args.get("file_path", ""))
                    tool_calls_seen.append(name)
                    print(f"  [tool] edit_file → {path}")
                elif name == "assemble_composition":
                    tool_calls_seen.append(name)
                    print("  [tool] assemble_composition → Building final HTML...")
                elif name == "validate_composition":
                    tool_calls_seen.append(name)
                    print("  [tool] validate_composition → Checking structure...")
                elif name in ("read_file", "ls", "glob", "grep") or name:
                    tool_calls_seen.append(name)
                    print(f"  [tool] {name}")

            # Show streaming text (agent's thinking/responses)
            if content and not tool_calls and msg.get("role") != "tool":
                # Print a snippet of the agent's response
                lines = content.strip().split("\n")
                for line in lines[:3]:
                    print(f"  > {line[:100]}")
                if len(lines) > 3:
                    print(f"  > ... ({len(lines)} lines)")

    print(f"\n  Tool calls executed: {len(tool_calls_seen)}")

    # ----------------------------------------------------------------
    # 3. Check thread state — should be interrupted for HITL review
    # ----------------------------------------------------------------
    print("\n=== Checking interrupt state ===")
    state = await client.threads.get_state(tid)
    next_nodes = state.get("next", [])
    print(f"  Next nodes: {next_nodes}")

    # ----------------------------------------------------------------
    # 4. Read the composition from Store (VFS)
    # ----------------------------------------------------------------
    print("\n=== Reading composition from Store ===")
    try:
        item = await client.store.get_item(
            namespace=["vfs", tid],
            key="/dist/index.html",
        )
        composition_html = item.get("value", {}).get("content", "")
        if composition_html:
            print(f"  Composition size: {len(composition_html)} bytes")
            # Show first few lines
            lines = composition_html.split("\n")
            for line in lines[:5]:
                print(f"    {line[:80]}")
            if len(lines) > 5:
                print(f"    ... ({len(lines)} total lines)")
        else:
            print("  No composition found at /dist/index.html yet.")
            print("  (The agent may have stored it at a different path)")

            # Try listing VFS files
            results = await client.store.search_items(
                namespace_prefix=["vfs", tid],
                limit=20,
            )
            if results:
                print(f"\n  VFS files found ({len(results)}):")
                for item in results:
                    print(f"    {item.get('key', '?')}")
    except Exception as e:
        print(f"  Could not read composition: {e}")

    # ----------------------------------------------------------------
    # 5. Resume with approval (or provide feedback)
    # ----------------------------------------------------------------
    print("\n=== Resuming with approval ===")

    async for event in client.runs.stream(
        tid,
        "video-agent",
        command={"resume": True},
        stream_mode=["values"],
    ):
        if event.event == "values":
            values = event.data
            if isinstance(values, dict):
                # Show final state snippet
                messages = values.get("messages", [])
                if messages:
                    last = messages[-1] if messages else {}
                    content = last.get("content", "")
                    if content:
                        print(f"  Final: {content[:150]}...")

    print("  Composition approved!")

    # ----------------------------------------------------------------
    # 6. Example: feedback loop (instead of approval)
    # ----------------------------------------------------------------
    print("\n=== Feedback loop example (not executed) ===")
    print("  To provide feedback instead of approving, resume with a message:")
    print('  command={"resume": {"feedback": "Make the product reveal more dramatic"}}')
    print("  The agent will iterate on the composition and interrupt again for review.")

    # ----------------------------------------------------------------
    # 7. Rendering instructions
    # ----------------------------------------------------------------
    print("\n=== Rendering ===")
    print("  To render the composition to video:")
    print("  1. Save /dist/index.html to a local file")
    print("  2. npx helios render index.html -o output.mp4 --width 1920 --height 1080 --fps 30")
    print("  Or use the frontend with <helios-player> for live preview.")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())

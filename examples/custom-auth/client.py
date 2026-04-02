"""SDK client demonstrating Langrove custom auth features.

Features shown:
  - Authenticated SDK client with Bearer token
  - Admin vs. read-only role tokens
  - 401 rejection for invalid/missing tokens
  - Health endpoints bypass auth (/ok, /health, /docs)

Prerequisites:
  1. docker compose up postgres redis   (from project root)
  2. uv run alembic upgrade head        (from project root)
  3. cp .env.example .env && fill in OPENAI_API_KEY
  4. cd examples/custom-auth && uv run langrove serve
"""

from __future__ import annotations

import asyncio

import httpx
from langgraph_sdk import get_client


async def main():
    # ----------------------------------------------------------------
    # 1. Health endpoints work WITHOUT auth
    # ----------------------------------------------------------------
    # Langrove skips auth for: /ok, /health, /info, /docs, /openapi.json, /redoc
    print("=== Health check (no auth required) ===")
    async with httpx.AsyncClient() as http:
        resp = await http.get("http://localhost:8123/ok")
        print(f"  GET /ok -> {resp.status_code}")

    # ----------------------------------------------------------------
    # 2. Unauthenticated request -> 401
    # ----------------------------------------------------------------
    print("\n=== Unauthenticated request ===")
    async with httpx.AsyncClient() as http:
        resp = await http.post("http://localhost:8123/threads")
        print(f"  POST /threads (no token) -> {resp.status_code}")
        print(f"  body: {resp.text}")

    # ----------------------------------------------------------------
    # 3. Invalid token -> 401
    # ----------------------------------------------------------------
    print("\n=== Invalid token ===")
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            "http://localhost:8123/threads",
            headers={"Authorization": "Bearer sk-wrong-key"},
        )
        print(f"  POST /threads (bad token) -> {resp.status_code}")

    # ----------------------------------------------------------------
    # 4. Authenticated client (admin role)
    # ----------------------------------------------------------------
    print("\n=== Authenticated client (admin) ===")
    admin_client = get_client(
        url="http://localhost:8123",
        headers={"Authorization": "Bearer sk-admin-key"},
    )

    # Create a thread -- succeeds with valid admin token
    thread = await admin_client.threads.create()
    print(f"  Created thread: {thread['thread_id']}")

    # Stream a run
    print("  Streaming response: ", end="")
    async for event in admin_client.runs.stream(
        thread["thread_id"],
        "agent",
        input={"messages": [{"role": "user", "content": "Say hello in 5 words."}]},
        stream_mode=["messages"],
    ):
        if event.event == "messages":
            msg = event.data[0] if isinstance(event.data, list) else event.data
            content = msg.get("content", "")
            if content:
                print(content, end="", flush=True)
    print()

    # ----------------------------------------------------------------
    # 5. Authenticated client (developer role)
    # ----------------------------------------------------------------
    print("\n=== Authenticated client (developer) ===")
    dev_client = get_client(
        url="http://localhost:8123",
        headers={"Authorization": "Bearer sk-dev-key"},
    )
    thread2 = await dev_client.threads.create()
    print(f"  Created thread: {thread2['thread_id']}")

    # ----------------------------------------------------------------
    # 6. Authenticated client (read-only role)
    # ----------------------------------------------------------------
    print("\n=== Authenticated client (viewer) ===")
    viewer_client = get_client(
        url="http://localhost:8123",
        headers={"Authorization": "Bearer sk-readonly-key"},
    )
    # Viewer can still hit endpoints -- role-based restrictions are
    # enforced in your auth handler or application logic, not by
    # Langrove middleware itself.
    assistants = await viewer_client.assistants.search()
    print(f"  Listed {len(assistants)} assistant(s)")


if __name__ == "__main__":
    asyncio.run(main())

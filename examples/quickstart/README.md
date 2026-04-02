# Quickstart -- Getting Started with Langrove

This example demonstrates the minimal path from zero to a running Langrove deployment.

## What You'll Learn

- How `langgraph.json` configures graph loading and CORS
- How Langrove auto-creates assistants from your graph registry
- How to use the `langgraph_sdk` Python client
- Persistent threads with PostgreSQL checkpointing
- SSE streaming in `messages` and `values` modes
- Thread state inspection via the API

## Project Structure

```
quickstart/
  agent.py          # Chatbot graph (StateGraph + ChatOpenAI)
  langgraph.json    # Langrove configuration
  client.py         # SDK client demonstrating all features
  .env.example      # Environment variable template
```

## Setup

**1. Start infrastructure** (from the project root):

```bash
docker compose up postgres redis -d
uv run alembic upgrade head
```

**2. Configure environment:**

```bash
cd examples/quickstart
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

**3. Start the server:**

```bash
uv run langrove serve
```

The server starts on `http://localhost:8123`. Verify with:

```bash
curl http://localhost:8123/ok
```

**4. Run the client:**

```bash
python client.py
```

## langgraph.json Explained

```jsonc
{
  // Each key is a graph_id, value is "path/to/module.py:attribute"
  "graphs": {
    "chatbot": "./agent.py:graph"
  },

  // Path to .env file (or inline dict of env vars)
  "env": ".env",

  // HTTP configuration
  "http": {
    "cors": {
      // Origins allowed to call the API (e.g., your React app)
      "allow_origins": ["http://localhost:3000", "http://localhost:5173"],
      "allow_methods": ["*"],
      "allow_headers": ["*"],
      // Set true if your frontend sends cookies/auth headers
      "allow_credentials": true
    }
  }
}
```

## Key Concepts

### Auto-Created Assistants

On startup, Langrove creates an assistant record for every graph in `langgraph.json`. You can list them via the SDK:

```python
assistants = await client.assistants.search()
```

### Streaming Modes

| Mode | What You Get |
|------|-------------|
| `messages` | Individual message chunks as they stream from the LLM |
| `values` | Full state snapshot after each graph node executes |
| `updates` | Only the delta/diff from each node |

### Thread Persistence

Threads persist conversation state in PostgreSQL via the LangGraph checkpointer. Send follow-up messages to the same `thread_id` and the full history is available to the graph.

## Compatible Frontends

This deployment works with:
- [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui) -- point it at `http://localhost:8123`
- [useStream React hook](https://langchain-ai.github.io/langgraphjs/how-tos/use-stream-react/) from `@langchain/langgraph-sdk`
- Any `langgraph_sdk` client (`get_client(url="http://localhost:8123")`)

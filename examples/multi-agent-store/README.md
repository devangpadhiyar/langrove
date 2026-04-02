# Multi-Agent Store -- Advanced Langrove Features

This example deploys two graphs in a single Langrove instance and demonstrates cross-thread memory (store), cron scheduling, interrupt/resume, and multitask strategies.

## What You'll Learn

- Deploying multiple graphs in one `langgraph.json`
- **Store API**: Cross-thread key-value storage with hierarchical namespaces
- **Cron API**: Scheduling periodic graph runs
- **Interrupt/Resume**: Pausing execution at a named node, then resuming
- **Multitask strategies**: reject, interrupt, rollback, enqueue
- Orchestrating a research-then-write pipeline via the SDK

## Project Structure

```
multi-agent-store/
  researcher.py     # Research graph (research -> publish nodes)
  writer.py         # Writer graph (write node)
  langgraph.json    # Two graphs registered
  client.py         # Full pipeline demonstrating all features
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
cd examples/multi-agent-store
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

**3. Start the server:**

```bash
uv run langrove serve
```

**4. Run the client:**

```bash
python client.py
```

## Multiple Graphs

Register multiple graphs in `langgraph.json`:

```json
{
  "graphs": {
    "researcher": "./researcher.py:graph",
    "writer": "./writer.py:graph"
  }
}
```

Each graph gets its own auto-created assistant. Reference them by graph_id in SDK calls:

```python
await client.runs.stream(thread_id, "researcher", input={...})
await client.runs.stream(thread_id, "writer", input={...})
```

## Store API

The store provides cross-thread key-value storage with hierarchical namespaces. Use it to share data between different graphs and threads.

### Namespace Structure

Namespaces are arrays of strings forming a hierarchy:

```
["research", "ai"]           # Research about AI
["research", "quantum"]      # Research about quantum computing
["user", "prefs", "theme"]   # User preferences
```

### Operations

```python
# Write
await client.store.put_item(
    namespace=["research", "ai"],
    key="findings-v1",
    value={"summary": "...", "sources": [...]},
)

# Read
item = await client.store.get_item(namespace=["research", "ai"], key="findings-v1")

# Search by namespace prefix
results = await client.store.search_items(namespace_prefix=["research"], limit=20)

# List namespaces
ns = await client.store.list_namespaces(prefix=["research"], max_depth=2)

# Delete
await client.store.delete_item(namespace=["research", "ai"], key="findings-v1")
```

## Cron API

Schedule graphs to run periodically:

```python
cron = await client.crons.create(
    assistant_id="researcher",
    schedule="0 */6 * * *",        # Every 6 hours
    payload={"messages": [{"role": "user", "content": "..."}]},
)

await client.crons.update(cron["cron_id"], schedule="0 */12 * * *")
await client.crons.update(cron["cron_id"], enabled=False)
await client.crons.delete(cron["cron_id"])
```

## Interrupt / Resume

Pause execution at a named node for human review:

```python
# Interrupt before the "publish" node
async for event in client.runs.stream(
    thread_id, "researcher",
    input={...},
    interrupt_before=["publish"],   # <-- request-time interrupt
):
    ...

# Check state -- next will show ["publish"]
state = await client.threads.get_state(thread_id)

# Resume execution
async for event in client.runs.stream(
    thread_id, "researcher",
    command={"resume": True},       # <-- approve and continue
):
    ...
```

## Multitask Strategies

Control what happens when a new run is created on a busy thread:

| Strategy | Behavior |
|----------|----------|
| `reject` (default) | Returns 409 Conflict |
| `interrupt` | Cancels current run, starts new one |
| `rollback` | Rolls back to last checkpoint, starts new run |
| `enqueue` | Queues new run behind the current one |

```python
await client.runs.stream(
    thread_id, "researcher",
    input={...},
    multitask_strategy="enqueue",
)
```

## Architecture: Research -> Store -> Write Pipeline

This example demonstrates a common multi-agent pattern:

```
1. Researcher graph runs on Thread A
   └── Produces findings

2. Client saves findings to the Store
   └── namespace=["research", "topic"], key="findings"

3. Writer graph runs on Thread B
   └── Reads findings from Store as input context
   └── Produces polished article
```

The Store acts as shared memory between graphs running on different threads, enabling loosely coupled multi-agent workflows.

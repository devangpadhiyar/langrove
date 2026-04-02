# Langrove Examples

Self-contained examples demonstrating how to use Langrove features.

## Prerequisites

All examples require:
- Python 3.12+
- PostgreSQL and Redis running (use `docker compose up postgres redis -d` from the project root)
- Database migrations applied (`uv run alembic upgrade head`)
- An OpenAI API key

## Examples

### [quickstart/](quickstart/)

The minimal path to a running deployment. Covers `langgraph.json` configuration, CORS setup, auto-created assistants, SSE streaming modes, persistent threads, and SDK client usage.

**Langrove features:** `langgraph.json` config, CORS, auto-assistants, schema API, streaming (messages/values), thread persistence, thread state API

### [custom-auth/](custom-auth/)

Secure your deployment with a custom auth handler. Shows the auth handler interface, `langgraph.json` wiring, authenticated SDK clients, and which endpoints bypass auth.

**Langrove features:** `auth.path` config, custom async auth handler, `AuthUser` (identity/role/metadata), auth middleware skip paths, 401 error handling

### [multi-agent-store/](multi-agent-store/)

Deploy multiple graphs with shared memory, scheduled runs, and interrupt/resume flows. Demonstrates the research-then-write pipeline pattern using the Store as cross-thread memory.

**Langrove features:** multiple graphs, Store API (put/get/search/namespaces/delete), Cron API (create/update/search/delete), interrupt/resume (`interrupt_before` + `command`), multitask strategies (reject/interrupt/rollback/enqueue), run search

## Running an Example

```bash
cd examples/<example-name>
cp .env.example .env
# Edit .env and set OPENAI_API_KEY

uv run langrove serve        # Start the server
python client.py               # Run the demo client (in another terminal)
```

## Feature Matrix

| Feature | quickstart | custom-auth | multi-agent-store |
|---------|:----------:|:-----------:|:-----------------:|
| `langgraph.json` config | x | x | x |
| CORS configuration | x | x | x |
| Auto-created assistants | x | | |
| Schema introspection | x | | |
| SSE streaming (messages) | x | x | x |
| SSE streaming (values) | x | | x |
| Persistent threads | x | | |
| Thread state API | x | | x |
| Custom auth handler | | x | |
| Auth middleware | | x | |
| Multiple graphs | | | x |
| Store API | | | x |
| Cron API | | | x |
| Interrupt / Resume | | | x |
| Multitask strategies | | | x |
| Run search | | | x |

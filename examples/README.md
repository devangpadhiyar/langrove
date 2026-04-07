# Langrove Examples

Self-contained examples demonstrating how to use Langrove features.

## Prerequisites

All examples require:
- Python 3.12+
- PostgreSQL and Redis running (use `docker compose up postgres redis -d` from the project root)
- Database migrations applied (`uv run alembic upgrade head`)
- An OpenAI or Anthropic API key

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

### [helios-video-agent/](helios-video-agent/)

Professional video production agent powered by [DeepAgents](https://github.com/langchain-ai/deepagents) and [Helios](https://github.com/BintzGavin/helios/). The agent acts as a creative director, producing ad-quality motion graphics, cinematic presentations, and animated content from natural language briefs. Includes a React frontend with live `<helios-player>` preview.

**Langrove features:** DeepAgents integration (`create_deep_agent`), VFS via StoreBackend, custom tools, HITL interrupt/resume, skills/memory middleware, Store API (cross-thread VFS), React frontend with SSE streaming

**Additional:** GSAP timelines, CSS @keyframes, Canvas/WebGL, Three.js, audio sync, kinetic typography, cinematic transitions, data-driven templates (inputProps)

## Running an Example

```bash
cd examples/<example-name>
cp .env.example .env
# Edit .env and set OPENAI_API_KEY

uv run langrove serve        # Start the server
python client.py               # Run the demo client (in another terminal)
```

## Feature Matrix

| Feature | quickstart | custom-auth | multi-agent-store | helios-video-agent |
|---------|:----------:|:-----------:|:-----------------:|:------------------:|
| `langgraph.json` config | x | x | x | x |
| CORS configuration | x | x | x | x |
| Auto-created assistants | x | | | x |
| Schema introspection | x | | | |
| SSE streaming (messages) | x | x | x | x |
| SSE streaming (values) | x | | x | x |
| Persistent threads | x | | | x |
| Thread state API | x | | x | x |
| Custom auth handler | | x | | |
| Auth middleware | | x | | |
| Multiple graphs | | | x | |
| Store API | | | x | x |
| Cron API | | | x | |
| Interrupt / Resume | | | x | x |
| Multitask strategies | | | x | |
| Run search | | | x | |
| DeepAgents integration | | | | x |
| VFS (StoreBackend) | | | | x |
| Custom tools | | | | x |
| Skills / Memory | | | | x |
| React frontend | | | | x |

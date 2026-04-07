# Helios Video Agent -- Professional Video Production with DeepAgents

This example deploys a **professional video production agent** powered by [DeepAgents](https://github.com/langchain-ai/deepagents) and the [Helios](https://github.com/BintzGavin/helios/) programmatic video engine. The agent acts as a creative director and motion designer, producing ad-quality motion graphics, cinematic presentations, and animated content from natural language briefs.

## What You'll Learn

- Using **DeepAgents** (`create_deep_agent()`) as a LangGraph graph on Langrove
- **VFS (Virtual File System)** via DeepAgents' `StoreBackend` backed by Langrove's PostgreSQL Store
- **Custom tools** injected into DeepAgents (Helios validation, assembly, schema)
- **Skills** loaded via `SkillsMiddleware` for LLM-accessible reference knowledge
- **AGENTS.md** memory for persistent agent persona and workflow
- **Human-in-the-loop** review with interrupt/resume
- React frontend with `useStream()`-style SSE and `<helios-player>` preview

## What The Agent Creates

The LLM designs everything from scratch -- no fixed templates or presets:

- **GSAP timelines** for complex animation choreography
- **CSS @keyframes** for self-contained entrance, exit, and loop animations
- **Canvas 2D** particle systems, generative art, data visualization
- **WebGL/Three.js** 3D effects, shaders, camera animations
- **Kinetic typography** -- character-by-character reveals, morphing, staggered text
- **Cinematic transitions** -- morphs, clip-path reveals, 3D, glitch, liquid, light leaks
- **Audio synchronization** -- beat-matched cuts, voiceover timing, multi-track mixing
- **Data-driven templates** via Helios `inputProps` for scalable ad production

## Architecture

```
User (Chat / SDK Client)
  |
  v
Langrove Server (FastAPI + SSE)
  |
  v
DeepAgents Graph (create_deep_agent)
  |-- write_todos    (planning)
  |-- write_file     (VFS: StoreBackend -> PostgreSQL)
  |-- read_file      (VFS)
  |-- edit_file      (VFS)
  |-- ls/glob/grep   (VFS browsing)
  |-- task           (sub-agent delegation)
  |-- validate_composition  (custom: Helios HTML validation)
  |-- assemble_composition  (custom: build final HTML, HITL interrupt)
  |-- generate_input_schema (custom: HeliosSchema JSON)
  |-- get_helios_api_reference (custom: on-demand API docs)
  |
  v
VFS (StoreBackend -> Langrove Store API -> PostgreSQL)
  /project.json
  /styles/base.css, animations.css
  /scenes/scene_00.html, scene_01.html, ...
  /scripts/timeline.js, effects.js
  /audio/manifest.json
  /dist/index.html  (assembled composition)
  |
  v
Frontend: <helios-player> preview OR CLI: npx helios render
```

## Project Structure

```
helios-video-agent/
  agent.py              # create_deep_agent() with StoreBackend + Helios tools
  helios_tools.py       # Custom tools: validate, assemble, schema, reference
  langgraph.json        # Graph registration
  AGENTS.md             # Creative director persona + workflow
  skills/               # Helios knowledge base (8 skill files)
    SKILL.md            # Master catalog
    composition-anatomy.md
    motion-design.md
    canvas-webgl.md
    cinematic-transitions.md
    audio-sync.md
    input-props-schema.md
    clip-system.md
    rendering-export.md
  client.py             # Python SDK demo
  .env.example          # API key template
  frontend/             # React + Vite + TypeScript
    src/
      App.tsx           # Split layout: chat + preview
      components/
        ChatPanel.tsx   # Message input + streaming
        PreviewPanel.tsx  # <helios-player> / iframe preview
        ToolProgress.tsx  # Tool call progress indicators
        ReviewBar.tsx     # HITL approve / feedback
      hooks/
        useVideoAgent.ts  # SSE streaming hook
      lib/
        store.ts        # Fetch composition from Store API
```

## Setup

### 1. Start infrastructure (from project root)

```bash
docker compose up postgres redis -d
```

### 2. Install dependencies (separate venv with Langrove as local dep)

```bash
cd examples/helios-video-agent
uv sync                              # Creates .venv, installs langrove (editable) + deepagents
uv run alembic upgrade head           # Run migrations using this venv
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set your ANTHROPIC_API_KEY (or OPENAI_API_KEY)
```

### 4. Start the server

```bash
uv run langrove serve
```

### 5. Run the Python client (optional)

```bash
uv run python client.py
```

### 6. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 -- chat panel on the left, preview on the right.

## Example Prompts

**Product Advertisement:**
> Create a 15-second product ad for premium wireless headphones. Cinematic dark theme with electric blue accents and particle effects. Features: noise cancellation, 40-hour battery, spatial audio. Include kinetic typography and a CTA with $299 price. 1920x1080.

**Startup Pitch:**
> Design a 30-second animated pitch video for an AI startup. Clean white background with bold neon gradient accents. Show: problem statement, solution demo, key metrics with animated counters, team, and CTA. Professional typography, data visualization.

**Social Media Story:**
> Make a 10-second Instagram story ad for a coffee brand. Warm earth tones, steam particle effects rising from a cup, kinetic text "Wake Up Beautiful", price pop at the end. 1080x1920 vertical.

**Event Promo:**
> Create a 20-second music festival promo. High energy, glitch transitions, beat-synced cuts at 128 BPM, neon colors on dark, artist names with elastic bounce, date/venue CTA. 1920x1080.

## How It Works

### DeepAgents Integration

`create_deep_agent()` returns a compiled LangGraph graph registered in `langgraph.json`. It comes with:

- **TodoListMiddleware** -- Planning via `write_todos`
- **FilesystemMiddleware** -- VFS operations via `StoreBackend`
- **SkillsMiddleware** -- Loads `skills/` directory into system prompt
- **MemoryMiddleware** -- Loads `AGENTS.md` into system prompt
- **SubAgentMiddleware** -- Delegate via `task` tool
- **SummarizationMiddleware** -- Auto-compacts long conversations
- **HumanInTheLoopMiddleware** -- Interrupts on `assemble_composition`

### VFS via StoreBackend

Files are stored in Langrove's PostgreSQL-backed Store with namespace isolation per thread:

```
Namespace: ("vfs", thread_id)
Key: "/scenes/scene_00.html"
Value: {"content": "<section ...>...</section>"}
```

The agent uses DeepAgents' built-in `write_file`, `read_file`, `edit_file`, `ls`, `glob`, `grep` to manage these files.

### Helios Skills

Eight skill files in `skills/` provide comprehensive Helios reference knowledge:

| Skill | What the LLM Learns |
|-------|---------------------|
| composition-anatomy | HTML structure, data attributes, signals API |
| motion-design | GSAP, WAAPI, CSS @keyframes, spring physics, patterns |
| canvas-webgl | Canvas 2D, Three.js, shaders, particles |
| cinematic-transitions | Morphs, reveals, 3D, glitch, liquid, cinematic |
| audio-sync | Tracks, fading, beat-sync, voiceover, visualization |
| input-props-schema | Data-driven templates, asset types, binding |
| clip-system | Multi-track, layering, sequencing utilities |
| rendering-export | Renderer modes, codecs, CLI, distributed rendering |

These are **reference knowledge, not constraints**. The LLM designs everything from scratch.

### Human-in-the-Loop

The agent interrupts at `assemble_composition()`. The client/frontend can:

- **Preview** the composition via `<helios-player>` or iframe
- **Approve** to finalize (resume with `{resume: true}`)
- **Send feedback** to iterate (resume with `{resume: {feedback: "..."}}`)

## Rendering to Video

After the composition is approved, render with the Helios CLI:

```bash
# Save the composition HTML to a local file first, then:
npx helios render composition.html -o output.mp4 --width 1920 --height 1080 --fps 30

# Vertical (stories/reels)
npx helios render composition.html -o story.mp4 --width 1080 --height 1920

# Square (social feed)
npx helios render composition.html -o square.mp4 --width 1080 --height 1080
```

Or use client-side export in the browser with `@helios-project/core`'s `ClientSideExporter`.

## Compatible Frontends

This deployment works with:
- The included React frontend (recommended)
- [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui) -- point at `http://localhost:8123`
- [useStream React hook](https://langchain-ai.github.io/langgraphjs/how-tos/use-stream-react/) from `@langchain/langgraph-sdk`
- Any `langgraph_sdk` client (`get_client(url="http://localhost:8123")`)

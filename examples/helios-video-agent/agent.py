"""Helios Video Production Agent — professional video composition with DeepAgents.

This agent acts as a creative director and motion designer, producing
professional-grade video compositions (advertisements, motion graphics,
cinematic presentations) using the Helios programmatic video engine.

It uses DeepAgents for:
  - Planning (write_todos)
  - Virtual filesystem via StoreBackend (write_file, read_file, edit_file, ls, glob, grep)
  - Sub-agent delegation (task)
  - Context management and summarization

And custom Helios tools for:
  - Composition validation
  - Final assembly into self-contained HTML
  - inputProps schema generation
  - Helios API reference lookup

Uses CompositeBackend:
  - Default: StoreBackend (DB-backed persistent VFS for agent file operations)
  - /skills/: FilesystemBackend (local disk for static skill files)
  - /AGENTS.md: FilesystemBackend (local disk for agent memory)

The store is provided at runtime by Langrove's RunExecutor via graph.astream(store=...).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StoreBackend

from helios_tools import _vfs_namespace, helios_tools

_example_dir = Path(__file__).parent

SYSTEM_PROMPT = """\
You are a senior creative director and motion systems architect. \
You produce premium video compositions using the Helios programmatic video engine. \
Your output is indistinguishable from top-tier agency work.

Helios drives the browser's NATIVE animation engine — CSS, WAAPI, GSAP — \
not JavaScript simulation. It uses @helios-project/core for timeline control \
and renders via DOM mode (CSS/WAAPI) or Canvas mode (WebGL/Canvas).

## Mandatory Workflow — Think, Read, Then Act

### Step 1: Think
Write out your creative plan:
- What video type? (promo, explainer, demo, social clip, launch, testimonial)
- Duration, aspect ratio, mood, audience
- Scene breakdown with visual techniques per scene
- Which "wow effect" — particles, 3D, generative art, kinetic typography

### Step 2: Read Skills
You MUST read the relevant skill files BEFORE writing any code:
- ALWAYS read: `skills/helios-skills/guided/motion-design-rules/SKILL.md`
- ALWAYS read: `skills/helios-skills/workflows/create-composition/SKILL.md`
- Read the matching guided workflow (promo-video, explainer-video, product-demo, \
social-clip, launch-announcement, or testimonial-video)
- Read integration skills as needed (gsap, threejs, canvas, vanilla, etc.)

Do NOT assume you know the skill contents. They contain exact patterns, \
constraints, and the Helios API that you must follow.

### Step 3: Act
Execute following the patterns from skill files. Every composition MUST:
- Create a Helios instance: `new Helios({ duration, fps, width, height, autoSyncAnimations: true })`
- Bind timeline: `helios.bindToDocumentTimeline()`
- Expose to window: `window.helios = helios`
- Subscribe for updates: `helios.subscribe((state) => { ... })`

### Step 4: Validate & Assemble
Call validate_composition() then assemble_composition().

## Motion Design Rules (Mandatory)

- **Anti-slideshow**: Global elements (background, particles, logo) persist across scenes. \
They morph and evolve — never disappear and reappear.
- **4+ visual layers**: Void (base gradient) → Texture (noise/drift) → Context (shapes/particles) → Hero (text/content)
- **Global easing personality**: Pick ONE easing for the whole video (circOut for tech, \
easeInOut for luxury, spring for playful, backOut for bold)
- **Choreography**: Nothing appears all at once. Entrance order: background → context → hero → details. \
Stagger 50-150ms depending on energy.
- **Transition continuity**: Scenes crossfade with 200ms+ overlap. Global elements stay continuous. \
Never hard-cut. Never full-black gaps.
- **Squint test**: At any random frame, the most important element must be instantly identifiable.

## File Structure

Write /composition.html as the entry point. For complex compositions, \
split JS into separate files that composition.html imports:

- /composition.html — entry HTML with inline <style> and <script type="module" src="./src/main.js">
- /src/main.js — Helios init, GSAP timeline, subscribe
- /src/effects.js — Canvas particles, generative art (optional)
- /project.json — {title, fps, duration, width, height}

For simpler compositions, inline everything in composition.html.
Always write /project.json with metadata.

## Technical Essentials

- Helios compositions use `@helios-project/core` — import Helios class
- CSS animations sync automatically with `autoSyncAnimations: true`
- GSAP: create paused timeline, seek via `tl.seek(state.currentFrame / fps)` in subscribe
- Audio: use `<audio data-helios-track-id="..." data-helios-fade-in="..." data-helios-fade-out="...">`
- Render: `npx helios render ./composition.html -o output.mp4`
- DOM mode for CSS/WAAPI compositions, Canvas mode for WebGL/Canvas
- No randomness — all motion must be deterministic (frame-based)

Read your AGENTS.md memory for the full creative playbook and standards.\
"""


def _make_backend(_rt: Any) -> CompositeBackend:
    """Create a CompositeBackend routing skills/memory to local disk, everything else to DB store.

    - Default (StoreBackend): All agent file operations (write_file, read_file, etc.)
      go to PostgreSQL via LangGraph's AsyncPostgresStore. Each thread gets isolated
      namespace via _vfs_namespace. Store is obtained at call time via get_store().
    - /local/: FilesystemBackend reads skills and AGENTS.md from local disk.
    """
    fs = FilesystemBackend(root_dir=_example_dir, virtual_mode=True)
    store = StoreBackend(namespace=_vfs_namespace)
    return CompositeBackend(
        default=store,
        routes={
            "/local/": fs,
        },
    )


graph = create_deep_agent(
    model="anthropic:claude-sonnet-4-20250514",
    system_prompt=SYSTEM_PROMPT,
    tools=helios_tools,
    backend=_make_backend,
    skills=["/local/skills/"],
    memory=["/local/AGENTS.md"],
    interrupt_on={"assemble_composition": True},
)

# Langfuse observability — auto-enabled when LANGFUSE_SECRET_KEY is set
if os.environ.get("LANGFUSE_SECRET_KEY"):
    from langfuse.langchain import CallbackHandler  # noqa: E402

    graph = graph.with_config({"callbacks": [CallbackHandler()]})

"""Helios-specific tools for the video production agent.

These tools handle structural concerns — validation, assembly, schema generation,
and API reference. The LLM does all creative work (HTML/CSS/JS design) using
DeepAgents' built-in filesystem tools (write_file, read_file, edit_file).
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.tools import tool


def _vfs_namespace(_ctx: Any) -> tuple[str, ...]:
    """Namespace factory: isolate VFS files per thread using thread_id from config."""
    from langgraph.utils.config import get_config

    cfg = get_config()
    thread_id = cfg.get("configurable", {}).get("thread_id", "default")
    return ("vfs", str(thread_id))


# ---------------------------------------------------------------------------
# Reference data — Helios API topics
# ---------------------------------------------------------------------------

_HELIOS_REFERENCES: dict[str, str] = {
    "core": """\
## Helios Core API

```javascript
import { Helios } from '@helios-project/core';

const helios = new Helios({
  duration: 30,             // seconds
  fps: 30,
  width: 1920,
  height: 1080,
  autoSyncAnimations: true, // Sync CSS/WAAPI automatically
  inputProps: { title: "Hello" },
  schema: { type: 'object', properties: { title: { type: 'string' } } }
});

// CRITICAL — these 3 lines are mandatory:
helios.bindToDocumentTimeline();  // Allows Renderer/Player to drive
window.helios = helios;            // Allows detection
helios.subscribe((state) => {      // Frame-driven updates
  const { currentFrame, fps, inputProps } = state;
  // Draw, update DOM, seek GSAP, etc.
});

// Playback control
helios.play(); helios.pause(); helios.seek(frame);
helios.setPlaybackRate(2.0);

// Signals (reactive)
helios.currentFrame  // ReadonlySignal<number>
helios.isPlaying     // ReadonlySignal<boolean>
helios.inputProps    // ReadonlySignal<object>
```
""",
    "frame-timing": """\
## Frame Timing Math

```
total_frames = fps * duration_seconds
frame_for_time = time_seconds * fps
time_for_frame = frame / fps

// Progress within a scene:
const time = state.currentFrame / state.fps;
const progress = time / duration;

// Scene timing (example: 0-5s, 5-12s, 12-20s):
const sceneStart = 5; // seconds
const sceneEnd = 12;
if (time >= sceneStart && time < sceneEnd) {
  const localProgress = (time - sceneStart) / (sceneEnd - sceneStart);
  // 0.0 to 1.0 within this scene
}
```
""",
    "gsap-sync": """\
## GSAP Timeline Sync with Helios

```javascript
import { Helios } from '@helios-project/core';

const helios = new Helios({ duration: 10, fps: 30 });
helios.bindToDocumentTimeline();
window.helios = helios;

// GSAP timeline MUST be paused
const tl = gsap.timeline({ paused: true });
tl.to('.title', { opacity: 1, y: 0, duration: 0.6, ease: 'power3.out' });
tl.to('.subtitle', { opacity: 1, duration: 0.4 }, '-=0.2');

// Sync GSAP to Helios via subscribe
helios.subscribe((state) => {
  const timeInSeconds = state.currentFrame / state.fps;
  tl.seek(timeInSeconds);
});
```

Rules: always paused:true, always tl.seek(), never requestAnimationFrame.
GSAP CDN: https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js
""",
    "audio": """\
## Audio in Helios

Helios auto-discovers <audio>/<video> elements in the DOM:

```html
<audio
  data-helios-track-id="bgm"
  data-helios-offset="0"
  data-helios-fade-in="2"
  data-helios-fade-out="3"
  data-helios-fade-easing="quad.in"
  src="music.mp3"
></audio>
```

Supported fade easings: linear, quad.in, quad.out, quad.inOut,
cubic.in, cubic.out, cubic.inOut, sine.in, sine.out, sine.inOut

For rendering, audio tracks are auto-discovered and included.
""",
    "canvas": """\
## Canvas Rendering with Helios

```javascript
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
canvas.width = 1920; canvas.height = 1080;

const helios = new Helios({ duration: 10, fps: 30 });
helios.bindToDocumentTimeline();
window.helios = helios;

helios.subscribe((state) => {
  const time = state.currentFrame / state.fps;
  ctx.clearRect(0, 0, 1920, 1080);
  // Draw particles, gradients, effects based on time
});
```

For Three.js, subscribe and call renderer.render(scene, camera) each frame.
Render with: npx helios render composition.html -o output.mp4 --mode canvas
""",
    "animation-helpers": """\
## Helios Animation Helpers

```javascript
import { interpolate, spring, series, stagger, shift } from '@helios-project/core';

// Interpolate: map value across ranges
const opacity = interpolate(frame, [0, 30], [0, 1], { extrapolateRight: 'clamp' });

// Spring physics
const scale = spring({ frame, fps: 30, from: 0, to: 1,
  config: { stiffness: 100, damping: 10 } });

// Series: chain items sequentially
const timed = series([
  { id: 'a', durationInFrames: 30 },
  { id: 'b', durationInFrames: 60, offset: -10 }  // 10-frame overlap
], 0);

// Stagger: offset start times
const staggered = stagger([{ id: 'a' }, { id: 'b' }, { id: 'c' }], 5);
// Results: a@0, b@5, c@10

// Shift: move all start times
const shifted = shift(items, 30);
```
""",
    "input-props": """\
## inputProps — Data-Driven Templates

```javascript
const helios = new Helios({
  duration: 10, fps: 30,
  schema: {
    type: 'object',
    properties: {
      headline: { type: 'string', default: 'Hello' },
      price: { type: 'number', minimum: 0 },
      productImage: { type: 'image' },
      primaryColor: { type: 'color', default: '#FF0000' }
    }
  },
  inputProps: { headline: 'Hello', price: 29.99 }
});

// Access in subscribe:
helios.subscribe((state) => {
  document.querySelector('.headline').textContent = state.inputProps.headline;
});

// Update dynamically:
helios.setInputProps({ headline: 'New Title' }); // Validates against schema
```

Types: string, number, boolean, color, image, video, audio, font, model, json, shader
""",
    "rendering": """\
## Rendering Helios Compositions

CLI:
```bash
npx helios render ./composition.html -o output.mp4
npx helios render ./composition.html -o output.mp4 --mode dom   # CSS/WAAPI
npx helios render ./composition.html -o output.mp4 --mode canvas  # WebGL/Canvas
```

DOM mode: best for CSS animations, WAAPI, HTML/DOM elements
Canvas mode: best for Three.js, Pixi.js, Canvas 2D
Audio tracks are auto-discovered from DOM <audio> elements.
""",
}


# ---------------------------------------------------------------------------
# Tool: validate_composition
# ---------------------------------------------------------------------------


@tool
async def validate_composition() -> str:
    """Validate the composition files in VFS against Helios requirements.

    Reads /composition.html and all src/*.js, src/*.css files from VFS,
    then checks for Helios runtime integration, animation setup, visual
    layering, and creative quality.

    Call this BEFORE assemble_composition() to catch issues early.

    Returns:
        Validation report — 'VALID' if no errors, or a list of issues found.
    """
    from deepagents.backends import StoreBackend

    backend = StoreBackend(namespace=_vfs_namespace)

    async def _read(path: str) -> str:
        result = await backend.aread(path)
        if result.error:
            return ""
        fd = result.file_data or {}
        content = fd.get("content", "")
        return "\n".join(content) if isinstance(content, list) else content

    # Collect all file contents from VFS
    parts: list[str] = []

    # Primary: /composition.html
    comp = await _read("/composition.html")
    if comp:
        parts.append(comp)

    # Secondary: any src/ files (JS, CSS, TS)
    for pattern, root in [
        ("**/*.js", "/src"),
        ("**/*.ts", "/src"),
        ("**/*.css", "/src"),
    ]:
        glob_result = await backend.aglob(pattern, root)
        for info in glob_result.matches or []:
            content = await _read(info["path"])
            if content:
                parts.append(content)

    # Fallback: old fragment structure (/styles/, /scenes/, /scripts/)
    if not parts:
        for pattern, root in [
            ("**/*.css", "/styles"),
            ("**/*.html", "/scenes"),
            ("**/*.js", "/scripts"),
        ]:
            glob_result = await backend.aglob(pattern, root)
            for info in glob_result.matches or []:
                content = await _read(info["path"])
                if content:
                    parts.append(content)

    # Also read project.json for metadata
    project_content = await _read("/project.json")
    if project_content:
        parts.append(project_content)

    html = "\n".join(parts)

    if not html.strip():
        return "INVALID — No files found in VFS. Write project files before validating."
    errors: list[str] = []
    warnings: list[str] = []

    # --- Helios Runtime Checks ---

    # Check for Helios core import
    has_helios_import = bool(re.search(r"@helios-project/core|from\s+['\"].*helios", html))
    if not has_helios_import:
        warnings.append(
            "No @helios-project/core import detected. "
            "Composition needs `import { Helios } from '@helios-project/core'`."
        )

    # Check for Helios instance creation
    has_new_helios = bool(re.search(r"new\s+Helios\s*\(", html))
    if not has_new_helios:
        errors.append(
            "No `new Helios(...)` instance created. "
            "Every composition must create a Helios instance with duration/fps."
        )

    # Check for bindToDocumentTimeline (CRITICAL for Renderer/Player)
    has_bind = "bindToDocumentTimeline" in html
    if not has_bind:
        errors.append(
            "Missing `helios.bindToDocumentTimeline()`. "
            "This is CRITICAL — without it, the Renderer and Player cannot drive the composition."
        )

    # Check for window.helios exposure (CRITICAL for detection)
    has_window_helios = bool(re.search(r"window\s*\.\s*helios\s*=", html))
    if not has_window_helios:
        errors.append(
            "Missing `window.helios = helios`. "
            "This is CRITICAL — the Renderer/Player needs this to detect the Helios instance."
        )

    # Check for subscribe (needed for frame-driven updates)
    has_subscribe = ".subscribe(" in html
    if not has_subscribe:
        warnings.append(
            "No `helios.subscribe(...)` found. "
            "Subscribe to state changes for Canvas/GSAP/DOM updates."
        )

    # Check for fabricated/non-existent Helios API methods
    _FAKE_APIS = {
        "addEvent": "Use helios.subscribe() with time checks instead: "
        "if (time >= X && time < Y) { ... }",
        "useVideoFrame": "Use helios.subscribe((state) => { ... }) instead.",
        "onFrame": "Use helios.subscribe((state) => { ... }) instead.",
        "registerFrame": "Use helios.subscribe((state) => { ... }) instead.",
        "setFrame": "Use helios.seek(frame) instead.",
        "addEventListener": "Use helios.subscribe() for frame updates, "
        "or helios.addMarker() for timeline markers.",
        "onUpdate": "Use helios.subscribe((state) => { ... }) instead.",
        "registerCallback": "Use helios.subscribe((state) => { ... }) instead.",
        "addTimeline": "Use helios.subscribe() + GSAP tl.seek() pattern instead.",
        "connectToParent": "Not needed — use bindToDocumentTimeline() + window.helios.",
    }
    for method, fix in _FAKE_APIS.items():
        pattern = rf"helios\.{method}\s*\("
        if re.search(pattern, html):
            errors.append(f"helios.{method}() does NOT exist in the Helios API. {fix}")

    # Check for autoSyncAnimations (needed for CSS/WAAPI)
    has_auto_sync = "autoSyncAnimations" in html
    keyframes_count = len(re.findall(r"@keyframes\s+\w+", html))
    if keyframes_count > 0 and not has_auto_sync:
        warnings.append(
            "CSS @keyframes found but `autoSyncAnimations: true` not set. "
            "CSS animations won't sync with Helios scrubbing without this."
        )

    # Check for GSAP integration
    if "gsap" in html.lower():
        has_paused = "paused: true" in html or "paused:true" in html
        if not has_paused:
            warnings.append(
                "GSAP timeline detected without `paused: true`. "
                "GSAP timelines MUST be paused — Helios drives them via tl.seek()."
            )
        has_seek = ".seek(" in html
        if not has_seek:
            warnings.append(
                "GSAP detected but no `tl.seek()` call found. "
                "Sync GSAP to Helios via `tl.seek(state.currentFrame / fps)` in subscribe."
            )

    # --- Creative Quality Checks ---
    creative_warnings: list[str] = []

    # Google Fonts
    has_font_import = bool(re.search(r"@import\s+url\(['\"]https://fonts\.googleapis", html))
    has_font_face = bool(re.search(r"@font-face", html))
    if not has_font_import and not has_font_face:
        creative_warnings.append(
            "No Google Fonts (@import) or @font-face detected. "
            "Load 2+ font families (display + body) for professional typography."
        )

    # Animation presence
    has_waapi = ".animate(" in html
    has_gsap = "gsap" in html.lower()
    if keyframes_count == 0 and not has_waapi and not has_gsap:
        creative_warnings.append(
            "No CSS @keyframes, WAAPI .animate(), or GSAP detected. "
            "Composition needs animation — use CSS, WAAPI, or GSAP."
        )

    # Visual layering (z-index depth)
    z_indices = re.findall(r"z-index\s*:\s*(\d+)", html)
    unique_layers = len(set(z_indices))
    if unique_layers < 3:
        creative_warnings.append(
            f"Only {unique_layers} z-index layer(s). Motion design rules require 4+ layers: "
            "Void (base), Texture (drift), Context (shapes), Hero (content)."
        )

    # CSS custom properties (design system)
    custom_props = len(set(re.findall(r"--[\w-]+", html)))
    if custom_props < 5:
        creative_warnings.append(
            f"Only {custom_props} CSS custom properties. Define 5+ palette variables "
            "(--color-bg, --color-primary, --color-accent, --color-text, etc.)."
        )

    # Atmospheric effects
    has_blend = "mix-blend-mode" in html
    has_backdrop = "backdrop-filter" in html
    has_canvas = "<canvas" in html.lower()
    has_gradient = bool(re.search(r"(linear|radial|conic)-gradient", html))
    if not has_blend and not has_backdrop and not has_canvas and not has_gradient:
        creative_warnings.append(
            "No atmospheric effects found (blend modes, backdrop-filter, canvas, gradients). "
            "Add visual depth — the background should never be flat."
        )

    # Stagger check
    has_stagger = "stagger" in html
    has_animation_delay = "animation-delay" in html
    has_css_stagger = bool(re.search(r"--[\w-]*delay|--[\w-]*i\)", html))
    if not has_stagger and not has_animation_delay and not has_css_stagger:
        creative_warnings.append(
            "No stagger pattern detected (GSAP stagger, animation-delay, or CSS var offsets). "
            "Elements should never appear all at once — stagger entrances 50-150ms."
        )

    # Build report
    if not errors and not warnings and not creative_warnings:
        return "VALID — Composition passes all structural and creative quality checks."

    report_parts: list[str] = []
    if errors:
        report_parts.append("ERRORS:")
        for e in errors:
            report_parts.append(f"  - {e}")
    if warnings:
        report_parts.append("STRUCTURAL WARNINGS:")
        for w in warnings:
            report_parts.append(f"  - {w}")
    if creative_warnings:
        report_parts.append("CREATIVE QUALITY WARNINGS:")
        for cw in creative_warnings:
            report_parts.append(f"  - {cw}")

    status = "INVALID" if errors else "VALID (with warnings)"
    return f"{status}\n" + "\n".join(report_parts)


# ---------------------------------------------------------------------------
# Tool: assemble_composition
# ---------------------------------------------------------------------------


@tool
async def assemble_composition() -> str:
    """Prepare the Helios composition for preview and rendering.

    If the agent wrote /composition.html (recommended Helios pattern), this
    tool writes metadata.json for the frontend and signals readiness.

    If the agent used the legacy fragment pattern (/styles/, /scenes/,
    /scripts/), this tool assembles them into a single self-contained HTML.

    In both cases, writes to /dist/index.html (for frontend preview) and
    /dist/metadata.json (for dimensions/timing). Triggers human review.

    Returns:
        Assembly status with quality summary.
    """
    from deepagents.backends import StoreBackend

    backend = StoreBackend(namespace=_vfs_namespace)

    async def read(path: str) -> str | None:
        result = await backend.aread(path)
        if result.error:
            return None
        fd = result.file_data or {}
        content = fd.get("content", "")
        return "\n".join(content) if isinstance(content, list) else content

    # --- Read project metadata ---
    project_raw = await read("/project.json")
    project: dict[str, Any] = {}
    if project_raw:
        import contextlib

        with contextlib.suppress(json.JSONDecodeError):
            project = json.loads(project_raw)

    title = project.get("title", "Helios Composition")
    fps = project.get("fps", 30)
    duration = project.get("duration", 10)
    width = project.get("width", 1920)
    height = project.get("height", 1080)

    store = backend._get_store()
    namespace = backend._get_namespace()

    # --- Check for /composition.html (new Helios pattern) ---
    composition_html = await read("/composition.html")

    if composition_html:
        # Agent wrote a proper Helios composition — no assembly needed.
        # Just copy to /dist/index.html for frontend compatibility.
        html = composition_html
        await store.aput(namespace, "/dist/index.html", {"content": html, "encoding": "utf-8"})
    else:
        # Fallback: legacy fragment assembly (/styles/, /scenes/, /scripts/)
        css_parts: list[str] = []
        for path in ("/styles/base.css", "/styles/animations.css"):
            content = await read(path)
            if content:
                css_parts.append(f"/* {path} */\n{content}")
        glob_result = await backend.aglob("**/*.css", "/styles")
        for info in glob_result.matches or []:
            p = info["path"]
            if p not in ("/styles/base.css", "/styles/animations.css"):
                content = await read(p)
                if content:
                    css_parts.append(f"/* {p} */\n{content}")

        scene_glob = await backend.aglob("**/*.html", "/scenes")
        scene_paths = sorted(info["path"] for info in scene_glob.matches or [])
        scene_parts: list[str] = []
        for p in scene_paths:
            content = await read(p)
            if content:
                scene_parts.append(f"<!-- {p} -->\n{content}")

        js_parts: list[str] = []
        for path in ("/scripts/main.js", "/scripts/timeline.js", "/scripts/effects.js"):
            content = await read(path)
            if content:
                js_parts.append(f"/* {path} */\n{content}")
        js_glob = await backend.aglob("**/*.js", "/scripts")
        for info in js_glob.matches or []:
            p = info["path"]
            if p not in ("/scripts/main.js", "/scripts/timeline.js", "/scripts/effects.js"):
                content = await read(p)
                if content:
                    js_parts.append(f"/* {p} */\n{content}")

        css_block = "\n\n".join(css_parts)
        scenes_block = "\n\n".join(scene_parts)
        js_block = "\n\n".join(js_parts)
        all_content = css_block + "\n" + scenes_block + "\n" + js_block

        cdn_scripts: list[str] = []
        if "gsap" in all_content.lower():
            cdn_scripts.append(
                '<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>'
            )
        if "THREE" in all_content or "three.js" in all_content.lower():
            cdn_scripts.append(
                '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'
            )
        cdn_block = "\n  ".join(cdn_scripts)

        has_helios_init = "new Helios(" in all_content or "@helios-project/core" in all_content
        helios_init = ""
        if not has_helios_init:
            helios_init = (
                f"import {{ Helios }} from 'https://esm.sh/@helios-project/core';\n\n"
                f"const helios = new Helios({{ duration: {duration}, fps: {fps}, "
                f"width: {width}, height: {height}, autoSyncAnimations: true }});\n"
                f"helios.bindToDocumentTimeline();\nwindow.helios = helios;\n\n"
            )

        html = (
            f"<!DOCTYPE html>\n<html>\n<head>\n"
            f'  <meta charset="utf-8">\n'
            f'  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"  <title>{title}</title>\n  {cdn_block}\n  <style>\n"
            f"*, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}\n"
            f"html, body {{ width: 100%; height: 100%; overflow: hidden; background: #000; }}\n\n"
            f"{css_block}\n  </style>\n</head>\n<body>\n\n"
            f"{scenes_block}\n\n"
            f'  <script type="module">\n{helios_init}{js_block}\n  </script>\n'
            f"</body>\n</html>"
        )

        await store.aput(namespace, "/dist/index.html", {"content": html, "encoding": "utf-8"})

    # --- Write metadata.json for frontend ---
    metadata = json.dumps(
        {"title": title, "width": width, "height": height, "fps": fps, "duration": duration}
    )
    await store.aput(namespace, "/dist/metadata.json", {"content": metadata, "encoding": "utf-8"})

    # --- Quality summary ---
    keyframes_count = len(re.findall(r"@keyframes\s+\w+", html))
    gsap_tweens = len(re.findall(r"\.(from|to|fromTo|set)\s*\(", html))
    z_layers = len(set(re.findall(r"z-index\s*:\s*(\d+)", html)))
    custom_props = len(set(re.findall(r"--[\w-]+", html)))

    quality_items = [
        f"@keyframes: {keyframes_count}",
        f"GSAP tweens: {gsap_tweens}",
        f"Z-layers: {z_layers}",
        f"CSS vars: {custom_props}",
        f"Canvas: {'Y' if '<canvas' in html.lower() else 'N'}",
        f"Blend: {'Y' if 'mix-blend-mode' in html else 'N'}",
        f"Stagger: {'Y' if 'stagger' in html or 'animation-delay' in html else 'N'}",
        f"Fonts: {'Y' if re.search(r'@import\\s+url|@font-face', html) else 'N'}",
        f"Helios: {'Y' if 'new Helios(' in html else 'N'}",
        f"Bound: {'Y' if 'bindToDocumentTimeline' in html else 'N'}",
    ]

    return (
        f"ASSEMBLY COMPLETE — '{title}' ({width}x{height}, {fps}fps, {duration}s)\n\n"
        f"Quality: {' | '.join(quality_items)}\n\n"
        "Preview is now available. Human review triggered.\n\n"
        "Render: npx helios render ./composition.html -o output.mp4"
    )


# ---------------------------------------------------------------------------
# Tool: generate_input_schema
# ---------------------------------------------------------------------------


@tool
def generate_input_schema(fields: list[dict[str, Any]]) -> str:
    """Generate a HeliosSchema JSON for data-driven video templates.

    Creates a schema.json that defines inputProps for the composition,
    enabling dynamic content substitution (text, images, colors, etc.)
    without modifying the composition code.

    Args:
        fields: List of field definitions. Each field dict should have:
            - name (str): Field identifier (e.g., 'headline', 'productImage')
            - type (str): One of 'string', 'number', 'boolean', 'image',
              'video', 'audio', 'font', 'model', 'json', 'shader', 'array', 'object'
            - title (str): Human-readable label
            - description (str, optional): Help text
            - default (any, optional): Default value
            - constraints (dict, optional): Type-specific constraints like
              minimum, maximum, step, pattern, enum, minLength, maxLength,
              minItems, maxItems

    Returns:
        The generated HeliosSchema JSON string.
    """
    props: dict[str, Any] = {}

    for field in fields:
        prop: dict[str, Any] = {"type": field["type"]}

        if "title" in field:
            prop["title"] = field["title"]
        if "description" in field:
            prop["description"] = field["description"]
        if "default" in field:
            prop["default"] = field["default"]

        # Merge constraints
        constraints = field.get("constraints", {})
        for key in (
            "minimum",
            "maximum",
            "step",
            "pattern",
            "enum",
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
            "items",
            "properties",
        ):
            if key in constraints:
                prop[key] = constraints[key]

        props[field["name"]] = prop

    schema = {
        "type": "object",
        "title": "Composition Input Schema",
        "description": "Dynamic input properties for this Helios composition",
        "props": props,
    }

    schema_json = json.dumps(schema, indent=2)

    return (
        f"Generated HeliosSchema with {len(fields)} field(s).\n"
        f"Write this to /schema.json using write_file:\n\n{schema_json}"
    )


# ---------------------------------------------------------------------------
# Tool: get_helios_api_reference
# ---------------------------------------------------------------------------


@tool
def get_helios_api_reference(topic: str) -> str:
    """Get a concise reference for a specific Helios API topic.

    Use this when you need a quick refresher on a specific Helios API
    during composition design. Saves context vs. re-reading full skill files.

    Args:
        topic: One of: 'core', 'frame-timing', 'gsap-sync',
               'audio', 'canvas', 'animation-helpers',
               'input-props', 'rendering'

    Returns:
        Concise reference documentation for the requested topic.
    """
    if topic in _HELIOS_REFERENCES:
        return _HELIOS_REFERENCES[topic]

    available = ", ".join(sorted(_HELIOS_REFERENCES.keys()))
    return f"Unknown topic '{topic}'. Available topics: {available}"


# ---------------------------------------------------------------------------
# Export all tools
# ---------------------------------------------------------------------------

helios_tools = [
    validate_composition,
    assemble_composition,
    generate_input_schema,
    get_helios_api_reference,
]

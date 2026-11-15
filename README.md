# DiagramForge AI

Describe a system in plain English and get editable UML, ERD, DFD, architecture, BPMN, network, security and DevOps diagrams.

**Stack:** Flask + REST, vanilla JS, Mermaid.js, PlantUML (via a server), bpmn-js, Gemini/Groq adapters, MongoDB Atlas (PyMongo), Render.

## How it works

1. **Stage 1, analysis** (`services/prompt_analyzer.py`): the LLM extracts actors, entities, components, tables, relationships, flows, assumptions and recommends diagram types as JSON. Output is normalised, and invalid type keys are dropped.
2. **Stage 2, generation** (`services/diagram_generator.py`): the analysis plus a per-type prompt (syntax rules for that diagram) produce `{title, explanation, source, assumptions}`.
3. **Validation + auto-fix**: the server validates the source (`services/diagram_validator.py`) and asks the LLM to repair problems, at most **3** times. If it is still invalid the API returns `422`, never a "successful" broken diagram. `validation_status` is set by the server, not claimed by the model.
4. **Browser render check**: Python can't run Mermaid's real parser, so the browser runs `mermaid.parse()` and, on failure, calls `/api/fix-diagram` (max 3 attempts, enforced server-side).
5. **Complete documentation**: one shared analysis feeds up to 10 diagrams (default: architecture, use case, DFD 0/1, ERD, class, sequence, activity, component, deployment) so they stay consistent. Failures are reported per diagram.

45 diagram types are catalogued in `services/diagram_types.py` and mapped to an engine: Mermaid (flowcharts, sequence, class, ER, state, DFD, architecture, network, security, DevOps), PlantUML (use case, object, activity, component, deployment, package, composite structure, communication, interaction overview, timing, profile, C4, swimlane), BPMN.io (BPMN).

## Setup (local)

```bash
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# macOS/Linux
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # add GEMINI_API_KEY and/or GROQ_API_KEY, SECRET_KEY
python app.py               # http://127.0.0.1:5000
```

Without `MONGODB_URI`, development mode uses an **in-memory store** (data is lost on restart; `/api/health` reports `db_mode: "memory"`). It is disabled in production.

**MongoDB Atlas:** create a free cluster, a database user, allow your IP (or `0.0.0.0/0` for Render), copy the connection string into `MONGODB_URI`. Collections (`users`, `projects`, `diagrams`, `diagram_history`) and indexes are created automatically.

**PlantUML:** diagram text is sent to `PLANTUML_SERVER` (default: the public server). For private data self-host: `docker run -d -p 8080:8080 plantuml/plantuml-server:jetty` and set `PLANTUML_SERVER=http://localhost:8080`.

## Deploy on Render

1. Push to GitHub, create a **Web Service** (or use `render.yaml`).
2. Build: `pip install -r requirements.txt`. Start: `gunicorn app:app --workers 2 --threads 4 --timeout 300` (long timeout is needed for multi-diagram generation).
3. Env vars: `FLASK_ENV=production`, `SECRET_KEY`, `MONGODB_URI`, `GEMINI_API_KEY` and/or `GROQ_API_KEY`, optionally `PLANTUML_SERVER`.

## API

| Method | Path | Notes |
|---|---|---|
| POST | `/api/analyze-prompt` | Stage 1 |
| POST | `/api/generate-diagram` | Stages 1+2 (accepts a prior `analysis`); `save:true` persists for logged-in users |
| POST | `/api/generate-project-diagrams` | Multi-diagram set |
| POST | `/api/validate-diagram`, `/api/fix-diagram` | Validate / repair (attempt ≤ 3) |
| POST | `/api/detect-type` | Keyword preview, no LLM |
| POST | `/api/render-plantuml` | Validated PlantUML → sanitized SVG/PNG |
| GET/POST | `/api/projects`, `/api/diagrams` | CRUD, user-scoped |
| GET/PUT/DELETE | `/api/diagrams/<id>` | PUT versions the source into history |
| GET | `/api/diagrams/<id>/history`, POST `/restore` | Version history |
| GET | `/api/diagrams/<id>/export?format=source\|json\|svg\|png` | svg/png server-side only for PlantUML |
| POST | `/api/auth/register\|login\|logout`, GET `/me` | Session auth, hashed passwords |

Mutating calls require header `X-Requested-With: DiagramForge` (CSRF defence; the bundled JS sends it).

## Security notes

Keys only in env vars and never sent to the browser; passwords hashed (Werkzeug scrypt); every user query filtered by `user_id`; request size limit; per-user/IP rate limits (in-memory, **per worker**, use Redis for shared limits); CSP with no inline scripts; Mermaid `securityLevel: strict`, `click`/init security directives rejected; PlantUML includes limited to stdlib `<...>`, no URL/file/env access; SVG sanitised server-side and with DOMPurify; BPMN XML with DOCTYPE/entities rejected; generated code is never executed.

## Export

SVG, PNG (1-4×, auto-reduced past browser canvas limits) and PDF are produced in the browser from the visible diagram. The PDF embeds a high-resolution **raster**, not vector. Source downloads: `.mmd`, `.puml`, `.bpmn`.

## Editing: what is and isn't implemented

- Source editor with syntax highlighting, apply, reset, copy, AI auto-fix.
- Pan/zoom/fit/fullscreen, layout direction and theme controls.
- **Visual editing exists only for Mermaid flowchart-family diagrams**: click a node to rename or delete; add nodes and connections. Each action rewrites the source and re-renders, so both stay in sync.
- **Not implemented:** React Flow / drag-to-position editing (Mermaid and PlantUML auto-layout), and visual editing for non-flowchart diagrams, PlantUML and BPMN (BPMN is view/pan/zoom only; edit its XML in the source editor).
- BPMN layout comes from `bpmn-auto-layout` (loaded from esm.sh) with a simple built-in layered fallback; lanes are not drawn.

## Testing

```bash
pytest -q                                  # 69 backend tests, LLM and network mocked
node --test tests/js/flowedit.test.js      # flowchart-editing + highlighter unit tests
```

Covered: valid/ambiguous/missing-requirement prompts, invalid Mermaid/PlantUML/BPMN, unsafe PlantUML directives, oversized sources, fix-loop limits, multi-diagram partial failure, export, auth and ownership isolation, rate limiting, DB failure, LLM/API failures.

## Known limitations

- Real Gemini/Groq calls, MongoDB Atlas, the PlantUML server and in-browser rendering are **not covered by automated tests**; they need a manual check with your keys (see below).
- Default model names (`GEMINI_MODEL`, `GROQ_MODEL`) and pinned CDN versions may need updating over time.
- "Complete documentation" is one long request (no streaming progress).
- Generated diagram quality depends on the model; Mermaid heuristics catch common errors but the browser parser is authoritative.

## Manual smoke test

1. Set a provider key, run `python app.py`, open `/`.
2. Generate "sequence diagram for login" → renders; try Export PNG/SVG/PDF; edit source → Apply.
3. Register, generate a flowchart, click a node → rename; reload via Recent Diagrams; check Version history.
4. Generate a use case (PlantUML) and a BPMN diagram.
5. Try "Complete documentation" and open each tab.

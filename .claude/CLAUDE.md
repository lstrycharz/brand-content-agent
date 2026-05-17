# Project Instructions

<!-- ⚠️  THIS FILE IS AUTO-POPULATED after the first planning session.
     When you run plan mode for the first time, Claude will fill in
     Tech Stack, Commands, Project Structure, and Rules based on the plan.
     Review and adjust as needed. -->

## Session Start

**Fresh project (no PROGRESS.md):**
Run the full test suite to orient yourself on project scope and current state. Do not proceed if tests are failing unless the task is specifically to fix them.

**Resuming work (PROGRESS.md exists):**
1. Read `.claude/PROGRESS.md` for handoff context
2. Run `git log --oneline -10` to see recent commits
3. Run the full test suite — confirm current state is green
4. Read `tasks/todo.md` and `tasks/lessons.md` if they exist
5. Pick the highest-priority incomplete item from PROGRESS.md
6. Begin work — do not re-implement anything marked as Completed

## Tech Stack
- **Language**: Python 3.14 (works on 3.11+)
- **LLM**: Anthropic Claude 3.5 Sonnet (`claude-3-5-sonnet-20241022`) via `anthropic` SDK
- **Image gen**: fal.ai Flux Schnell via `fal-client` (Chunk 3)
- **Database**: SQLite via `sqlmodel` (Pydantic-typed)
- **Web UI**: Streamlit (Chunk 4)
- **Settings**: `pydantic-settings` loading `.env`
- **HTTP**: `httpx`
- **Tests**: `pytest`, `pytest-asyncio`
- **Lint/format**: `ruff`

## Commands
```bash
# Activate venv (once per shell)
source .venv/bin/activate

# Run agent once (live mode — calls real Claude + writes to drafts/)
python -m agent.runner

# Run agent for a specific topic id
python -m agent.runner --topic-id 1

# Run tests
python -m pytest tests/ -v

# Lint
ruff check agent/ tests/
ruff check --fix agent/ tests/

# (Chunk 4) Start the Streamlit UI
streamlit run app.py
```

## Project Structure
```
agent/                 # Core agent package
├── runner.py          # Orchestrates 7 stages; CLI entry (python -m agent.runner)
├── config.py          # pydantic-settings loaded from .env
├── db.py              # sqlmodel tables: Topic, Run, Draft, ResearchCache
├── prompts.py         # Centralised Claude system/user prompts
├── progress.py        # In-memory pub/sub bus (agent → UI)
└── stages/            # One module per stage, each a deep module
    ├── init.py        # Stage 1: select topic, create Run
    ├── research.py    # Stage 2: Claude web_search + cache
    ├── outline.py     # Stage 3: Claude → JSON outline
    ├── draft.py       # Stage 4: Claude → Markdown + frontmatter
    ├── quality.py     # Stage 5: validators + auto-retry (Chunk 2)
    ├── image.py       # Stage 6: fal.ai hero image (Chunk 3)
    └── persist.py     # Stage 7: Draft record + RUN_LOG.md (Chunk 2/5)

app.py                 # Streamlit UI (Chunk 4)
data/                  # brand_guide.json, seed_topics.csv
drafts/                # Generated articles + images (gitignored)
db/                    # SQLite file (gitignored)
tests/                 # pytest tests with mocked LLM/web boundaries
```

## Rules
- **Mock at the stage boundary, not internal helpers.** Each stage exposes a private `_call_claude_*` function — that's the mock point. Don't mock internal parsing/cache helpers.
- **Pure stage signatures.** Stages take `Topic`, dicts, and `run_id` strings; they don't take clients. Internal boundary functions build their own `Anthropic()` instance from settings.
- **All datetimes are naive UTC.** SQLite drops tzinfo on roundtrip, so `utcnow()` in `agent.db` returns naive UTC. Don't introduce tz-aware datetimes — comparison errors follow.
- **`run_id` flows through every stage.** It's the join key for the progress bus, Run records, and frontmatter. Always pass it through.
- **Topic status transitions land in `runner.py`, not `init.py`.** `init.run()` only selects + creates a Run record. Marking `processed`/`failed_review_needed` happens at the orchestration layer.

## Definition of Done
- Tests written before implementation (red/green/refactor cycle)
- Types pass
- Tests pass
- No new linting errors
- DB migrations generated if models changed
- No `TODO` or `FIXME` left without a linked issue
- Works locally end-to-end before pushing

## Common Gotchas
- **SQLite timezone drop**: `datetime.now(tz=UTC)` round-trips through SQLite as naive. We use naive UTC throughout (`agent.db.utcnow()`) — don't mix.
- **Test DB isolation**: `agent.db._engine` is a module-global. Tests must call `db.reset_engine()` in fixtures (see `conftest.py::temp_db` and `test_integration.py::_isolated_paths`).
- **Topic re-selection**: Without marking a topic `processed`, `init.run()` keeps picking the same highest-priority pending one. The runner handles this — `init` itself does not.
- **Anthropic tool name versioning**: Web search tool type is `web_search_20250305`. If Anthropic releases a new version, update `agent/stages/research.py`.

## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
- **Own Your Mistakes**: When wrong, say so, fix it, add a lesson. No excuses.
- **Context Is King**: Read existing code before writing new code. Match patterns already in the repo.

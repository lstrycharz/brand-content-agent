# BrandContent

An autonomous content production agent for a DTC skincare brand.

You give it a backlog of topics; it researches each one, drafts a publish-ready
Markdown article in your brand voice, generates a hero image, runs quality and
hallucination checks, and queues the result for review. Everything runs locally
behind a Streamlit UI you trigger by hand — no cron, no cloud.

```
┌─────────────────────────────────────────────┐
│  Streamlit UI (localhost:8501)              │
│  Topics · Generate · Drafts · Settings      │
└──────────────────────┬──────────────────────┘
                       │ button click
                       ▼
┌─────────────────────────────────────────────┐
│  Agent (7 stages, deep modules)             │
│  1. Init      → load topic, create run_id   │
│  2. Research  → Claude web_search + cache   │
│  3. Outline   → Claude → JSON outline       │
│  4. Draft     → Claude → Markdown body      │
│  5. Quality   → validate + retry once       │
│  6. Image     → fal.ai Flux Schnell         │
│  7. Persist   → file + DB + RUN_LOG.md      │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  SQLite   (topics, runs, drafts, cache)     │
│  drafts/  (.md articles + .png hero images) │
│  RUN_LOG.md (auto-generated from DB)        │
└─────────────────────────────────────────────┘
```

---

## What it does, end to end

1. You add topics in the **Topics** tab (or import the bundled 30-topic CSV)
2. You click **Generate** on the dashboard
3. The agent picks the highest-priority pending topic
4. It searches the web through Claude's `web_search_20250305` tool and caches
   the findings in SQLite for 7 days
5. It generates a structured JSON outline (H1, H2 sections, CTA, SEO meta)
6. It expands the outline into a ~1200-word Markdown article in your brand
   voice (cached prompt context keeps cost down)
7. It runs five quality checks — word count, keyword placement, H2 structure,
   tone vs brand voice (LLM-eval), and hallucination check (LLM cross-check
   against the research findings). On failure, it retries the draft *once*
   with concrete feedback, then either passes or marks the topic
   `failed_review_needed`
8. It generates a 16:9 hero image via fal.ai Flux Schnell (~$0.003 per image)
9. It writes the final Markdown to `drafts/`, updates SQLite, and regenerates
   `RUN_LOG.md` from the runs table

You preview the result in the **Drafts** tab and publish to your blog manually.

---

## Setup

Requirements: Python 3.11+, an Anthropic API key, a fal.ai API key.

```bash
git clone <this repo>
cd BrandContent

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and fill in:
#   ANTHROPIC_API_KEY=sk-ant-...
#   FAL_KEY=...
```

---

## Running

```bash
streamlit run app.py
```

Open <http://localhost:8501>:

- **📋 Topics** — Inline CRUD over the topics backlog. First visit shows
  *Seed starter topics from CSV* which imports the 30 topics in
  `data/seed_topics.csv`. Add/edit/delete rows, then *Save changes*.
- **🚀 Generate** — Shows the next pending topic. Click *Generate article* and
  watch each stage stream events into the status panel. Takes 1-3 minutes per
  run depending on web search latency.
- **📰 Drafts** — Gallery of finished runs with hero images, tone/SEO scores,
  and the rendered article body.
- **⚙️ Settings** — Generate a brand voice JSON from a one-line description,
  or view the auto-generated `RUN_LOG.md`.

---

## Running without the UI

```bash
# Run the agent once on the highest-priority pending topic
python -m agent.runner

# Or pin a specific topic
python -m agent.runner --topic-id 7
```

Both paths produce the same output: a `.md` + `.png` in `drafts/`, a row in
the `runs` table, and an updated `RUN_LOG.md`.

---

## Tests

```bash
python -m pytest tests/ -v
```

42 tests. Every Claude and fal.ai call is mocked at the function boundary
(`_call_claude_*` and `_call_fal_*`), so the suite runs offline in well under
a second and costs zero dollars. The "five successive runs" integration test
proves the pipeline is reliable without waiting on a real cron schedule.

---

## Project layout

```
agent/
├── runner.py           # Orchestrates the 7 stages; CLI entry
├── config.py           # pydantic-settings loaded from .env
├── db.py               # sqlmodel tables: Topic, Run, Draft, ResearchCache
├── brand_voice.py      # Brand guide generator (Stage 5 helper)
├── run_log.py          # RUN_LOG.md regeneration from SQLite
├── prompts.py          # Centralised Claude system/user prompts
├── progress.py         # Thread-safe pub/sub bus (agent → UI)
└── stages/
    ├── init.py         # Select topic, create Run record
    ├── research.py     # Claude web_search + cache
    ├── outline.py      # Claude → JSON outline
    ├── draft.py        # Claude → Markdown body
    ├── quality.py      # Validators + LLM evaluators
    ├── image.py        # fal.ai Flux Schnell hero image
    └── persist.py      # (currently inlined in runner — Stage 7)

app.py                  # Streamlit UI (4 tabs, ~350 lines)
data/seed_topics.csv    # 30 starter topics
drafts/                 # Generated articles + hero images (gitignored)
db/                     # SQLite file (gitignored)
RUN_LOG.md              # Auto-generated audit log
tests/                  # 42 tests, fully mocked
```

---

## Design rules followed

- **Deep modules over shallow.** Each stage is one public `run()` over a
  hidden private boundary (`_call_claude_*`, `_call_fal_*`). Tests mock at
  that boundary.
- **TDD.** Every chunk landed RED → GREEN → REFACTOR. No implementation
  shipped without a failing test first.
- **One thing per commit.** Five chunks, five commits, each a working state.
  See `git log`.
- **Naive UTC datetimes.** SQLite drops tzinfo on roundtrip; we use naive
  UTC throughout to avoid `can't compare offset-naive and offset-aware`
  surprises.

---

## What's *not* in scope

- GitHub Actions cron (the scheduler is *you* — click the button)
- Email or Slack notifications (the UI shows progress live)
- Auto-publishing to a CMS — you copy/paste from `drafts/` to your blog
- Multi-agent orchestration
- Self-improvement / RL on outputs

# Brand Content Agent

A small open-source app that writes publish-ready blog articles for **any** DTC brand — automatically.

It's a framework, not a skincare tool. The same pipeline works for skincare, supplements, pet food, fitness apparel, B2B SaaS, financial services, or anything else. The brand's vertical, audience, tone, and writing rules live in a single `brand_guide.json` file that Claude generates for you from a one-line description.

---

## What it does

You give it a list of article topics. When you click a button, it:

1. Searches the web for accurate, up-to-date information on the topic
2. Writes a ~1,100-word article in your brand's voice
3. Generates a custom hero image for the top of the article
4. Saves everything as a ready-to-publish Markdown file on your computer

You stay in control. The app does **not** post anywhere on its own — you review the result and publish to your blog yourself. It just removes the hours of writing and image-making.

---

## What you need before starting

Three things, all free to set up:

1. **A computer** — Mac, Windows, or Linux. Anything from the last 5 years.
2. **An Anthropic account** (the company that makes Claude AI) — to write the articles
3. **A fal.ai account** — to make the hero images

Both services give you free starter credits. Ongoing usage costs about **6 cents per article** (5¢ Claude + ~0.3¢ fal.ai).

---

## Step 1 — Get your API keys

Think of API keys like passwords that let this app use Claude and fal.ai on your behalf.

**Anthropic key**
1. Go to <https://console.anthropic.com/>
2. Sign up or log in
3. Click **API Keys** in the left menu
4. Click **Create Key**, give it any name (e.g. "Brand Content")
5. Copy the key (it starts with `sk-ant-...`) — **save it somewhere safe**, you won't see it again

**fal.ai key**
1. Go to <https://fal.ai/dashboard>
2. Sign up or log in
3. Open the **API Keys** section
4. Create a new key and copy it

---

## Step 2 — Install Python

This app runs on Python (a programming language). Most computers don't have the right version pre-installed.

- **Mac:** Open Terminal (⌘+Space, type "Terminal"). If you don't have Homebrew, install it from <https://brew.sh>, then run:
  ```
  brew install python@3.11
  ```
- **Windows:** Download Python from <https://www.python.org/downloads/>. During install, **check the box** that says *"Add Python to PATH"* — this is the most common gotcha.
- **Linux:** You probably already have Python. Run `python3 --version`. If it shows 3.11 or higher, you're good.

You'll also need **Git** (a tool that downloads code from GitHub). Mac and Linux usually have it. On Windows, install from <https://git-scm.com/downloads>.

---

## Step 3 — Download Brand Content Agent

Open Terminal (Mac/Linux) or Command Prompt (Windows). Navigate to where you want to install the app (e.g. your Desktop):

```
cd ~/Desktop
git clone https://github.com/lstrycharz/brand-content-agent.git
cd brand-content-agent
```

---

## Step 4 — Set up the app

Still in the terminal, in the `brand-content-agent` folder, run these three commands one at a time:

**Mac/Linux:**
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

The last command downloads everything the app needs. Takes about a minute. When it's done, you'll see your prompt change to start with `(.venv)`.

---

## Step 5 — Add your API keys

In the `brand-content-agent` folder, find the file called `.env.example`. Make a copy of it and rename the copy to just `.env` (remove `.example` from the end).

Open `.env` in any text editor (TextEdit on Mac, Notepad on Windows). Paste your keys in:

```
ANTHROPIC_API_KEY=sk-ant-paste-your-key-here
FAL_KEY=paste-your-fal-key-here
```

Save and close. The `.env` file stays on your computer — it's automatically excluded from anything you share.

---

## Step 6 — Start the app

In the terminal, with `(.venv)` still showing at the start of your prompt:

```
streamlit run app.py
```

A browser tab opens at **http://localhost:8501**. That's the app.

To stop the app later, go back to the terminal and press **Ctrl+C**.

---

## How to use it

The app has four tabs. The first time, use them in this order:

### 1. ⚙️ Settings — Describe your brand (one time)

Write one or two sentences about your brand. Be specific about three things:
**what you sell**, **who your audience is**, and **how you sound**.

Examples that work well:

> *"Skincare brand for sensitive-skin adults, science-backed and no-nonsense like The Ordinary."*

> *"Premium dog food for senior pets — warm and informative tone, audience is owners worried about joint health and longevity."*

> *"B2B observability SaaS for backend engineers — terse, technically precise, no marketing fluff."*

Click **✨ Generate brand guide**. Claude turns your sentence into a structured JSON guide that includes your vertical, audience, tone, vocabulary level, values, dos and don'ts. This takes ~5 seconds and costs less than a penny.

Every prompt in the pipeline — research, outline, draft, image generation, tone evaluation — references this guide. So tweaking it changes how every future article sounds.

You only do this once. Regenerate any time you want to change the brand's voice.

### 2. 📋 Topics — Load your topic list

The repo ships with **30 example skincare topics** in `data/seed_topics.csv`. Useful for kicking the tyres if your brand happens to be skincare-adjacent, but for any other vertical you'll want to delete them and write your own.

**Two ways to add topics:**
- **Inline:** click the "+" row at the bottom of the table and type in title, keyword, category, difficulty, priority. Hit *Save changes*.
- **Bulk:** open `data/seed_topics.csv` in any spreadsheet app (Numbers, Excel), replace the rows with your own topics, save, then click *Import example skincare topics* (it's the same import button — it picks up whatever's in the file).

For each topic you need:
- **title** — what the article is about (becomes the H1)
- **keyword** — the SEO phrase you want the article to rank for
- **category** — your own grouping (e.g. "ingredients", "comparison", "how-to")
- **difficulty** — `beginner`, `intermediate`, or `advanced` (informational, doesn't affect the pipeline)
- **priority** — 1-10, higher gets picked first

### 3. 🚀 Generate — Make an article

You'll see the next pending topic at the top. Click **🚀 Generate article**.

A progress panel shows what's happening:

```
· [init]     Selected topic: Why senior dogs need joint support
· [research] Searching the web for 'senior dog joint supplements'...
· [research] Got 7 key points, 3 sources
· [outline]  Generating outline...
✓ [outline]  Outline ready (5 sections)
· [draft]    Drafting article...
✓ [draft]    Drafted 1108 words
· [quality]  Validating draft...
✓ [quality]  Passed all checks
· [image]    Generating hero image...
✓ [image]    Image saved: 2026-05-17-why-senior-dogs-need-joint-support-hero.png
✓ [done]     Draft written to drafts/...
```

It takes 1-3 minutes per article.

### 4. 📰 Drafts — Review

Every finished article appears here as a card with the hero image, quality scores, and the article text. Click *View article* to expand the full draft.

The actual files live in the `drafts/` folder on your computer — copy them into your blog when you're happy.

---

## What does it cost?

Per article:

| Item | Cost |
|---|---|
| Claude (writing + checks) | ~5¢ |
| fal.ai (hero image) | ~0.3¢ |
| **Total** | **~6¢** |

For 100 articles: about **$6**.

You only pay for what you generate. No subscription.

---

## Common problems

**"Model not found" error**
Claude model names change occasionally. Open `agent/config.py`, find the line with `drafting_model`, and update it to the current best Sonnet model (check <https://docs.anthropic.com/> for the latest name).

**"No pending topics"**
Either you haven't added topics yet, or every topic is marked done. Click **↩ Reset failed → pending** on the Topics tab, or change a topic's status back to `pending` directly in the table.

**Article quality feels off / doesn't match my brand**
The agent retries once if quality checks fail, then gives up. If results feel generic or off-brand, your brand voice description was probably too vague. Regenerate it on the Settings tab with a more specific description — include the vertical, audience, and 2-3 concrete tone words.

**Articles are too short / too long**
Adjust the bounds in `agent/config.py`:
```python
target_word_count: int = 1100   # what Claude aims for
word_count_min: int = 900       # below this triggers a retry
word_count_max: int = 1300      # above this triggers a retry
```

**Stuck / weird behavior**
Stop the app with Ctrl+C in the terminal, then run `streamlit run app.py` again to restart.

**Forgot what the agent has done**
Open the **Run log** section at the bottom of the Settings tab — every article it's ever made is listed there. Or open the `RUN_LOG.md` file in the project folder.

---

## For the technically curious

- **`agent/`** — the AI logic, split into seven stages (init, research, outline, draft, quality, image, persist)
- **`app.py`** — the Streamlit web interface (~370 lines)
- **`db/brandcontent.sqlite`** — local database of topics, runs, and drafts (open with any SQLite viewer)
- **`RUN_LOG.md`** — auto-regenerated audit log
- **`tests/`** — 43 tests, every API call mocked. Run with `python -m pytest tests/`. Costs nothing.

### Vertical-agnostic by design

Every prompt reads `brand_voice.vertical` and `brand_voice.target_audience` rather than hardcoding any industry. The `brand_guide.json` Claude generates is the single source of truth for what your brand sells and who it talks to. To swap verticals, you just regenerate the brand guide and replace the topics — no code changes.

The agent was built with strict TDD across 6 incremental commits. See `git log --oneline` for the chunk-by-chunk history.

---

## What this app does *not* do

- Post to your blog or CMS for you (you copy/paste from the `drafts/` folder)
- Run on a schedule (you trigger each article manually with a button)
- Send email/Slack notifications (everything happens in the UI window)
- Compete with you for control — every output is reviewed by you before going live

It's a tool, not an autopilot.

# Brand Content Agent

A small app that writes publish-ready blog articles for your skincare brand — automatically.

You give it a list of article topics (like *"How to treat hormonal acne"* or *"Vitamin C serums explained"*). When you click a button, it:

1. Searches the web for accurate, up-to-date information
2. Writes a ~1,200-word article in your brand's voice
3. Generates a custom hero image for the top of the article
4. Saves everything as a ready-to-publish Markdown file on your computer

You stay in control. The app does **not** post anywhere on its own — you review the result and publish to your blog yourself. It just removes the hours of writing and image-making.

---

## What you need before starting

Three things, all free to set up:

1. **A computer** — Mac, Windows, or Linux. Anything from the last 5 years.
2. **An Anthropic account** (the company that makes Claude AI) — to write the articles
3. **A fal.ai account** — to make the hero images

Both services give you free starter credits, and ongoing usage costs about **6 cents per article** (5¢ Claude + ~0.3¢ fal.ai).

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

### 1. ⚙️ Settings — Tell it how your brand sounds

Write one or two sentences describing your brand voice. For example:

> *"Science-backed and no-nonsense, like The Ordinary. Educate, don't sell. Avoid hype and clichés."*

Click **✨ Generate brand guide**. Claude turns your sentence into a detailed style guide that every article will follow. This takes ~5 seconds and costs less than a penny.

You only need to do this once. (You can regenerate any time you want to tweak the tone.)

### 2. 📋 Topics — Load your topic list

First time here, you'll see an empty table and a button **📥 Seed starter topics from CSV**. Click it — you get 30 skincare article ideas ready to go.

You can also:
- **Edit any cell** by clicking it (change titles, keywords, etc.)
- **Add new rows** at the bottom
- **Delete rows** by checking the box on the left
- **Change priority** numbers (1-10, higher = picked sooner)

Click **💾 Save changes** to keep your edits.

### 3. 🚀 Generate — Make an article

You'll see the next pending topic at the top. Click **🚀 Generate article**.

A progress panel shows what's happening:

```
· [init]     Selected topic: How to treat hormonal acne in adults
· [research] Searching the web for 'hormonal acne treatment'...
· [research] Got 7 key points, 3 sources
· [outline]  Generating outline...
✓ [outline]  Outline ready (5 sections)
· [draft]    Drafting article...
✓ [draft]    Drafted 1213 words
· [quality]  Validating draft...
✓ [quality]  Passed all checks
· [image]    Generating hero image...
✓ [image]    Image saved: 2026-05-17-how-to-treat-hormonal-acne-hero.png
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
Either you haven't seeded topics yet (Topics tab → big blue button), or every topic is marked done. Click **↩ Reset failed → pending** on the Topics tab, or change a topic's status back to `pending` directly in the table.

**Article quality feels off**
The agent retries once if quality is poor, then gives up. If results feel generic or off-brand, your brand voice needs more specifics. Regenerate it on the Settings tab with a more detailed description.

**Stuck / weird behavior**
Stop the app with Ctrl+C in the terminal, then run `streamlit run app.py` again to restart.

**Forgot what the agent has done**
Open the **Run log** section at the bottom of the Settings tab — every article it's ever made is listed there. Or open the `RUN_LOG.md` file in the project folder.

---

## For the technically curious

- **`agent/`** — the AI logic, split into seven stages (init, research, outline, draft, quality, image, persist)
- **`app.py`** — the Streamlit web interface (~350 lines)
- **`db/brandcontent.sqlite`** — local database of topics, runs, and drafts (open with any SQLite viewer)
- **`RUN_LOG.md`** — auto-regenerated audit log
- **`tests/`** — 42 tests, every API call mocked. Run with `python -m pytest tests/`. Costs nothing.

The agent was built with strict TDD across 6 incremental commits. See `git log --oneline` for the chunk-by-chunk history.

---

## What this app does *not* do

- Post to your blog or CMS for you (you copy/paste from the `drafts/` folder)
- Run on a schedule (you trigger each article manually with a button)
- Send email/Slack notifications (everything happens in the UI window)
- Compete with you for control — every output is reviewed by you before going live

It's a tool, not an autopilot.

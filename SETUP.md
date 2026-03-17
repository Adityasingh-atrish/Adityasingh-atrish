# VC Pitch Triage Tool — Setup Guide

> A semi-automated dashboard to triage inbound pitch emails from Gmail using GPT-4.

---

## What This Does

1. Connects to your Gmail inbox
2. Pulls pitch emails (searches for keywords like "pitch", "investor pitch", SuperDM emails)
3. Reads the email body + extracts text from PDF attachments
4. Sends everything to GPT-4 → gives you: Company name, Problem, Solution, Rating (1–5 stars), Recommendation, Reasoning
5. Shows a clean dashboard
6. One-click buttons: **Send Rejection** / **Forward to My Email** / **Forward to Disha**

---

## Step 1 — Install Python & Dependencies

You need Python 3.10 or higher.

```bash
pip install -r requirements.txt
```

---

## Step 2 — Get a Google API Credential (Gmail access)

This lets the app read your Gmail. Takes ~5 minutes.

1. Go to: https://console.cloud.google.com/
2. Create a new project (name it anything, e.g. "Pitch Triage")
3. Go to **APIs & Services → Library**
4. Search for **Gmail API** → Enable it
5. Go to **APIs & Services → OAuth consent screen**
   - Choose **External** → Fill in app name (e.g. "Pitch Triage") → Save
   - Under **Scopes** add: `gmail.readonly` and `gmail.send`
   - Under **Test users** add your own Gmail address
6. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Desktop app**
   - Download the JSON file
7. Rename the downloaded file to `credentials.json` and put it in this folder

---

## Step 3 — Get an OpenAI API Key

1. Go to: https://platform.openai.com/api-keys
2. Create a new key
3. Copy it

---

## Step 4 — Configure Your .env File

Copy the example and fill in your details:

```bash
cp .env.example .env
```

Edit `.env`:

```
OPENAI_API_KEY=sk-...your-key-here...
MY_WORK_EMAIL=aditya@yourfirm.com
DISHA_EMAIL=disha@yourfirm.com
```

You can also customize the rejection email template inside `.env`.

---

## Step 5 — Run the App

```bash
python app.py
```

The first time you run it, a browser window will open asking you to sign in to Google and grant permission. Do that once — it saves a `token.json` file so you won't need to do it again.

Then open: **http://localhost:5000**

---

## How to Use the Dashboard

1. Click **"Fetch Today's Pitches"** — waits 20–60 seconds while it reads emails + runs AI
2. Each pitch shows up as a card with:
   - Company name, sector badge
   - Problem / Solution / Traction
   - Star rating (1–5) + MEET / REJECT recommendation
   - AI reasoning + green/red flags
3. Click one of the 3 buttons:
   - **✕ Send Rejection** — sends your preset rejection email to the founder
   - **→ Send to My Email** — forwards pitch + AI summary to your work email
   - **→ Send to Disha** — forwards to Disha's email
4. Done cards move to a "Done" section below

---

## Customizing What Emails Get Fetched

By default the app searches Gmail for:
```
subject:pitch OR subject:"investor pitch" OR from:messages@superdm.com newer_than:7d
```

To change this, edit `gmail_service.py` line ~38, the `query` variable.

---

## Files Overview

```
app.py              — Flask web server + API routes
gmail_service.py    — Gmail read/send logic
ai_analyzer.py      — GPT-4 analysis
templates/index.html — Dashboard UI
requirements.txt    — Python dependencies
.env                — Your secrets (never commit this)
credentials.json    — Google OAuth credential (never commit this)
token.json          — Auto-generated after first login (never commit this)
```

---

## Security Notes

- Never commit `.env`, `credentials.json`, or `token.json` to git
- The app only runs locally on your machine (port 5000)
- All AI analysis happens via OpenAI API (no data stored on their servers beyond the API call)

"""
AI analyzer: send pitch content to Claude and get structured analysis.
"""
import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are an expert VC analyst at an early-stage venture fund.
Your job is to quickly triage inbound pitch emails and investor decks.
You extract key information and give a sharp, honest investment signal.

Respond ONLY with valid JSON. No markdown fences, no extra text."""

USER_PROMPT_TEMPLATE = """Analyze this startup pitch and return a JSON object with exactly these fields:

{{
  "company_name": "Name of the company (string)",
  "sector": "Primary sector like 'AI/DeepTech', 'Consumer', 'Fintech', 'SaaS', 'HealthTech', etc. (string)",
  "problem": "One crisp sentence describing the problem they're solving (string)",
  "solution": "One crisp sentence describing what they've built (string)",
  "stage": "Funding stage they're raising (e.g. Pre-seed, Seed, Series A) (string)",
  "ask": "Amount they're raising (string)",
  "traction": "Key traction or metrics in one sentence, or 'Not mentioned' (string)",
  "rating": "Integer 1-5. 5=must meet, 4=strong interest, 3=borderline, 2=weak, 1=pass",
  "recommendation": "One word: 'MEET' or 'REJECT'",
  "reasoning": "2-3 sentences: why meet or reject. Be direct and honest.",
  "red_flags": ["list", "of", "concerns", "if", "any"],
  "green_flags": ["list", "of", "positives", "if", "any"]
}}

PITCH CONTENT:
{pitch_content}"""


def analyze_pitch(full_content: str) -> dict:
    """
    Send pitch content to Claude and return structured analysis dict.
    Falls back to a default dict if parsing fails.
    """
    prompt = USER_PROMPT_TEMPLATE.format(
        pitch_content=full_content[:12000]  # Cap to avoid token overrun
    )

    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=800,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.content[0].text.strip()
        analysis = json.loads(raw)
        # Ensure required keys exist
        for key in ["company_name", "problem", "solution", "rating", "recommendation", "reasoning"]:
            analysis.setdefault(key, "Unknown")
        analysis["rating"] = int(analysis.get("rating", 1))
        return analysis

    except json.JSONDecodeError:
        return _fallback_analysis(full_content)
    except Exception as e:
        return {
            "company_name": "Unknown",
            "sector": "Unknown",
            "problem": "Could not parse",
            "solution": "Could not parse",
            "stage": "Unknown",
            "ask": "Unknown",
            "traction": "Unknown",
            "rating": 0,
            "recommendation": "REVIEW_MANUALLY",
            "reasoning": f"AI analysis failed: {str(e)}",
            "red_flags": [],
            "green_flags": [],
            "error": str(e),
        }


def _fallback_analysis(content: str) -> dict:
    """Simple fallback if JSON parsing fails — retry with stricter prompt."""
    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract from this pitch: company name, 1-line problem, 1-line solution, "
                        "and rating 1-5. Return ONLY JSON with keys: company_name, problem, "
                        f"solution, rating, recommendation (MEET or REJECT), reasoning.\n\n{content[:6000]}"
                    ),
                }
            ],
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return {
            "company_name": "Unknown",
            "sector": "Unknown",
            "problem": "Manual review needed",
            "solution": "Manual review needed",
            "stage": "Unknown",
            "ask": "Unknown",
            "traction": "Unknown",
            "rating": 0,
            "recommendation": "REVIEW_MANUALLY",
            "reasoning": "AI could not parse this pitch. Please review manually.",
            "red_flags": [],
            "green_flags": [],
        }


def build_summary_text(analysis: dict) -> str:
    """Build a readable text summary for email forwarding."""
    stars = "★" * analysis.get("rating", 0) + "☆" * (5 - analysis.get("rating", 0))
    return f"""AI PITCH ANALYSIS
==================
Company:        {analysis.get('company_name', 'Unknown')}
Sector:         {analysis.get('sector', 'Unknown')}
Stage/Ask:      {analysis.get('stage', '?')} / {analysis.get('ask', '?')}
Rating:         {stars} ({analysis.get('rating', 0)}/5)
Recommendation: {analysis.get('recommendation', '?')}

Problem:  {analysis.get('problem', '?')}
Solution: {analysis.get('solution', '?')}
Traction: {analysis.get('traction', 'Not mentioned')}

Reasoning: {analysis.get('reasoning', '?')}

Green flags: {', '.join(analysis.get('green_flags', [])) or 'None'}
Red flags:   {', '.join(analysis.get('red_flags', [])) or 'None'}
"""

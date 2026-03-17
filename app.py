"""
VC Pitch Triage Tool — Flask app
Run: python app.py
"""
import json
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

from ai_analyzer import analyze_pitch, build_summary_text
from gmail_service import (
    fetch_pitch_emails,
    forward_to,
    get_gmail_service,
    send_rejection,
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

MY_WORK_EMAIL = os.environ.get("MY_WORK_EMAIL", "")
DISHA_EMAIL = os.environ.get("DISHA_EMAIL", "")
REJECTION_TEMPLATE = os.environ.get(
    "REJECTION_TEMPLATE",
    "Hi {founder_name},\n\nThank you for sharing your pitch for {company_name}. "
    "After careful review, we've decided to pass at this stage. "
    "We wish you the very best with your fundraise.\n\nBest,\nAditya",
)

# In-memory store for the current session's pitches
# (persists as long as Flask is running)
pitches_store: dict[str, dict] = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fetch", methods=["POST"])
def fetch_pitches():
    """Fetch emails from Gmail and run AI analysis on each."""
    try:
        service = get_gmail_service()
        emails = fetch_pitch_emails(service)

        # Evict any previously cached entries that contain errors so they get re-analyzed
        for mid in list(pitches_store.keys()):
            if "error" in pitches_store[mid].get("analysis", {}):
                del pitches_store[mid]

        results = []
        for em in emails:
            msg_id = em["id"]
            if msg_id in pitches_store:
                # Already analyzed — return cached
                results.append(pitches_store[msg_id])
                continue

            analysis = analyze_pitch(em["full_content"])
            summary_text = build_summary_text(analysis)

            pitch_data = {
                "id": msg_id,
                "subject": em["subject"],
                "founder_name": em["founder_name"],
                "founder_email": em["founder_email"],
                "date": em["date"],
                "body": em["body"],
                "pdf_text": em["pdf_text"],
                "analysis": analysis,
                "summary_text": summary_text,
                "action_taken": None,  # reject / my_email / disha_email
            }
            # Only cache successful analyses; errors will be retried on next refresh
            if "error" not in analysis:
                pitches_store[msg_id] = pitch_data
            results.append(pitch_data)

        # Sort: highest rated first
        results.sort(key=lambda x: x["analysis"].get("rating", 0), reverse=True)
        return jsonify({"pitches": results, "count": len(results)})

    except FileNotFoundError:
        return jsonify({"error": "credentials.json not found. See setup guide."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/action", methods=["POST"])
def take_action():
    """Handle Reject / Send to Me / Send to Disha."""
    data = request.json
    msg_id = data.get("id")
    action = data.get("action")  # "reject", "my_email", "disha_email"

    if msg_id not in pitches_store:
        return jsonify({"error": "Pitch not found"}), 404

    pitch = pitches_store[msg_id]
    analysis = pitch["analysis"]
    company_name = analysis.get("company_name", "Unknown")
    founder_name = pitch["founder_name"]
    founder_email = pitch["founder_email"]

    try:
        service = get_gmail_service()

        if action == "reject":
            send_rejection(
                service,
                to_email=founder_email,
                founder_name=founder_name,
                company_name=company_name,
                rejection_template=REJECTION_TEMPLATE,
            )
            pitches_store[msg_id]["action_taken"] = "rejected"
            return jsonify({"status": "ok", "message": f"Rejection sent to {founder_email}"})

        elif action == "my_email":
            if not MY_WORK_EMAIL:
                return jsonify({"error": "MY_WORK_EMAIL not set in .env"}), 400
            forward_to(
                service,
                to_email=MY_WORK_EMAIL,
                original_subject=pitch["subject"],
                original_body=pitch["body"],
                pdf_text=pitch["pdf_text"],
                analysis_summary=pitch["summary_text"],
            )
            pitches_store[msg_id]["action_taken"] = "sent_to_me"
            return jsonify({"status": "ok", "message": f"Forwarded to {MY_WORK_EMAIL}"})

        elif action == "disha_email":
            if not DISHA_EMAIL:
                return jsonify({"error": "DISHA_EMAIL not set in .env"}), 400
            forward_to(
                service,
                to_email=DISHA_EMAIL,
                original_subject=pitch["subject"],
                original_body=pitch["body"],
                pdf_text=pitch["pdf_text"],
                analysis_summary=pitch["summary_text"],
            )
            pitches_store[msg_id]["action_taken"] = "sent_to_disha"
            return jsonify({"status": "ok", "message": f"Forwarded to {DISHA_EMAIL}"})

        else:
            return jsonify({"error": "Unknown action"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pitches", methods=["GET"])
def get_cached_pitches():
    """Return already-analyzed pitches without re-fetching Gmail."""
    results = sorted(
        pitches_store.values(),
        key=lambda x: x["analysis"].get("rating", 0),
        reverse=True,
    )
    return jsonify({"pitches": results, "count": len(results)})


if __name__ == "__main__":
    print("\n✓ VC Pitch Triage running at http://localhost:5000\n")
    app.run(debug=True, port=5000)

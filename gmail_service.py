"""
Gmail service: authenticate, fetch pitch emails, send/forward.
"""
import base64
import email
import os
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pdfplumber

# Only need to read mail + send
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def get_gmail_service():
    """Return an authenticated Gmail API service object."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token_file:
            token_file.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def fetch_pitch_emails(service, max_results=20):
    """
    Fetch recent emails from inbox that look like pitch emails.
    Returns a list of parsed email dicts.
    """
    # Search for emails with common pitch keywords or SuperDM subject
    query = 'subject:pitch OR subject:"investor pitch" OR from:messages@superdm.com newer_than:7d'
    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = result.get("messages", [])
    parsed = []
    for msg_ref in messages:
        parsed_email = _parse_email(service, msg_ref["id"])
        if parsed_email:
            parsed.append(parsed_email)
    return parsed


def _parse_email(service, msg_id):
    """Download and parse a single email, including PDF attachments."""
    raw = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()

    headers = {h["name"]: h["value"] for h in raw["payload"]["headers"]}
    subject = headers.get("Subject", "(no subject)")
    sender = headers.get("From", "")
    date = headers.get("Date", "")

    body_text = _extract_body(raw["payload"])
    pdf_text = _extract_pdf_attachment(service, msg_id, raw["payload"])

    # Extract sender name and email
    founder_name = sender.split("<")[0].strip().strip('"') if "<" in sender else sender
    founder_email = sender.split("<")[-1].strip(">") if "<" in sender else sender

    return {
        "id": msg_id,
        "subject": subject,
        "sender": sender,
        "founder_name": founder_name,
        "founder_email": founder_email,
        "date": date,
        "body": body_text,
        "pdf_text": pdf_text,
        # Combined content for AI analysis
        "full_content": f"EMAIL BODY:\n{body_text}\n\nPITCH DECK CONTENT:\n{pdf_text}",
    }


def _extract_body(payload):
    """Recursively extract plain text body from email payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore") if data else ""

    if payload.get("mimeType") == "text/html":
        return ""  # Prefer plain text

    parts = payload.get("parts", [])
    for part in parts:
        text = _extract_body(part)
        if text:
            return text
    return ""


def _extract_pdf_attachment(service, msg_id, payload):
    """Find and extract text from the first PDF attachment."""
    parts = payload.get("parts", [])
    for part in parts:
        filename = part.get("filename", "")
        mime_type = part.get("mimeType", "")

        if "pdf" in mime_type.lower() or filename.lower().endswith(".pdf"):
            attachment_id = part.get("body", {}).get("attachmentId")
            if attachment_id:
                attachment = service.users().messages().attachments().get(
                    userId="me", messageId=msg_id, id=attachment_id
                ).execute()
                pdf_bytes = base64.urlsafe_b64decode(attachment["data"])
                return _read_pdf_text(pdf_bytes)

        # Recurse into nested parts
        if part.get("parts"):
            text = _extract_pdf_attachment(service, msg_id, part)
            if text:
                return text

    return ""


def _read_pdf_text(pdf_bytes):
    """Extract text from PDF bytes using pdfplumber."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages_text = []
            for page in pdf.pages[:15]:  # Cap at 15 pages to save tokens
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            return "\n".join(pages_text)
    except Exception as e:
        return f"[Could not extract PDF text: {e}]"


def send_rejection(service, to_email, founder_name, company_name, rejection_template):
    """Reply with the rejection email template."""
    body = rejection_template.replace("{founder_name}", founder_name).replace(
        "{company_name}", company_name
    )
    _send_email(service, to_email, "Re: Your Pitch", body)


def forward_to(service, to_email, original_subject, original_body, pdf_text, analysis_summary):
    """Forward the pitch with AI summary to an internal email."""
    fwd_body = f"""Hi,

Forwarding this pitch for your review. AI analysis summary below.

---
{analysis_summary}
---

ORIGINAL EMAIL:
{original_body}

PITCH DECK (extracted text):
{pdf_text[:3000]}...
"""
    subject = f"FWD: {original_subject}"
    _send_email(service, to_email, subject, fwd_body)


def _send_email(service, to, subject, body):
    """Send a plain-text email."""
    message = MIMEMultipart()
    message["to"] = to
    message["subject"] = subject
    message.attach(MIMEText(body, "plain"))
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()

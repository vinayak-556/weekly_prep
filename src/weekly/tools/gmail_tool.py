from crewai.tools import BaseTool
from typing import Type, List, Dict, Optional
from pydantic import BaseModel, Field
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os, json, base64, re
from html import unescape
 
class GmailMeetingToolInput(BaseModel):
    query: str = Field(..., description="Gmail search query with optional filters like date or sender.")
    max_results: int = Field(5, description="Maximum number of emails to return (1-10).")
    include_body: bool = Field(False, description="If true, return a truncated plain-text body.")
    body_char_limit: int = Field(800, description="Max characters of body to include when include_body=True (hard cap).")
 
class GmailMeetingTool(BaseTool):
    name: str = "GmailMeetingTool"
    description: str = "Search Gmail for meeting-related emails based on a query string (e.g., meeting title) and return compact results."
    args_schema: Type[BaseModel] = GmailMeetingToolInput
 
    def _run(self, query: str, max_results: int = 5, include_body: bool = False, body_char_limit: int = 800) -> str:
        try:
            load_dotenv()
            tkn_env = os.getenv("GMAIL_TKN")
            if not tkn_env:
                return json.dumps({"error": "GMAIL_TKN not found in environment"})
 
            tkn_data = json.loads(tkn_env)
            creds = Credentials(
                token=tkn_data["token"],
                refresh_token=tkn_data.get("refresh_token"),
                token_uri=tkn_data["token_uri"],
                client_id=tkn_data["client_id"],
                client_secret=tkn_data["client_secret"],
                scopes=tkn_data["scopes"],
            )
 
            service = build("gmail", "v1", credentials=creds)
 
            # Bound max_results (keep the tool lightweight)
            max_results = max(1, min(int(max_results), 10))
 
            search = service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
 
            ids = [m["id"] for m in search.get("messages", [])]
            if not ids:
                return json.dumps({"count": 0, "items": []})
 
            items: List[Dict] = []
            for mid in ids:
                # Fetch minimal data first
                msg = service.users().messages().get(
                    userId="me", id=mid, format="metadata", metadataHeaders=["Subject","From","Date"]
                ).execute()
 
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                subject = headers.get("Subject", "No Subject")
                sender  = headers.get("From", "No Sender")
                date    = headers.get("Date", "No Date")
                snippet = msg.get("snippet", "")
 
                record: Dict[str, Optional[str]] = {
                    "id": mid,
                    "subject": subject,
                    "from": sender,
                    "date": date,
                    "snippet": snippet[:300] if snippet else "",
                }
 
                if include_body:
                    # Fetch full only when requested
                    full = service.users().messages().get(userId="me", id=mid, format="full").execute()
                    body_text = self._extract_plain_text(full.get("payload", {}))
                    # Truncate hard to protect the LLM context
                    record["body"] = body_text[:body_char_limit] if body_text else ""
 
                items.append(record)
 
            return json.dumps({"count": len(items), "items": items})
 
        except Exception as e:
            return json.dumps({"error": f"Error while accessing Gmail: {str(e)}"})
 
    # --- Utilities ---
 
    def _extract_plain_text(self, payload: dict) -> str:
        """
        Recursively extract text/plain first, else fallback to text/html (stripped),
        else concatenate text from subparts. Always returns safe, small-ish text.
        """
        if not payload:
            return ""
 
        # If the message has a direct body
        data = payload.get("body", {}).get("data")
        mime = payload.get("mimeType")
        if data:
            text = self._safe_b64_to_text(data)
            if mime == "text/html":
                return self._strip_html(text)
            return text
 
        # If the message has parts, search for text/plain first
        parts = payload.get("parts", [])
        if not parts:
            return ""
 
        # Prefer text/plain
        for p in parts:
            if p.get("mimeType") == "text/plain":
                dt = p.get("body", {}).get("data")
                if dt:
                    return self._safe_b64_to_text(dt)
 
        # Fallback to text/html
        for p in parts:
            if p.get("mimeType") == "text/html":
                dt = p.get("body", {}).get("data")
                if dt:
                    return self._strip_html(self._safe_b64_to_text(dt))
 
        # Recurse/concatenate (last resort)
        texts = []
        for p in parts:
            texts.append(self._extract_plain_text(p))
        return "\n".join(t for t in texts if t).strip()
 
    def _safe_b64_to_text(self, data: str) -> str:
        # Gmail uses web-safe base64; pad and decode robustly
        data = data.replace("-", "+").replace("_", "/")
        padding = "=" * ((4 - len(data) % 4) % 4)
        try:
            raw = base64.b64decode(data + padding, validate=False)
            return unescape(raw.decode("utf-8", errors="replace"))
        except Exception:
            return ""
 
    def _strip_html(self, html: str) -> str:
        # Very lightweight HTML stripper to keep dependencies minimal
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)  # remove scripts/styles
        text = re.sub(r"(?s)<br\s*/?>", "\n", text)
        text = re.sub(r"(?s)</p\s*>", "\n", text)
        text = re.sub(r"(?s)<[^>]+>", "", text)  # remove tags
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
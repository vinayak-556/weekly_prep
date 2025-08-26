# calendar_tool.py
 
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional, Any, List, Dict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import os
import json
import re
from typing import Type
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
 
IST = ZoneInfo("Asia/Kolkata") #zone according to location
 

class FetchUpcomingMeetingsInput(BaseModel):
    # Backward-compat shim: some callers may still send a "query" param.
    # Make it Optional[Any] so even a dict (schema snippet) won't break validation.
    query: Optional[Any] = Field(None, description="Null")
 
    # Optional overrides; if omitted we default to the next 7 days window starting 'now'
    start_iso: Optional[str] = Field(
        None, description="ISO-8601 start in IST; defaults to now"
    )
    end_iso: Optional[str] = Field(
        None, description="ISO-8601 end in IST; defaults to now + 7 days"
    )
 
    # Only include meetings that have Zoom details in location or description
    require_zoom: bool = Field(
        True, description="Only include events containing zoom.us in location/description"
    )


class FetchUpcomingMeetingsTool(BaseTool):
    name: str = "fetch_upcoming_meetings"
    description: str = ( 
        "Fetches upcoming Google Calendar events within the next 7 days (IST). "
        "Returns compact JSON with title/day/start/end/event_link/location/description/attendees. "
        "Optional filter require_zoom=True keeps only Zoom meetings."
    )
    args_schema: Type[BaseModel] = FetchUpcomingMeetingsInput
 
    # --------------------- Public entry ---------------------
 
    def _run(
        self,
        query: Optional[Any] = None,             # backward-compat (ignored)
        start_iso: Optional[str] = None,
        end_iso: Optional[str] = None,
        require_zoom: bool = True,
    ) -> str:
        try:
            service = self._authorize()
            if isinstance(service, str):
                # error JSON from _authorize
                return service
 
            # Determine time window (IST)
            now_ist = datetime.now(IST)
            if start_iso:
                start_dt = self._parse_iso_local(start_iso)
            else:
                start_dt = now_ist
 
            if end_iso:
                end_dt = self._parse_iso_local(end_iso)
            else:
                end_dt = start_dt + timedelta(days=7)
 
            # Convert to RFC3339 UTC for Calendar API
            time_min = start_dt.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
            time_max = end_dt.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
 
            events_result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                maxResults=100,
                orderBy="startTime",
            ).execute()
            events = events_result.get("items", [])
 
            items: List[Dict] = []
            for ev in events:
                if require_zoom and not self._has_zoom(ev):
                    continue
 
                start_raw = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date")
                end_raw = (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date")
 
                start_local = self._to_local(start_raw)
                end_local = self._to_local(end_raw)
 
                attendees = []
                for a in (ev.get("attendees") or []):
                    attendees.append({
                        "name": a.get("displayName"),
                        "email": a.get("email"),
                        "response": a.get("responseStatus"),
                    })
 
                items.append({
                    "title": ev.get("summary") or "No Title",
                    "day": start_local.strftime("%A") if start_local else None,
                    "start_local": start_local.isoformat() if start_local else None,
                    "end_local": end_local.isoformat() if end_local else None,
                    "event_link": ev.get("htmlLink"),
                    "location": ev.get("location"),
                    "description": ev.get("description"),
                    "attendees": attendees,
                })
 
            return json.dumps({"count": len(items), "items": items}, ensure_ascii=False)
 
        except Exception as e:
            return json.dumps({"error": f"Calendar fetch failed: {str(e)}"})
 
    # --------------------- Internals ---------------------
 
    def _authorize(self):
        """
        Build an authenticated Calendar service. Expects one of these env vars to contain
        a JSON string produced by Google OAuth flow:
          - GOOGLE_TKN
        """
        load_dotenv()
 
        token_env_names = ["GOOGLE_TKN"]
        token_json = None
        for name in token_env_names:
            val = os.getenv(name)
            if val:
                token_json = val
                break
 
        if not token_json:
            return json.dumps({"error": "No calendar token JSON found in env (GOOGLE_TKN)"})
 
        try:
            info = json.loads(token_json)
            creds = Credentials.from_authorized_user_info(info)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return build("calendar", "v3", credentials=creds)
        except Exception as e:
            return json.dumps({"error": f"Auth error: {str(e)}"})
 
    def _parse_iso_local(self, iso_str: str) -> datetime:
        """
        Parse an ISO-8601 string and ensure it's in IST timezone.
        """
        dt = datetime.fromisoformat(iso_str)
        # If naive, assume IST
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        else:
            dt = dt.astimezone(IST)
        return dt
 
    def _to_local(self, dt_str: Optional[str]) -> Optional[datetime]:
        if not dt_str:
            return None
        # All-day events provide YYYY-MM-DD
        if len(dt_str) == 10:
            # treat all-day start as 00:00 IST
            dt = datetime.fromisoformat(dt_str).replace(tzinfo=IST, hour=0, minute=0, second=0, microsecond=0)
            return dt
        try:
            return datetime.fromisoformat(dt_str).astimezone(IST)
        except Exception:
            # Some APIs may return 'Z' suffixed strings not parsed by fromisoformat in older versions.
            # As a safe fallback, replace 'Z' with '+00:00' and retry.
            if dt_str.endswith("Z"):
                dt_str = dt_str[:-1] + "+00:00"
                try:
                    return datetime.fromisoformat(dt_str).astimezone(IST)
                except Exception:
                    return None
            return None
 
    def _has_zoom(self, ev: Dict) -> bool:
        text = " ".join([
            ev.get("location") or "",
            ev.get("description") or "",
        ])
        return bool(re.search(r"\bzoom\.us\b", text, flags=re.I))
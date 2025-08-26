from typing import Type
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class GoogleDocInput(BaseModel):
    """Input schema for GoogleDocTool."""
    meeting_summary: str = Field(..., description="The meeting summary text to insert into the document.")

class GoogleDocTool(BaseTool):
    name: str = "GoogleDocTool"
    description: str = "Creates a Google Doc with a custom title and inserts the meeting summary."
    args_schema: Type[BaseModel] = GoogleDocInput

    def _run(self, meeting_summary: str) -> str:
        try:
            # Load env and token JSON
            load_dotenv()
            tkn_json = os.getenv("GOOGLE_TKN_DOC")
            tkn_data = json.loads(tkn_json)

            # Setup credentials
            creds = Credentials(
                token=tkn_data["access_token"],
                refresh_token=tkn_data["refresh_token"],
                token_uri="https://oauth2.googleapis.com/token",
                client_id=tkn_data["client_id"],
                client_secret=tkn_data["client_secret"],
                scopes=tkn_data["scope"].split()
            )

            # Refresh if needed
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())

            # Google Docs API
            docs_service = build("docs", "v1", credentials=creds)
            date = datetime.now().strftime("%A %Y-%m-%d")
            # Create document
            doc = docs_service.documents().create(body={"title":date }).execute()

            # Insert text
            requests = [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": meeting_summary + "\n"
                    }
                }
            ]
            docs_service.documents().batchUpdate(
                documentId=doc["documentId"], body={"requests": requests}
            ).execute()

            # Google Drive API for permissions
            drive_service = build("drive", "v3", credentials=creds)

            # Set to "anyone with link can edit"
            drive_service.permissions().create(
                fileId=doc["documentId"],
                body={"type": "anyone", "role": "writer"},
                fields="id"
            ).execute()

            # Return link
            return f"https://docs.google.com/document/d/{doc['documentId']}/edit"


        except Exception as e:
            return f"Error creating document: {str(e)}"

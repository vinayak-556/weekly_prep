# hubspot_tool.py (replace file)
 
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from hubspot import HubSpot
from hubspot.crm.objects.meetings import PublicObjectSearchRequest as MeetingSearchRequest
from hubspot.crm.contacts import PublicObjectSearchRequest as ContactSearchRequest
from hubspot.crm.objects.exceptions import ApiException as ObjectsApiException
from hubspot.crm.contacts.exceptions import ApiException as ContactsApiException
from hubspot.crm.objects.meetings.exceptions import ApiException as MeetingsApiException
import json, os
from typing import Type
from dotenv import load_dotenv
 
load_dotenv()
 
class HubspotToolInput(BaseModel):
    meeting_title: str = Field(..., description='Title of the event from the calendar')
    email: str = Field(..., description='Email of the attendee from the event')
 
class HubSpotSearchTool(BaseTool):
    name: str = "HubSpotSearchTool"
    description: str = (
        "Search HubSpot for a meeting, contact, and associated companies/deals. "
        "Inputs: meeting_title, email. Returns compact JSON."
    )
    args_schema: Type[BaseModel] = HubspotToolInput
 
    def _run(self, meeting_title: str, email: str) -> str:
        try:
            client = HubSpot(access_token=os.getenv("HUBSPOT_ACCESS_TKN"))
        except Exception as e:
            return json.dumps({"found": False, "reason": f"Auth error: {str(e)}"})
 
        meeting_obj = None
        contact_obj = None
        companies = []
        deals = []
 
        # 1) meeting by title (best effort)
        try:
            mreq = MeetingSearchRequest(query=meeting_title, limit=1)
            mres = client.crm.objects.meetings.search_api.do_search(public_object_search_request=mreq)
            if mres and mres.results:
                meeting_obj = mres.results[0].properties or {}
        except Exception:
            meeting_obj = None
 
        # 2) contact by email + assoc
        try:
            contact = client.crm.objects.basic_api.get_by_id(
                object_type="contacts",
                object_id=email,
                id_property="email",
                properties=["firstname", "lastname", "email", "phone", "lifecyclestage", "linkedinbio", "hs_linkedinid", "hs_linkedinbio"],
                associations=["companies", "deals", "meetings"],
            )
            contact_obj = contact.properties or {}
 
            # companies
            if getattr(contact, "associations", None) and "companies" in contact.associations:
                for company_assoc in contact.associations["companies"].results[:3]:
                    try:
                        comp = client.crm.objects.basic_api.get_by_id("companies", company_assoc.id)
                        companies.append(comp.properties or {})
                    except Exception:
                        continue
 
            # deals
            if getattr(contact, "associations", None) and "deals" in contact.associations:
                for deal_assoc in contact.associations["deals"].results[:3]:
                    try:
                        dl = client.crm.objects.basic_api.get_by_id("deals", deal_assoc.id)
                        deals.append(dl.properties or {})
                    except Exception:
                        continue
 
        except (ObjectsApiException, ContactsApiException):
            contact_obj = None
        except Exception:
            contact_obj = None
 
        has_anything = any([meeting_obj, contact_obj, companies, deals])
        if not has_anything:
            return json.dumps({"found": False, "reason": "No HubSpot data found"})
 
        return json.dumps({
            "found": True,
            "meeting": meeting_obj or {},
            "contact": contact_obj or {},
            "companies": companies,
            "deals": deals
        }, ensure_ascii=False)
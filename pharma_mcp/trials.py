"""ClinicalTrials.gov API v2. Docs: https://clinicaltrials.gov/data-api/api"""

from __future__ import annotations

import re
from typing import Any

from pharma_mcp.http import ApiClient, NotFound

BASE = "https://clinicaltrials.gov/api/v2"
STATUSES = {
    "RECRUITING",
    "NOT_YET_RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "COMPLETED",
    "TERMINATED",
    "WITHDRAWN",
    "SUSPENDED",
    "ENROLLING_BY_INVITATION",
    "UNKNOWN",
    "WITHHELD",
    "AVAILABLE",
    "NO_LONGER_AVAILABLE",
    "TEMPORARILY_NOT_AVAILABLE",
    "APPROVED_FOR_MARKETING",
}
PHASES = {"EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"}


def _summary(study: dict[str, Any]) -> dict[str, Any]:
    p = study.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    status = p.get("statusModule", {})
    design = p.get("designModule", {})
    nct = ident.get("nctId")
    return {
        "nct_id": nct,
        "title": ident.get("briefTitle"),
        "status": status.get("overallStatus"),
        "phases": design.get("phases", []),
        "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
        "start_date": (status.get("startDateStruct") or {}).get("date"),
        "primary_completion": (status.get("primaryCompletionDateStruct") or {}).get("date"),
        "sponsor": ((p.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get(
            "name"
        ),
        "conditions": (p.get("conditionsModule") or {}).get("conditions", []),
        "interventions": [
            i.get("name") for i in (p.get("armsInterventionsModule") or {}).get("interventions", [])
        ],
        "locations": len((p.get("contactsLocationsModule") or {}).get("locations", [])),
        "url": f"https://clinicaltrials.gov/study/{nct}" if nct else None,
    }


class Trials:
    def __init__(self, client: ApiClient | None = None) -> None:
        self.client = client or ApiClient(BASE)

    async def search(
        self,
        condition: str | None = None,
        intervention: str | None = None,
        status: str | None = None,
        phase: str | None = None,
        sponsor: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        if not (condition or intervention or sponsor):
            raise ValueError("give at least one of condition, intervention or sponsor")
        if status and status.upper() not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        if phase and phase.upper() not in PHASES:
            raise ValueError(f"phase must be one of {sorted(PHASES)}")
        params: dict[str, Any] = {
            "query.cond": condition,
            "query.intr": intervention,
            "query.spons": sponsor,
            "filter.overallStatus": status.upper() if status else None,
            "filter.advanced": f"AREA[Phase]{phase.upper()}" if phase else None,
            "pageSize": min(max(limit, 1), 50),
            "countTotal": "true",
            "format": "json",
        }
        data = await self.client.get("/studies", params)
        return {
            "total": data.get("totalCount"),
            "studies": [_summary(s) for s in data.get("studies", [])],
        }

    async def get(self, nct_id: str) -> dict[str, Any]:
        nct_id = nct_id.strip().upper()
        if not re.fullmatch(r"NCT\d{8}", nct_id):
            raise ValueError("nct_id must look like NCT01234567")
        try:
            study = await self.client.get(f"/studies/{nct_id}", {"format": "json"})
        except NotFound:
            return {"error": f"{nct_id} not found"}
        out = _summary(study)
        p = study.get("protocolSection", {})
        elig = p.get("eligibilityModule", {})
        out |= {
            "brief_summary": (p.get("descriptionModule") or {}).get("briefSummary"),
            "eligibility": {
                "criteria": elig.get("eligibilityCriteria"),
                "sex": elig.get("sex"),
                "min_age": elig.get("minimumAge"),
                "max_age": elig.get("maximumAge"),
                "healthy_volunteers": elig.get("healthyVolunteers"),
            },
            "primary_outcomes": [
                o.get("measure") for o in (p.get("outcomesModule") or {}).get("primaryOutcomes", [])
            ],
        }
        return out

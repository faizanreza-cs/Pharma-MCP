"""openFDA: drug labels, adverse event reports (FAERS) and enforcement reports (recalls).

Docs: https://open.fda.gov/apis/  Set OPENFDA_API_KEY for higher rate limits.
"""

from __future__ import annotations

import os
import re
from typing import Any

from pharma_mcp.http import ApiClient, NotFound
from pharma_mcp.signals import disproportionality, table

BASE = "https://api.fda.gov"
FAERS_NOTE = (
    "FAERS contains voluntary reports. Counts show what was reported, not how often a drug "
    "causes an event, and do not establish causation."
)


def _q(value: str) -> str:
    """Quote a search term for openFDA (drop quotes and backslashes, collapse spaces)."""
    v = re.sub(r"\s+", " ", re.sub(r'[\\"]', "", value)).strip()
    if not v:
        raise ValueError("search term is empty")
    return f'"{v}"'


def _first(v: Any) -> Any:
    return v[0] if isinstance(v, list) and v else v


def _clip(v: Any, n: int = 800) -> str | None:
    s = _first(v)
    if not s:
        return None
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


class OpenFDA:
    def __init__(self, client: ApiClient | None = None) -> None:
        key = os.environ.get("OPENFDA_API_KEY")
        self.client = client or ApiClient(BASE, default_params={"api_key": key} if key else {})

    async def _total(self, path: str, search: str | None) -> int:
        try:
            data = await self.client.get(path, {"search": search, "limit": 1})
        except NotFound:
            return 0
        return int(data["meta"]["results"]["total"])

    # ------------------------------------------------------------------ labels
    async def search_labels(self, drug: str, limit: int = 3) -> list[dict[str, Any]]:
        q = _q(drug)
        search = f"openfda.brand_name:{q} OR openfda.generic_name:{q}"
        try:
            data = await self.client.get("/drug/label.json", {"search": search, "limit": limit})
        except NotFound:
            return []
        out = []
        for r in data.get("results", []):
            o = r.get("openfda", {})
            out.append(
                {
                    "brand_name": _first(o.get("brand_name")),
                    "generic_name": _first(o.get("generic_name")),
                    "manufacturer": _first(o.get("manufacturer_name")),
                    "route": o.get("route"),
                    "effective_date": r.get("effective_time"),
                    "boxed_warning": _clip(r.get("boxed_warning")),
                    "indications_and_usage": _clip(r.get("indications_and_usage")),
                    "contraindications": _clip(r.get("contraindications")),
                    "warnings_and_cautions": _clip(
                        r.get("warnings_and_cautions") or r.get("warnings")
                    ),
                    "adverse_reactions": _clip(r.get("adverse_reactions")),
                    "set_id": r.get("set_id"),
                    "source": f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={r.get('set_id')}",
                }
            )
        return out

    # ------------------------------------------------------------------ adverse events
    async def top_reactions(
        self, drug: str, limit: int = 10, serious_only: bool = False
    ) -> dict[str, Any]:
        search = f"patient.drug.medicinalproduct:{_q(drug)}"
        if serious_only:
            search += " AND serious:1"
        total = await self._total("/drug/event.json", search)
        try:
            data = await self.client.get(
                "/drug/event.json",
                {
                    "search": search,
                    "count": "patient.reaction.reactionmeddrapt.exact",
                    "limit": limit,
                },
            )
            rows = data.get("results", [])
        except NotFound:
            rows = []
        return {
            "drug": drug,
            "serious_only": serious_only,
            "total_reports": total,
            "reactions": [
                {
                    "reaction": r["term"],
                    "reports": r["count"],
                    "share_of_reports": round(r["count"] / total, 4) if total else None,
                }
                for r in rows
            ],
            "note": FAERS_NOTE,
        }

    async def signal(self, drug: str, reaction: str) -> dict[str, Any]:
        d = f"patient.drug.medicinalproduct:{_q(drug)}"
        # .exact matches one MedDRA term, the same field get_adverse_events counts
        e = f"patient.reaction.reactionmeddrapt.exact:{_q(reaction.upper())}"
        drug_event = await self._total("/drug/event.json", f"{d} AND {e}")
        drug_total = await self._total("/drug/event.json", d)
        event_total = await self._total("/drug/event.json", e)
        all_reports = await self._total("/drug/event.json", None)
        result: dict[str, Any] = {
            "drug": drug,
            "reaction": reaction,
            "counts": {
                "drug_and_reaction": drug_event,
                "drug_total": drug_total,
                "reaction_total": event_total,
                "all_reports": all_reports,
            },
        }
        if drug_total == 0:
            result["error"] = f"no FAERS reports found for {drug!r}; try the generic name"
            return result
        if event_total == 0:
            result["error"] = (
                f"no FAERS reports found for reaction {reaction!r}; use a MedDRA preferred term"
            )
            return result
        a, b, c, dd = table(drug_event, drug_total, event_total, all_reports)
        result["disproportionality"] = disproportionality(a, b, c, dd).to_dict()
        result["note"] = (
            "A statistical association in voluntary reports, to prompt review. " + FAERS_NOTE
        )
        return result

    # ------------------------------------------------------------------ recalls
    async def recalls(self, drug: str, limit: int = 5) -> list[dict[str, Any]]:
        q = _q(drug)
        search = f"product_description:{q} OR openfda.generic_name:{q} OR openfda.brand_name:{q}"
        try:
            data = await self.client.get(
                "/drug/enforcement.json",
                {"search": search, "limit": limit, "sort": "report_date:desc"},
            )
        except NotFound:
            return []
        return [
            {
                "recall_number": r.get("recall_number"),
                "classification": r.get("classification"),
                "status": r.get("status"),
                "reason": _clip(r.get("reason_for_recall"), 400),
                "product": _clip(r.get("product_description"), 300),
                "firm": r.get("recalling_firm"),
                "initiated": r.get("recall_initiation_date"),
                "report_date": r.get("report_date"),
            }
            for r in data.get("results", [])
        ]

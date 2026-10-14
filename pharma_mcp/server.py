"""pharma-mcp server: public drug-safety and clinical-trial data as MCP tools.

Run over stdio (default, for desktop assistants and IDEs):
    pharma-mcp
or over HTTP:
    pharma-mcp --transport streamable-http --port 8000
"""

from __future__ import annotations

import argparse
from typing import Any

from mcp.server.mcpserver import MCPServer

from pharma_mcp import __version__
from pharma_mcp.http import UpstreamError
from pharma_mcp.openfda import OpenFDA
from pharma_mcp.trials import Trials

INSTRUCTIONS = """\
Tools for public US drug and clinical-trial data (openFDA and ClinicalTrials.gov).
- Prefer generic drug names (e.g. "semaglutide", not a brand) for adverse-event tools.
- Adverse-event (FAERS) results are voluntary reports: present counts and signals as
  associations, never as proof that a drug causes an event, and never as medical advice.
- Cite the source links the tools return.
"""

mcp = MCPServer(
    name="pharma-mcp",
    version=__version__,
    instructions=INSTRUCTIONS,
    website_url="https://github.com/faizanreza-cs/pharma-mcp",
)
_fda = OpenFDA()
_trials = Trials()


def _err(e: Exception) -> dict[str, Any]:
    return {"error": f"{type(e).__name__}: {e}"}


@mcp.tool(
    description="Search FDA drug labels (package inserts) by brand or generic name. "
    "Returns boxed warning, indications, contraindications, warnings and "
    "adverse reactions sections, trimmed, with a DailyMed link."
)
async def search_drug_labels(drug: str, limit: int = 3) -> dict[str, Any]:
    try:
        return {"labels": await _fda.search_labels(drug, max(1, min(limit, 10)))}
    except (ValueError, UpstreamError) as e:
        return _err(e)


@mcp.tool(
    description="Most frequently reported adverse reactions for a drug in FAERS "
    "(FDA Adverse Event Reporting System), with report counts. Optionally "
    "only serious reports."
)
async def get_adverse_events(
    drug: str, limit: int = 10, serious_only: bool = False
) -> dict[str, Any]:
    try:
        return await _fda.top_reactions(drug, max(1, min(limit, 50)), serious_only)
    except (ValueError, UpstreamError) as e:
        return _err(e)


@mcp.tool(
    description="Pharmacovigilance signal check for a drug-reaction pair in FAERS: "
    "proportional reporting ratio (PRR) and reporting odds ratio (ROR) with "
    "95% confidence intervals, Yates chi-squared, and whether it meets the "
    "Evans signal criteria. Use MedDRA preferred terms, e.g. 'PANCREATITIS'."
)
async def signal_check(drug: str, reaction: str) -> dict[str, Any]:
    try:
        return await _fda.signal(drug, reaction)
    except (ValueError, UpstreamError) as e:
        return _err(e)


@mcp.tool(
    description="Recent FDA drug recalls (enforcement reports) matching a drug name, "
    "with classification (Class I is most serious), reason and status."
)
async def drug_recalls(drug: str, limit: int = 5) -> dict[str, Any]:
    try:
        return {"recalls": await _fda.recalls(drug, max(1, min(limit, 25)))}
    except (ValueError, UpstreamError) as e:
        return _err(e)


@mcp.tool(
    description="Search ClinicalTrials.gov by condition, intervention and/or sponsor. "
    "Filter by status (e.g. RECRUITING, COMPLETED) and phase (PHASE1, PHASE2, "
    "PHASE3, PHASE4). Returns NCT id, title, phase, enrollment, dates, sponsor."
)
async def search_trials(
    condition: str | None = None,
    intervention: str | None = None,
    status: str | None = None,
    phase: str | None = None,
    sponsor: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    try:
        return await _trials.search(condition, intervention, status, phase, sponsor, limit)
    except (ValueError, UpstreamError) as e:
        return _err(e)


@mcp.tool(
    description="Full details of one clinical trial by NCT id: summary, eligibility "
    "criteria, primary outcomes, enrollment, sponsor and status."
)
async def get_trial(nct_id: str) -> dict[str, Any]:
    try:
        return await _trials.get(nct_id)
    except (ValueError, UpstreamError) as e:
        return _err(e)


@mcp.prompt(
    description="Draft a safety brief for a drug from its label, FAERS reports, "
    "recalls and ongoing trials."
)
def drug_safety_brief(drug: str) -> str:
    return (
        f"Prepare a one-page safety brief for {drug}. Use search_drug_labels for the boxed "
        "warning and key warnings, get_adverse_events for the most reported reactions, "
        "signal_check on the two or three reactions that look most specific to this drug, "
        "drug_recalls, and search_trials for recruiting studies. Separate label facts from "
        "spontaneous-report associations, cite every source link, and end with the limitations "
        "of FAERS data."
    )


def main() -> None:
    p = argparse.ArgumentParser(prog="pharma-mcp")
    p.add_argument("--transport", default="stdio", choices=["stdio", "sse", "streamable-http"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    if a.transport == "stdio":
        mcp.run("stdio")
    else:
        mcp.run(a.transport, host=a.host, port=a.port)


if __name__ == "__main__":
    main()

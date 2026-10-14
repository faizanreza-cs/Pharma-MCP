# pharma-mcp

**An MCP server that gives AI assistants FDA drug labels, adverse event reports (FAERS),
recalls and ClinicalTrials.gov, plus pharmacovigilance signal detection.**

[![CI](https://github.com/faizanreza-cs/pharma-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/faizanreza-cs/pharma-mcp/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)
![MCP](https://img.shields.io/badge/MCP-server-6f42c1)
![License](https://img.shields.io/badge/license-MIT-green)

Ask your assistant *"What are the most reported adverse events for semaglutide, and is
pancreatitis disproportionately reported?"* or *"Find recruiting phase 3 trials for type 2
diabetes sponsored by Novo Nordisk"*. It calls these tools, and every answer links back to the
FDA or ClinicalTrials.gov source.

## Tools

| Tool | Source | What it returns |
|---|---|---|
| `search_drug_labels` | openFDA drug labels | Boxed warning, indications, contraindications, warnings, adverse reactions (trimmed), DailyMed link |
| `get_adverse_events` | openFDA FAERS | Most reported reactions with counts and share of reports, optionally serious-only |
| `signal_check` | openFDA FAERS | **PRR and ROR with 95% CIs, Yates chi-squared and the Evans signal flag** for a drug–reaction pair |
| `drug_recalls` | openFDA enforcement | Recalls with Class I/II/III, reason, status, firm, dates |
| `search_trials` | ClinicalTrials.gov v2 | Trials by condition, intervention or sponsor, filtered by status and phase |
| `get_trial` | ClinicalTrials.gov v2 | Summary, eligibility criteria, primary outcomes, enrollment, sponsor |

There's also a prompt, `drug_safety_brief`, that has the assistant combine all six into a
one-page safety brief with sources and limitations.

### How `signal_check` works

From four FAERS counts (drug and reaction, drug, reaction, all reports) it builds the 2×2
table

|  | reaction | other reactions |
|---|---|---|
| **drug** | a | b |
| **other drugs** | c | d |

and computes PRR = [a/(a+b)] / [c/(c+d)] and ROR = ad/bc, with log-normal 95% confidence
intervals and a Yates-corrected chi-squared. A pair is flagged when **PRR ≥ 2, χ² ≥ 4 and at
least 3 cases** (Evans et al., 2001), the screening rule used in pharmacovigilance practice.
When a reaction is reported only for this drug (a zero cell), PRR and ROR use the
Haldane-Anscombe correction (+0.5 per cell), so it can still be flagged. Reactions are
matched as exact MedDRA terms, the same terms `get_adverse_events` lists.

> FAERS holds voluntary reports. A signal is a statistical association that deserves review,
> not proof that the drug causes the event. The server's instructions tell the assistant to
> present results that way and never as medical advice.

## Install

With any MCP-compatible client (desktop assistants, IDE agents), add this to the client's MCP
server config:

```json
{
  "mcpServers": {
    "pharma": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/faizanreza-cs/pharma-mcp", "pharma-mcp"],
      "env": { "OPENFDA_API_KEY": "optional-your-key" }
    }
  }
}
```

Or run it yourself:

```bash
git clone https://github.com/faizanreza-cs/pharma-mcp && cd pharma-mcp
make setup
make run                    # stdio
make http                   # streamable HTTP at http://127.0.0.1:8000/mcp
make inspect                # MCP Inspector (needs Node)
```

An openFDA API key is optional but raises the limits from 1,000 to 120,000 requests per day.
Get one free at https://open.fda.gov/apis/authentication/.

## Built for real use

- **Polite to public APIs:** responses are cached for an hour, requests are spaced out, and
  429 and 5xx responses are retried with backoff, honouring `Retry-After`.
- **Doesn't fail on "no results":** openFDA answers 404 when nothing matches, and the server
  returns an empty list instead of an error.
- **Validated inputs:** NCT id format, trial status and phase enums, empty search terms. Bad
  input returns a clear error message to the model, not an exception.
- **Compact outputs:** long label sections are trimmed so they don't flood the context window.
- **Tests:** 21, all offline. Signal math is checked against hand-computed values,
  including zero-cell cases. Every tool is exercised end to end through a real MCP client
  against mocked HTTP. Retries, `Retry-After` parsing, caching and query escaping are covered.
  CI runs on Python 3.11 to 3.13, plus a Docker build and handshake check.

The test fixtures are hand-made samples in the documented response shapes, not real data
(see `tests/fixtures/README.md`).

```
pharma_mcp/
  server.py    MCP tools + prompt (stdio / HTTP)
  openfda.py   labels, FAERS counts, signal queries, recalls
  trials.py    ClinicalTrials.gov v2 search + detail
  signals.py   PRR / ROR / chi-squared, Evans rule
  http.py      cache, rate limiting, retries
```

## Roadmap

- Bayesian signal scores (EBGM / IC) alongside PRR and ROR
- Time-to-onset and reporter-type breakdowns
- DailyMed SPL section search and label change history
- EMA EudraVigilance and WHO VigiAccess sources

## Need healthcare data connected to your AI tools?

I build MCP servers and AI integrations for pharma, biotech and healthcare teams: internal
data warehouses, safety databases, CTMS, CRM, literature search. Every one gets the same
attention to correctness and compliance as this project.

**Faizan Reza**, AI engineer · [GitHub](https://github.com/faizanreza-cs) · faizanreza01@gmail.com

## License

MIT. Not affiliated with the FDA or NIH. Data come from public APIs and are provided as-is.

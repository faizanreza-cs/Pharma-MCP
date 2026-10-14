"""Disproportionality analysis for spontaneous adverse-event reports.

For a drug D and an event E, the 2x2 contingency table over all reports is:

                 E        not E
    D            a          b
    not D        c          d

PRR = [a/(a+b)] / [c/(c+d)]       ROR = (a*d) / (b*c)

95% confidence intervals use the standard log-normal approximations. When a > 0 and another cell
is 0, PRR and ROR use the Haldane-Anscombe correction (0.5 added to every cell), so a reaction
reported only for this drug still gets a finite, flaggable score. The default signal rule
follows Evans et al. (2001): PRR >= 2, chi-squared (Yates) >= 4 and at least 3 cases.

A signal is a statistical association in voluntary reports, which are subject to under- and
stimulated reporting, confounding by indication and duplicates. It is a reason to look closer,
not evidence that the drug causes the event.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

Z95 = 1.959964


@dataclass(frozen=True)
class Signal:
    a: int
    b: int
    c: int
    d: int
    prr: float | None
    prr_ci: tuple[float, float] | None
    ror: float | None
    ror_ci: tuple[float, float] | None
    chi2_yates: float | None
    is_signal: bool
    rule: str = "Evans 2001: PRR >= 2, chi2 >= 4, cases >= 3"

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("prr", "ror", "chi2_yates"):
            if d[k] is not None:
                d[k] = round(d[k], 3)
        for k in ("prr_ci", "ror_ci"):
            if d[k] is not None:
                d[k] = [round(x, 3) for x in d[k]]
        return d


def table(drug_event: int, drug_total: int, event_total: int, all_reports: int) -> tuple[int, ...]:
    """Build (a, b, c, d) from the four counts an API can return."""
    a = drug_event
    b = drug_total - drug_event
    c = event_total - drug_event
    d = all_reports - drug_total - event_total + drug_event
    if min(a, b, c, d) < 0:
        raise ValueError("inconsistent counts: check that totals cover the same report set")
    return a, b, c, d


def chi2_yates(a: int, b: int, c: int, d: int) -> float | None:
    n = a + b + c + d
    denom = (a + b) * (c + d) * (a + c) * (b + d)
    if denom == 0:
        return None
    return n * max(0.0, abs(a * d - b * c) - n / 2) ** 2 / denom


def disproportionality(
    a: int,
    b: int,
    c: int,
    d: int,
    min_cases: int = 3,
    prr_threshold: float = 2.0,
    chi2_threshold: float = 4.0,
) -> Signal:
    prr = prr_ci = ror = ror_ci = None
    if a > 0:
        ha, hb, hc, hd = (x + 0.5 for x in (a, b, c, d)) if min(b, c, d) == 0 else (a, b, c, d)
        prr = (ha / (ha + hb)) / (hc / (hc + hd))
        se = math.sqrt(1 / ha - 1 / (ha + hb) + 1 / hc - 1 / (hc + hd))
        prr_ci = (math.exp(math.log(prr) - Z95 * se), math.exp(math.log(prr) + Z95 * se))
        ror = (ha * hd) / (hb * hc)
        se = math.sqrt(1 / ha + 1 / hb + 1 / hc + 1 / hd)
        ror_ci = (math.exp(math.log(ror) - Z95 * se), math.exp(math.log(ror) + Z95 * se))
    chi2 = chi2_yates(a, b, c, d)
    is_signal = bool(
        prr is not None
        and chi2 is not None
        and a >= min_cases
        and prr >= prr_threshold
        and chi2 >= chi2_threshold
    )
    return Signal(a, b, c, d, prr, prr_ci, ror, ror_ci, chi2, is_signal)

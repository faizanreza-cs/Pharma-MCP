import math

import pytest

from pharma_mcp.signals import chi2_yates, disproportionality, table


def test_table_from_counts():
    assert table(10, 100, 50, 10_000) == (10, 90, 40, 9_860)
    with pytest.raises(ValueError):
        table(10, 5, 50, 100)


def test_prr_and_ror_hand_checked():
    # a=20, b=80, c=100, d=9800 -> PRR = (20/100)/(100/9900) = 19.8; ROR = 20*9800/(80*100) = 24.5
    s = disproportionality(20, 80, 100, 9800)
    assert s.prr == pytest.approx(19.8)
    assert s.ror == pytest.approx(24.5)
    lo, hi = s.prr_ci
    assert lo < s.prr < hi
    se = math.sqrt(1 / 20 - 1 / 100 + 1 / 100 - 1 / 9900)
    assert lo == pytest.approx(19.8 * math.exp(-1.959964 * se))
    assert s.is_signal


def test_no_signal_when_proportional():
    s = disproportionality(10, 990, 100, 9900)  # same reporting rate inside and outside
    assert s.prr == pytest.approx(1.0) and not s.is_signal


def test_needs_three_cases():
    assert not disproportionality(2, 10, 5, 100_000).is_signal


def test_zero_cells_are_safe():
    s = disproportionality(0, 100, 50, 1000)
    assert s.prr is None and s.ror is None and not s.is_signal
    assert chi2_yates(0, 0, 0, 0) is None


def test_zero_cell_uses_haldane_correction():
    # only this drug reports the reaction (c=0): still a finite PRR and a flagged signal
    s = disproportionality(5, 95, 0, 10**7)
    assert s.prr is not None and s.prr > 2 and s.is_signal
    assert s.c == 0  # reported counts stay uncorrected
    s = disproportionality(3, 0, 10, 1000)  # b=0: ROR is reported too
    assert s.ror is not None and s.ror_ci is not None


def test_query_quoting_strips_escape_characters():
    from pharma_mcp.openfda import _q

    assert _q('a\\" OR x  b') == '"a OR x b"'
    with pytest.raises(ValueError):
        _q(' \\" ')

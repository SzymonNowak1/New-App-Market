"""Unit tests for Buffett/Lynch scoring weights and moat component."""

from buffett_lynch.fundamental_scoring import (
    FundamentalScorer,
    ScoringRules,
    growth_score,
    moat_score,
    quality_score,
)
from buffett_lynch.models import FundamentalSnapshot


def test_total_score_weights_include_moat_component():
    """Verify TotalScore weights (35/20/20/15/10) and MoatScore contribution."""

    # Deterministic component scores so we can assert the weighted sum directly
    snap = FundamentalSnapshot(
        period="2024",
        market_cap=1_000_000_000,
        sector="Tech",
        metrics={
            "quality": 50.0,
            "growth": 40.0,
            "moat": 60.0,
            "value": 30.0,
            "risk": 20.0,
        },
    )

    scorer = FundamentalScorer(
        ScoringRules(
            quality=lambda s: s.metrics["quality"],
            growth=lambda s: s.metrics["growth"],
            moat=lambda s: s.metrics["moat"],
            value=lambda s: s.metrics["value"],
            risk=lambda s: s.metrics["risk"],
        )
    )

    scored = scorer.score("ABC", [snap])[0]

    expected_total = (
        0.35 * snap.metrics["quality"]
        + 0.20 * snap.metrics["growth"]
        + 0.20 * snap.metrics["moat"]
        + 0.15 * snap.metrics["value"]
        + 0.10 * snap.metrics["risk"]
    )

    assert scored.moat == snap.metrics["moat"]
    assert scored.total == expected_total


def test_moat_score_formula():
    """MoatScore should combine gross margin, R&D/Sales, and ROIC trend with 40/30/30 weights."""

    snap = FundamentalSnapshot(
        period="2024",
        market_cap=1_000_000_000,
        sector="Tech",
        metrics={
            "gross_margin_percentile": 75.0,
            "r_and_d_to_sales_percentile": 15.0,
            "roic_trend_percentile": 55.0,
        },
    )

    expected_moat = 0.4 * 75.0 + 0.3 * 15.0 + 0.3 * 55.0

    assert moat_score(snap) == expected_moat


def test_quality_score_includes_roic_trend():
    """QualityScore should reward a rising 5Y ROIC trend in addition to ROE."""

    snap = FundamentalSnapshot(
        period="2024",
        market_cap=1_000_000_000,
        sector="Industrials",
        metrics={
            "roe": 20.0,
            "roic_trend_pct": 60.0,
        },
    )

    # quality_score = 0.9*ROE + 0.1*ROIC_trend_pct
    assert quality_score(snap) == 0.9 * 20.0 + 0.1 * 60.0


def test_moat_score_falls_back_to_median_when_data_missing():
    """Missing moat components should default to median percentiles instead of zero."""

    snap = FundamentalSnapshot(
        period="2024",
        market_cap=500_000_000,
        sector="Consumer",
        metrics={},
    )

    # With all components missing, the median percentile (0.5) should be applied.
    assert moat_score(snap) == 0.5


def test_growth_score_penalizes_revenue_volatility():
    """GrowthScore should subtract a volatility penalty to reward stability."""

    snap = FundamentalSnapshot(
        period="2024",
        market_cap=1_000_000_000,
        sector="Health",
        metrics={
            "growth": 50.0,
            "revenue_volatility_penalty": 12.5,
        },
    )

    assert growth_score(snap) == 37.5


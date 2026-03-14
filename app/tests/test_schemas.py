"""Tests for Pydantic models (typed state)."""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    CompanyAnalysis,
    CompanyDecision,
    CompanyResearch,
    CompanyResearchSet,
    FinancialAnalysis,
    InvestmentDecision,
    RiskAssessment,
    RiskFactor,
)


class TestCompanyResearch:
    def test_roundtrip_serialization(self):
        cr = CompanyResearch(
            ticker="NVDA",
            company_name="NVIDIA Corporation",
            sector="Semiconductors",
            current_price=950.50,
            market_cap="2.3T",
            pe_ratio=65.2,
            revenue_growth="122% YoY",
            analyst_consensus="Strong Buy",
            recent_news=["NVIDIA beats earnings", "New AI chip announced"],
            key_products=["GPUs", "Data center accelerators"],
            competitive_position="Market leader in AI chips",
            negative_news=["Antitrust scrutiny in EU"],
        )
        json_str = cr.model_dump_json()
        parsed = CompanyResearch.model_validate_json(json_str)
        assert parsed.ticker == "NVDA"
        assert parsed.current_price == 950.50
        assert len(parsed.negative_news) == 1

    def test_optional_fields_default_to_none(self):
        cr = CompanyResearch(
            ticker="AMD",
            company_name="AMD",
            sector="Semiconductors",
        )
        assert cr.current_price is None
        assert cr.market_cap is None
        assert cr.recent_news == []
        assert cr.negative_news == []


class TestCompanyResearchSet:
    def test_serialization(self):
        research_set = CompanyResearchSet(
            sector="Semiconductors",
            companies=[
                CompanyResearch(
                    ticker="NVDA",
                    company_name="NVIDIA",
                    sector="Semiconductors",
                ),
                CompanyResearch(
                    ticker="AMD",
                    company_name="AMD",
                    sector="Semiconductors",
                ),
            ],
            research_date="2025-01-15",
        )
        json_str = research_set.model_dump_json()
        parsed = CompanyResearchSet.model_validate_json(json_str)
        assert parsed.sector == "Semiconductors"
        assert len(parsed.companies) == 2
        assert parsed.companies[0].ticker == "NVDA"


class TestFinancialAnalysis:
    def test_serialization(self):
        analysis = FinancialAnalysis(
            sector="Semiconductors",
            company_analyses=[
                CompanyAnalysis(
                    ticker="NVDA",
                    strengths=["AI market leader", "Strong revenue growth"],
                    weaknesses=["High valuation", "Customer concentration"],
                    valuation_assessment="Fairly valued given growth trajectory",
                    growth_outlook="Strong growth expected from AI demand",
                ),
            ],
            comparative_summary="NVDA leads in AI, AMD offers value play",
            top_pick="NVDA - dominant AI position justifies premium",
        )
        json_str = analysis.model_dump_json()
        parsed = FinancialAnalysis.model_validate_json(json_str)
        assert parsed.top_pick.startswith("NVDA")
        assert len(parsed.company_analyses) == 1


class TestRiskAssessment:
    def test_serialization(self):
        assessment = RiskAssessment(
            risks=[
                RiskFactor(
                    category="market",
                    description="AI spending slowdown risk",
                    severity="medium",
                    affected_tickers=["NVDA", "AMD"],
                ),
            ],
            assumptions_challenged=["AI spending will continue to grow"],
            data_gaps=["No insider trading data available"],
            contrarian_view="AI chip demand may plateau in 2025",
            overall_confidence="medium",
        )
        json_str = assessment.model_dump_json()
        parsed = RiskAssessment.model_validate_json(json_str)
        assert len(parsed.risks) == 1
        assert parsed.risks[0].severity == "MEDIUM"
        assert parsed.risks[0].category == "MARKET"
        assert parsed.overall_confidence == "MEDIUM"


class TestInvestmentDecision:
    def test_serialization(self):
        decision = InvestmentDecision(
            sector="Semiconductors",
            company_decisions=[
                CompanyDecision(
                    ticker="NVDA",
                    recommendation="BUY",
                    confidence="high",
                    reasoning="Market leader in AI with strong revenue growth; risks are manageable",
                ),
                CompanyDecision(
                    ticker="AMD",
                    recommendation="HOLD",
                    confidence="medium",
                    reasoning="Solid competitor but valuation risk and market share uncertainty",
                ),
            ],
            top_pick="NVDA",
            top_pick_justification=(
                "NVIDIA's dominant AI chip position and 122% revenue growth "
                "justify its premium valuation. While antitrust scrutiny is a risk, "
                "the AI spending tailwind outweighs near-term concerns."
            ),
            investment_thesis=(
                "The semiconductor sector is driven by AI infrastructure demand. "
                "NVIDIA leads with best-in-class GPUs, while AMD offers a value alternative."
            ),
            key_conditions=[
                "AI infrastructure spending slowdown",
                "Antitrust regulatory action against NVIDIA",
                "AMD gaining significant data center market share",
            ],
        )
        json_str = decision.model_dump_json()
        parsed = InvestmentDecision.model_validate_json(json_str)
        assert parsed.top_pick == "NVDA"
        assert len(parsed.company_decisions) == 2
        assert parsed.company_decisions[0].recommendation == "BUY"
        assert parsed.company_decisions[0].confidence == "HIGH"
        assert parsed.company_decisions[1].confidence == "MEDIUM"
        assert len(parsed.key_conditions) == 3


class TestEnumValidation:
    """Test that enum-like fields are properly validated and normalized."""

    # --- Severity ---
    @pytest.mark.parametrize(
        "input_val,expected",
        [
            ("HIGH", "HIGH"),
            ("high", "HIGH"),
            ("High", "HIGH"),
            ("medium", "MEDIUM"),
            ("LOW", "LOW"),
            ("  low  ", "LOW"),
        ],
    )
    def test_severity_normalization(self, input_val, expected):
        rf = RiskFactor(
            category="MARKET",
            description="test",
            severity=input_val,
            affected_tickers=["AAPL"],
        )
        assert rf.severity == expected

    def test_severity_rejects_invalid(self):
        with pytest.raises(ValidationError):
            RiskFactor(
                category="MARKET",
                description="test",
                severity="CRITICAL",
                affected_tickers=["AAPL"],
            )

    # --- Recommendation ---
    @pytest.mark.parametrize(
        "input_val,expected",
        [
            ("BUY", "BUY"),
            ("buy", "BUY"),
            ("Buy", "BUY"),
            ("hold", "HOLD"),
            ("sell", "SELL"),
        ],
    )
    def test_recommendation_normalization(self, input_val, expected):
        cd = CompanyDecision(
            ticker="AAPL",
            recommendation=input_val,
            confidence="HIGH",
            reasoning="test",
        )
        assert cd.recommendation == expected

    def test_recommendation_rejects_invalid(self):
        with pytest.raises(ValidationError):
            CompanyDecision(
                ticker="AAPL",
                recommendation="STRONG_BUY",
                confidence="HIGH",
                reasoning="test",
            )

    # --- Confidence ---
    @pytest.mark.parametrize(
        "input_val,expected",
        [
            ("HIGH", "HIGH"),
            ("high", "HIGH"),
            ("Medium", "MEDIUM"),
            ("low", "LOW"),
        ],
    )
    def test_confidence_normalization(self, input_val, expected):
        cd = CompanyDecision(
            ticker="AAPL",
            recommendation="BUY",
            confidence=input_val,
            reasoning="test",
        )
        assert cd.confidence == expected

    def test_confidence_rejects_invalid(self):
        with pytest.raises(ValidationError):
            CompanyDecision(
                ticker="AAPL",
                recommendation="BUY",
                confidence="VERY_HIGH",
                reasoning="test",
            )

    # --- Category ---
    @pytest.mark.parametrize(
        "input_val,expected",
        [
            ("MARKET", "MARKET"),
            ("market", "MARKET"),
            ("COMPANY_SPECIFIC", "COMPANY_SPECIFIC"),
            ("company-specific", "COMPANY_SPECIFIC"),
            ("company specific", "COMPANY_SPECIFIC"),
            ("sector", "SECTOR"),
            ("MACRO", "MACRO"),
            ("regulatory", "REGULATORY"),
        ],
    )
    def test_category_normalization(self, input_val, expected):
        rf = RiskFactor(
            category=input_val,
            description="test",
            severity="HIGH",
            affected_tickers=["AAPL"],
        )
        assert rf.category == expected

    def test_category_rejects_invalid(self):
        with pytest.raises(ValidationError):
            RiskFactor(
                category="GEOPOLITICAL",
                description="test",
                severity="HIGH",
                affected_tickers=["AAPL"],
            )

    # --- Overall confidence in RiskAssessment ---
    def test_risk_assessment_confidence_normalization(self):
        ra = RiskAssessment(
            risks=[],
            assumptions_challenged=[],
            data_gaps=[],
            contrarian_view="test",
            overall_confidence="medium",
        )
        assert ra.overall_confidence == "MEDIUM"

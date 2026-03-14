"""Tests for private company verification via confidence scoring."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.models.schemas import CompanyResearch
from app.tools.ticker_validation import CompanyValidationTool


# ---------------------------------------------------------------------------
# Confidence score computation
# ---------------------------------------------------------------------------
class TestComputeConfidence:
    def _make_tool(self) -> CompanyValidationTool:
        return CompanyValidationTool(tavily_client=MagicMock())

    def test_empty_results_returns_zero(self):
        tool = self._make_tool()
        assert tool._compute_confidence("FakeAICo", []) == 0.0

    def test_high_confidence_for_real_company(self):
        """Simulated Tavily results for 'Anthropic' should score well above threshold."""
        tool = self._make_tool()
        results = [
            {
                "title": "Anthropic | AI Safety",
                "url": "https://www.anthropic.com/",
                "content": "Anthropic is an AI safety company...",
                "score": 0.95,
            },
            {
                "title": "Anthropic - Crunchbase",
                "url": "https://www.crunchbase.com/organization/anthropic",
                "content": "Anthropic company profile...",
                "score": 0.90,
            },
            {
                "title": "Anthropic raises $2B - TechCrunch",
                "url": "https://techcrunch.com/anthropic-funding",
                "content": "Anthropic announced a major funding round...",
                "score": 0.88,
            },
            {
                "title": "Anthropic - Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Anthropic",
                "content": "Anthropic is an AI safety startup...",
                "score": 0.85,
            },
            {
                "title": "Anthropic Claude review",
                "url": "https://www.forbes.com/anthropic-claude",
                "content": "Anthropic's Claude assistant...",
                "score": 0.82,
            },
        ]
        score = tool._compute_confidence("Anthropic", results)
        assert score >= 0.7

    def test_low_confidence_for_irrelevant_results(self):
        """Results that don't mention the company name should score low."""
        tool = self._make_tool()
        results = [
            {
                "title": "AI Companies to Watch",
                "url": "https://example.com/ai",
                "content": "Various AI companies are emerging...",
                "score": 0.3,
            },
        ]
        score = tool._compute_confidence("FakeAICo", results)
        assert score < 0.4

    def test_source_quality_boosts_score(self):
        """Results from reputable domains should boost confidence."""
        tool = self._make_tool()
        results = [
            {
                "title": "TestCo funding round",
                "url": "https://www.reuters.com/article/testco",
                "content": "TestCo secured funding...",
                "score": 0.9,
            },
            {
                "title": "TestCo - Crunchbase",
                "url": "https://crunchbase.com/org/testco",
                "content": "TestCo company profile...",
                "score": 0.8,
            },
            {
                "title": "TestCo blog post",
                "url": "https://random-blog.com/post",
                "content": "TestCo is interesting...",
                "score": 0.7,
            },
        ]
        score = tool._compute_confidence("TestCo", results)
        # 2 of 3 reputable + company name in all = strong signal
        assert score > 0.6

    def test_company_own_domain_counts_as_reputable(self):
        """Company's own domain should count toward source quality."""
        tool = self._make_tool()
        results = [
            {
                "title": "Anthropic",
                "url": "https://www.anthropic.com/",
                "content": "Anthropic builds AI systems...",
                "score": 0.95,
            },
        ]
        score = tool._compute_confidence("Anthropic", results)
        # anthropic in anthropic.com → reputable match
        assert score > 0.0


# ---------------------------------------------------------------------------
# _verify_company_exists
# ---------------------------------------------------------------------------
class TestVerifyCompanyExists:
    def test_verified_for_real_company(self):
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [
                {
                    "title": "Anthropic",
                    "url": "https://anthropic.com",
                    "content": "Anthropic is an AI safety company...",
                    "score": 0.95,
                },
                {
                    "title": "Anthropic on Crunchbase",
                    "url": "https://crunchbase.com/anthropic",
                    "content": "Anthropic funding and investors...",
                    "score": 0.9,
                },
                {
                    "title": "Anthropic raises billions",
                    "url": "https://techcrunch.com/anthropic",
                    "content": "Anthropic announced...",
                    "score": 0.88,
                },
            ]
        }
        tool = CompanyValidationTool(tavily_client=mock_client)
        result = tool._verify_company_exists("Anthropic")
        assert result["verification_status"] == "VERIFIED"
        assert result["confidence_score"] >= 0.4
        assert result["verification_warning"] is None

    def test_unverified_for_fake_company(self):
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": []}
        tool = CompanyValidationTool(tavily_client=mock_client)
        result = tool._verify_company_exists("FakeAICo")
        assert result["verification_status"] == "UNVERIFIED"
        assert result["confidence_score"] == 0.0
        assert "LOW CONFIDENCE" in result["verification_warning"]

    def test_search_failed_on_exception(self):
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("API down")
        tool = CompanyValidationTool(tavily_client=mock_client)
        result = tool._verify_company_exists("Anthropic")
        assert result["verification_status"] == "SEARCH_FAILED"
        assert result["confidence_score"] is None
        assert "failed" in result["verification_warning"].lower()

    def test_search_failed_when_no_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            tool = CompanyValidationTool(tavily_client=None)
            tool._tavily = None  # Reset any cached client
            result = tool._verify_company_exists("Anthropic")
            assert result["verification_status"] == "SEARCH_FAILED"
            assert "TAVILY_API_KEY" in result["verification_warning"]

    def test_uses_correct_search_params(self):
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": []}
        tool = CompanyValidationTool(tavily_client=mock_client)
        tool._verify_company_exists("Anthropic")
        mock_client.search.assert_called_once_with(
            query='"Anthropic" company',
            search_depth="basic",
            max_results=5,
            include_answer=False,
        )

    def test_custom_threshold(self):
        """A single low-relevance result should be VERIFIED with low threshold."""
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [
                {
                    "title": "SomeCo",
                    "url": "https://example.com",
                    "content": "SomeCo does things...",
                    "score": 0.5,
                },
            ]
        }

        # Strict threshold → UNVERIFIED
        tool_strict = CompanyValidationTool(
            tavily_client=mock_client, verification_threshold=0.9
        )
        result = tool_strict._verify_company_exists("SomeCo")
        assert result["verification_status"] == "UNVERIFIED"

        # Lenient threshold → VERIFIED
        tool_lenient = CompanyValidationTool(
            tavily_client=mock_client, verification_threshold=0.1
        )
        result = tool_lenient._verify_company_exists("SomeCo")
        assert result["verification_status"] == "VERIFIED"


# ---------------------------------------------------------------------------
# validate_companies integration (with verification)
# ---------------------------------------------------------------------------
class TestValidateCompaniesVerification:
    @patch("app.tools.ticker_validation.yf.Search")
    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_verified_private_company(self, mock_ticker_cls, mock_search_cls):
        mock_ticker_cls.return_value.info = {}
        mock_search_cls.return_value.quotes = []

        mock_tavily = MagicMock()
        mock_tavily.search.return_value = {
            "results": [
                {
                    "title": "Anthropic",
                    "url": "https://anthropic.com",
                    "content": "Anthropic is an AI safety company...",
                    "score": 0.95,
                },
                {
                    "title": "Anthropic on Crunchbase",
                    "url": "https://crunchbase.com/anthropic",
                    "content": "Anthropic funding...",
                    "score": 0.9,
                },
            ]
        }

        tool = CompanyValidationTool(tavily_client=mock_tavily)
        result = json.loads(tool.validate_companies("Anthropic"))

        assert len(result["private_companies"]) == 1
        private = result["private_companies"][0]
        assert private["verification_status"] == "VERIFIED"
        assert private["confidence_score"] >= 0.4
        assert "Verified as a real company" in private["reason"]
        assert result["summary"]["unverified_count"] == 0

    @patch("app.tools.ticker_validation.yf.Search")
    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_unverified_company_includes_warnings(
        self, mock_ticker_cls, mock_search_cls
    ):
        mock_ticker_cls.return_value.info = {}
        mock_search_cls.return_value.quotes = []

        mock_tavily = MagicMock()
        mock_tavily.search.return_value = {"results": []}

        tool = CompanyValidationTool(tavily_client=mock_tavily)
        result = json.loads(tool.validate_companies("FakeAICo"))

        assert len(result["private_companies"]) == 1
        private = result["private_companies"][0]
        assert private["verification_status"] == "UNVERIFIED"
        assert private["confidence_score"] == 0.0
        assert result["summary"]["unverified_count"] == 1
        assert "warnings" in result
        assert any("FakeAICo" in w for w in result["warnings"])

    @patch("app.tools.ticker_validation.yf.Search")
    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_mixed_verified_and_unverified(
        self, mock_ticker_cls, mock_search_cls
    ):
        """One real private company and one fake should get different statuses."""
        mock_ticker_cls.return_value.info = {}
        mock_search_cls.return_value.quotes = []

        mock_tavily = MagicMock()
        # First call: real company (Anthropic), second call: fake
        mock_tavily.search.side_effect = [
            {
                "results": [
                    {
                        "title": "Anthropic AI",
                        "url": "https://anthropic.com",
                        "content": "Anthropic builds AI...",
                        "score": 0.95,
                    },
                    {
                        "title": "Anthropic funding",
                        "url": "https://techcrunch.com/anthropic",
                        "content": "Anthropic raised...",
                        "score": 0.9,
                    },
                    {
                        "title": "Anthropic Wikipedia",
                        "url": "https://wikipedia.org/wiki/Anthropic",
                        "content": "Anthropic is...",
                        "score": 0.85,
                    },
                ]
            },
            {"results": []},
        ]

        tool = CompanyValidationTool(tavily_client=mock_tavily)
        result = json.loads(tool.validate_companies("Anthropic,FakeAICo"))

        assert len(result["private_companies"]) == 2
        assert result["private_companies"][0]["verification_status"] == "VERIFIED"
        assert result["private_companies"][1]["verification_status"] == "UNVERIFIED"
        assert result["summary"]["unverified_count"] == 1
        assert "warnings" in result
        assert any("FakeAICo" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Schema: verification_status field
# ---------------------------------------------------------------------------
class TestVerificationStatusSchema:
    def test_normalization(self):
        cr = CompanyResearch(
            company_name="Test",
            company_type="PRIVATE",
            sector="AI",
            verification_status="verified",
        )
        assert cr.verification_status == "VERIFIED"

    def test_allows_none(self):
        cr = CompanyResearch(
            company_name="Test",
            sector="AI",
        )
        assert cr.verification_status is None
        assert cr.confidence_score is None

    def test_rejects_invalid(self):
        with pytest.raises(ValidationError):
            CompanyResearch(
                company_name="Test",
                company_type="PRIVATE",
                sector="AI",
                verification_status="UNKNOWN",
            )

    @pytest.mark.parametrize(
        "input_val,expected",
        [
            ("VERIFIED", "VERIFIED"),
            ("unverified", "UNVERIFIED"),
            ("search_failed", "SEARCH_FAILED"),
            ("not_applicable", "NOT_APPLICABLE"),
            ("  VERIFIED  ", "VERIFIED"),
        ],
    )
    def test_all_valid_values(self, input_val, expected):
        cr = CompanyResearch(
            company_name="Test",
            company_type="PRIVATE",
            sector="AI",
            verification_status=input_val,
        )
        assert cr.verification_status == expected

    def test_private_company_with_verification(self):
        cr = CompanyResearch(
            company_name="Anthropic",
            company_type="PRIVATE",
            sector="AI",
            verification_status="VERIFIED",
            confidence_score=0.87,
            latest_funding_round="Series D",
        )
        assert cr.verification_status == "VERIFIED"
        assert cr.confidence_score == 0.87

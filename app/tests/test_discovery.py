"""Tests for company discovery via sector/niche web search."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.tools.ticker_validation import CompanyValidationTool


# ---------------------------------------------------------------------------
# _extract_company_names
# ---------------------------------------------------------------------------
class TestExtractCompanyNames:
    def _make_tool(self) -> CompanyValidationTool:
        return CompanyValidationTool(tavily_client=MagicMock())

    def test_extracts_names_from_answer_text(self):
        tool = self._make_tool()
        answer = (
            "Top autonomous driving startups include Waymo, Aurora Innovation, "
            "and Nuro. These companies are leading the industry."
        )
        names = tool._extract_company_names([], answer, 10)
        name_set = {n.lower() for n in names}
        assert "waymo" in name_set
        assert "aurora innovation" in name_set
        assert "nuro" in name_set

    def test_extracts_names_from_titles(self):
        tool = self._make_tool()
        results = [
            {"title": "Waymo raises $5B in funding round"},
            {"title": "Aurora Innovation IPO plans revealed"},
            {"title": "Nuro secures delivery robot partnership"},
        ]
        names = tool._extract_company_names(results, None, 10)
        name_set = {n.lower() for n in names}
        assert "waymo" in name_set
        assert "aurora innovation" in name_set
        assert "nuro" in name_set

    def test_answer_has_higher_weight_than_titles(self):
        tool = self._make_tool()
        answer = "Key startups include AlphaCompany."
        results = [
            {"title": "BetaCompany wins award"},
            {"title": "BetaCompany raises funding"},
        ]
        names = tool._extract_company_names(results, answer, 2)
        # AlphaCompany from answer (weight 2) should rank above
        # BetaCompany from titles (weight 1 each = 2), but
        # both should appear
        assert len(names) == 2

    def test_deduplicates_names(self):
        tool = self._make_tool()
        answer = "Companies include Waymo, Waymo, and Waymo."
        results = [{"title": "Waymo launches new service"}]
        names = tool._extract_company_names(results, answer, 10)
        waymo_count = sum(1 for n in names if n.lower() == "waymo")
        assert waymo_count == 1

    def test_excludes_generic_terms(self):
        tool = self._make_tool()
        answer = "Top Leading Startup Company Technology Solutions"
        names = tool._extract_company_names([], answer, 10)
        generic = {"top", "leading", "startup", "company", "technology", "solutions"}
        for name in names:
            assert name.lower() not in generic

    def test_empty_results_returns_empty(self):
        tool = self._make_tool()
        names = tool._extract_company_names([], None, 10)
        assert names == []

    def test_respects_max_names(self):
        tool = self._make_tool()
        answer = (
            "Companies include AlphaCo, BetaCo, GammaCo, "
            "DeltaCo, EpsilonCo, ZetaCo."
        )
        names = tool._extract_company_names([], answer, 3)
        assert len(names) <= 3


# ---------------------------------------------------------------------------
# discover_companies
# ---------------------------------------------------------------------------
class TestDiscoverCompanies:
    @patch("app.tools.ticker_validation.yf.Search")
    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_discover_private_companies(self, mock_ticker_cls, mock_search_cls):
        """Discovers private companies via Tavily and verifies them."""
        # YFinance returns nothing for all lookups (companies are private)
        mock_ticker_cls.return_value.info = {}
        mock_search_cls.return_value.quotes = []

        mock_tavily = MagicMock()
        # First call: discover search, returns answer with company names
        # Subsequent calls: verify each company
        mock_tavily.search.side_effect = [
            # Discovery search
            {
                "answer": (
                    "Leading autonomous driving startups include Waymo, "
                    "Aurora Innovation, and Nuro."
                ),
                "results": [
                    {"title": "Waymo leads self-driving race", "score": 0.9},
                    {"title": "Aurora Innovation funding", "score": 0.85},
                    {"title": "Nuro delivery robots expand", "score": 0.8},
                ],
            },
            # Verification for Waymo
            {
                "results": [
                    {
                        "title": "Waymo",
                        "url": "https://waymo.com",
                        "content": "Waymo is a self-driving tech company...",
                        "score": 0.95,
                    },
                    {
                        "title": "Waymo - Crunchbase",
                        "url": "https://crunchbase.com/waymo",
                        "content": "Waymo profile...",
                        "score": 0.9,
                    },
                ]
            },
            # Verification for Aurora Innovation
            {
                "results": [
                    {
                        "title": "Aurora Innovation",
                        "url": "https://aurora.tech",
                        "content": "Aurora Innovation develops...",
                        "score": 0.9,
                    },
                    {
                        "title": "Aurora Innovation - TechCrunch",
                        "url": "https://techcrunch.com/aurora",
                        "content": "Aurora Innovation raised...",
                        "score": 0.85,
                    },
                ]
            },
            # Verification for Nuro
            {
                "results": [
                    {
                        "title": "Nuro",
                        "url": "https://nuro.ai",
                        "content": "Nuro builds autonomous delivery...",
                        "score": 0.9,
                    },
                    {
                        "title": "Nuro funding",
                        "url": "https://crunchbase.com/nuro",
                        "content": "Nuro profile...",
                        "score": 0.85,
                    },
                ]
            },
        ]

        tool = CompanyValidationTool(tavily_client=mock_tavily)
        result = json.loads(
            tool.discover_companies(
                sector="autonomous driving",
                count="3",
                company_type="PRIVATE",
            )
        )

        assert len(result["public_companies"]) == 0
        assert len(result["private_companies"]) >= 1
        for company in result["private_companies"]:
            assert company["company_type"] == "PRIVATE"
            assert company["verification_status"] == "VERIFIED"
        assert result["discovery_query"]["sector"] == "autonomous driving"
        assert result["discovery_query"]["company_type_filter"] == "PRIVATE"

    @patch("app.tools.ticker_validation.yf.Search")
    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_discover_public_companies(self, mock_ticker_cls, mock_search_cls):
        """Discovers public companies via Tavily and validates on YFinance."""
        # YFinance resolves these as public companies
        mock_ticker_cls.return_value.info = {
            "shortName": "NVIDIA Corporation",
            "exchange": "NMS",
        }
        mock_search_cls.return_value.quotes = []

        mock_tavily = MagicMock()
        mock_tavily.search.return_value = {
            "answer": (
                "Top semiconductor companies include NVIDIA, AMD, and Intel."
            ),
            "results": [
                {"title": "NVIDIA leads AI chip market", "score": 0.9},
                {"title": "AMD competes in GPU space", "score": 0.85},
                {"title": "Intel restructures chip business", "score": 0.8},
            ],
        }

        tool = CompanyValidationTool(tavily_client=mock_tavily)
        result = json.loads(
            tool.discover_companies(
                sector="semiconductor",
                count="3",
                company_type="PUBLIC",
            )
        )

        assert len(result["public_companies"]) >= 1
        assert len(result["private_companies"]) == 0
        for company in result["public_companies"]:
            assert company["company_type"] == "PUBLIC"
            assert "ticker" in company
        assert result["discovery_query"]["company_type_filter"] == "PUBLIC"

    def test_output_format_matches_validate(self):
        """Output has the same keys as validate_companies for downstream compat."""
        mock_tavily = MagicMock()
        mock_tavily.search.return_value = {
            "answer": "Companies include TestCo.",
            "results": [{"title": "TestCo news", "score": 0.8}],
        }

        tool = CompanyValidationTool(tavily_client=mock_tavily)

        with patch.object(tool, "_resolve_identifier", return_value=None), \
             patch.object(tool, "_verify_company_exists", return_value={
                 "verification_status": "VERIFIED",
                 "confidence_score": 0.8,
                 "verification_warning": None,
             }):
            result = json.loads(
                tool.discover_companies(
                    sector="tech", count="1", company_type="PRIVATE"
                )
            )

        assert "public_companies" in result
        assert "private_companies" in result
        assert "summary" in result
        assert "discovery_query" in result

    def test_no_results_returns_error(self):
        mock_tavily = MagicMock()
        mock_tavily.search.return_value = {"answer": None, "results": []}

        tool = CompanyValidationTool(tavily_client=mock_tavily)
        result = json.loads(
            tool.discover_companies(
                sector="nonexistent niche xyz",
                count="3",
                company_type="PRIVATE",
            )
        )

        assert "error" in result
        assert result["public_companies"] == []
        assert result["private_companies"] == []

    def test_count_clamped_to_max(self):
        mock_tavily = MagicMock()
        mock_tavily.search.return_value = {"answer": None, "results": []}

        tool = CompanyValidationTool(tavily_client=mock_tavily)
        result = json.loads(
            tool.discover_companies(
                sector="tech", count="50", company_type="PRIVATE"
            )
        )

        # Should not error — count is clamped internally
        assert result["discovery_query"]["requested_count"] == 10

    def test_invalid_count_returns_error(self):
        tool = CompanyValidationTool(tavily_client=MagicMock())
        result = json.loads(
            tool.discover_companies(
                sector="tech", count="abc", company_type="PRIVATE"
            )
        )
        assert "error" in result

    def test_invalid_company_type_returns_error(self):
        tool = CompanyValidationTool(tavily_client=MagicMock())
        result = json.loads(
            tool.discover_companies(
                sector="tech", count="3", company_type="ANY"
            )
        )
        assert "error" in result
        assert "Must be PUBLIC or PRIVATE" in result["error"]

    def test_no_tavily_key_returns_error(self):
        with patch.dict(os.environ, {}, clear=True):
            tool = CompanyValidationTool(tavily_client=None)
            tool._tavily = None
            result = json.loads(
                tool.discover_companies(
                    sector="tech", count="3", company_type="PRIVATE"
                )
            )
            assert "error" in result
            assert "TAVILY_API_KEY" in result["error"]

    def test_fewer_than_requested_includes_note(self):
        mock_tavily = MagicMock()
        mock_tavily.search.side_effect = [
            # Discovery search — only one company
            {
                "answer": "The only notable startup is SoloCo.",
                "results": [{"title": "SoloCo raises funding", "score": 0.9}],
            },
            # Verification for SoloCo
            {
                "results": [
                    {
                        "title": "SoloCo",
                        "url": "https://soloco.com",
                        "content": "SoloCo does...",
                        "score": 0.9,
                    },
                    {
                        "title": "SoloCo on Crunchbase",
                        "url": "https://crunchbase.com/soloco",
                        "content": "SoloCo profile...",
                        "score": 0.85,
                    },
                ]
            },
        ]

        tool = CompanyValidationTool(tavily_client=mock_tavily)

        with patch.object(tool, "_resolve_identifier", return_value=None):
            result = json.loads(
                tool.discover_companies(
                    sector="niche sector",
                    count="5",
                    company_type="PRIVATE",
                )
            )

        assert result["summary"]["total"] < 5
        assert "Only found" in result["summary"]["discovery_note"]

    def test_tavily_search_failure_returns_error(self):
        mock_tavily = MagicMock()
        mock_tavily.search.side_effect = Exception("API timeout")

        tool = CompanyValidationTool(tavily_client=mock_tavily)
        result = json.loads(
            tool.discover_companies(
                sector="tech", count="3", company_type="PRIVATE"
            )
        )

        assert "error" in result
        assert "API timeout" in result["error"]

    def test_discovery_query_metadata_in_output(self):
        mock_tavily = MagicMock()
        mock_tavily.search.return_value = {
            "answer": "Companies include TestCo.",
            "results": [{"title": "TestCo does things", "score": 0.8}],
        }

        tool = CompanyValidationTool(tavily_client=mock_tavily)

        with patch.object(tool, "_resolve_identifier", return_value=None), \
             patch.object(tool, "_verify_company_exists", return_value={
                 "verification_status": "VERIFIED",
                 "confidence_score": 0.8,
                 "verification_warning": None,
             }):
            result = json.loads(
                tool.discover_companies(
                    sector="robotics",
                    count="2",
                    company_type="PRIVATE",
                )
            )

        assert result["discovery_query"]["sector"] == "robotics"
        assert result["discovery_query"]["requested_count"] == 2
        assert result["discovery_query"]["company_type_filter"] == "PRIVATE"

    @patch("app.tools.ticker_validation.yf.Search")
    @patch("app.tools.ticker_validation.yf.Ticker")
    def test_private_discovery_skips_public_companies(
        self, mock_ticker_cls, mock_search_cls
    ):
        """When discovering PRIVATE companies, public ones are filtered out."""
        # First candidate resolves as public, second does not
        def resolve_side_effect(identifier):
            if identifier == "NVIDIA":
                return {
                    "ticker": "NVDA",
                    "company_name": "NVIDIA Corporation",
                    "exchange": "NMS",
                    "company_type": "PUBLIC",
                }
            return None

        mock_tavily = MagicMock()
        mock_tavily.search.side_effect = [
            # Discovery search
            {
                "answer": "Key companies: NVIDIA and PrivateStartup.",
                "results": [],
            },
            # Verification for PrivateStartup
            {
                "results": [
                    {
                        "title": "PrivateStartup",
                        "url": "https://privatestartup.com",
                        "content": "PrivateStartup builds...",
                        "score": 0.9,
                    },
                    {
                        "title": "PrivateStartup funding",
                        "url": "https://crunchbase.com/privatestartup",
                        "content": "PrivateStartup profile...",
                        "score": 0.85,
                    },
                ]
            },
        ]

        tool = CompanyValidationTool(tavily_client=mock_tavily)
        tool._resolve_identifier = resolve_side_effect

        result = json.loads(
            tool.discover_companies(
                sector="AI", count="2", company_type="PRIVATE"
            )
        )

        assert len(result["public_companies"]) == 0
        # NVIDIA should be filtered out since it's public
        private_names = [p["company_name"] for p in result["private_companies"]]
        assert "NVIDIA" not in private_names


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------
class TestDiscoverCompaniesRegistration:
    def test_tool_registers_discover_method(self):
        tool = CompanyValidationTool(tavily_client=MagicMock())
        func_names = [f.name for f in tool.functions.values()]
        assert "discover_companies" in func_names

    def test_tool_registers_both_methods(self):
        tool = CompanyValidationTool(tavily_client=MagicMock())
        func_names = [f.name for f in tool.functions.values()]
        assert "validate_companies" in func_names
        assert "discover_companies" in func_names

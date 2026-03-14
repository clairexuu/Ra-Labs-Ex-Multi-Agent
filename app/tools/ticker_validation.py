"""Company validation and discovery tool for classifying and finding companies."""

import contextlib
import io
import json
import os
import re
import sys
from typing import Any
from urllib.parse import urlparse

import yfinance as yf
from agno.tools import Toolkit

_REPUTABLE_DOMAINS = frozenset(
    {
        "reuters.com",
        "bloomberg.com",
        "cnbc.com",
        "wsj.com",
        "ft.com",
        "nytimes.com",
        "bbc.com",
        "techcrunch.com",
        "forbes.com",
        "businessinsider.com",
        "crunchbase.com",
        "pitchbook.com",
        "linkedin.com",
        "theverge.com",
        "wired.com",
        "arstechnica.com",
        "venturebeat.com",
        "wikipedia.org",
        "apnews.com",
    }
)

DEFAULT_VERIFICATION_THRESHOLD = 0.4
MAX_DISCOVERY_COUNT = 10

# Words to ignore when extracting company names from search results
_DISCOVERY_STOP_WORDS = frozenset(
    {
        "ai", "the", "top", "best", "leading", "emerging", "new", "most",
        "largest", "biggest", "fastest", "growing", "innovative",
        "startup", "startups", "company", "companies", "firm", "firms",
        "inc", "corp", "corporation", "llc", "ltd", "co",
        "stock", "stocks", "share", "shares", "market", "markets",
        "sector", "industry", "publicly", "traded", "private", "public",
        "investment", "venture", "capital", "fund", "funds",
        "technology", "technologies", "tech", "solutions", "services",
        "group", "holdings", "global", "international", "world",
        "here", "are", "some", "list", "these", "this", "that",
        "key", "major", "notable", "important", "popular",
        "ipo", "ceo", "cto", "cfo", "coo",
    }
)


class CompanyValidationTool(Toolkit):
    """Validates, classifies, and discovers company identifiers.

    Provides two main capabilities:
    - validate_companies: Classify known company names/tickers as public or private
    - discover_companies: Search for companies in a sector/niche via web search

    Private companies are verified via Tavily web search with a confidence
    score that gates VERIFIED vs. UNVERIFIED status.
    """

    def __init__(
        self,
        tavily_client: Any | None = None,
        verification_threshold: float = DEFAULT_VERIFICATION_THRESHOLD,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name="company_validation",
            tools=[self.validate_companies, self.discover_companies],
            **kwargs,
        )
        self._tavily = tavily_client
        self._verification_threshold = verification_threshold

    # ------------------------------------------------------------------
    # Tavily client (lazy init)
    # ------------------------------------------------------------------

    def _get_tavily_client(self) -> Any | None:
        """Get or lazily create the Tavily client. Returns None if no API key."""
        if self._tavily is not None:
            return self._tavily
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return None
        from tavily import TavilyClient

        self._tavily = TavilyClient(api_key=api_key)
        return self._tavily

    # ------------------------------------------------------------------
    # YFinance lookup helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_plausible_ticker(symbol: str) -> bool:
        """Return True if *symbol* looks like a real ticker symbol.

        Rejects strings with spaces, longer than 10 chars, or containing
        characters outside [A-Z0-9.-] — which filters out full phrases
        the LLM sometimes passes (e.g. "TOP SELF DRIVING CAR").
        """
        return bool(symbol) and len(symbol) <= 10 and re.fullmatch(r"[A-Z0-9.\-]+", symbol) is not None

    def _try_direct_ticker(self, symbol: str) -> dict[str, str] | None:
        """Try looking up a symbol directly as a ticker on YFinance."""
        if not self._is_plausible_ticker(symbol):
            return None
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                info = yf.Ticker(symbol).info
            if info and info.get("shortName"):
                return {
                    "ticker": symbol,
                    "company_name": info.get("shortName", symbol),
                    "exchange": info.get("exchange", "Unknown"),
                    "company_type": "PUBLIC",
                }
        except Exception:
            pass
        return None

    def _search_by_name(self, name: str) -> dict[str, str] | None:
        """Search YFinance by company name with fuzzy matching."""
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                search = yf.Search(
                    name, max_results=5, enable_fuzzy_query=True, news_count=0
                )
            for quote in search.quotes:
                if quote.get("quoteType") == "EQUITY":
                    symbol = quote.get("symbol", "")
                    result = self._try_direct_ticker(symbol)
                    if result:
                        return result
        except Exception:
            pass
        return None

    def _resolve_identifier(self, identifier: str) -> dict[str, str] | None:
        """Resolve a company identifier (ticker or name) to a public company.

        Tries direct ticker lookup first, then falls back to a fuzzy
        name search. Returns None if the company cannot be found.
        """
        # Step 1: try as a direct ticker symbol
        result = self._try_direct_ticker(identifier.strip().upper())
        if result:
            return result

        # Step 2: search by company name (handles names and typos)
        return self._search_by_name(identifier)

    # ------------------------------------------------------------------
    # Private company verification via Tavily
    # ------------------------------------------------------------------

    def _compute_confidence(
        self, company_name: str, results: list[dict]
    ) -> float:
        """Compute confidence score that a company exists based on search results.

        Combines four weighted signals:
          - result_count  (0.3): more results = more likely real
          - avg_relevance (0.3): average Tavily relevance score
          - name_match    (0.2): fraction of results mentioning the company name
          - source_quality(0.2): fraction from reputable domains
        """
        if not results:
            return 0.0

        # Signal 1: Result count
        count = len(results)
        if count >= 4:
            result_count_score = 1.0
        elif count == 3:
            result_count_score = 0.8
        elif count == 2:
            result_count_score = 0.6
        elif count == 1:
            result_count_score = 0.3
        else:
            result_count_score = 0.0

        # Signal 2: Average Tavily relevance score
        avg_relevance = sum(r.get("score", 0.0) for r in results) / len(results)

        # Signal 3: Name match frequency
        name_lower = company_name.lower()
        matches = sum(
            1
            for r in results
            if name_lower in r.get("title", "").lower()
            or name_lower in r.get("content", "").lower()
        )
        name_match_score = matches / len(results)

        # Signal 4: Source quality
        reputable_count = 0
        name_slug = company_name.lower().replace(" ", "")
        for r in results:
            try:
                domain = urlparse(r.get("url", "")).netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]
                if domain in _REPUTABLE_DOMAINS or name_slug in domain:
                    reputable_count += 1
            except Exception:
                pass
        source_quality_score = reputable_count / len(results)

        return (
            0.3 * result_count_score
            + 0.3 * avg_relevance
            + 0.2 * name_match_score
            + 0.2 * source_quality_score
        )

    def _verify_company_exists(self, company_name: str) -> dict[str, Any]:
        """Verify a private company exists via Tavily web search.

        Returns a dict with verification_status, confidence_score,
        and an optional verification_warning.
        """
        client = self._get_tavily_client()
        if client is None:
            return {
                "verification_status": "SEARCH_FAILED",
                "confidence_score": None,
                "verification_warning": (
                    "Could not verify company existence: "
                    "TAVILY_API_KEY not configured."
                ),
            }

        try:
            response = client.search(
                query=f'"{company_name}" company',
                search_depth="basic",
                max_results=5,
                include_answer=False,
            )
            results = response.get("results", [])
            score = self._compute_confidence(company_name, results)

            if score >= self._verification_threshold:
                return {
                    "verification_status": "VERIFIED",
                    "confidence_score": round(score, 2),
                    "verification_warning": None,
                }
            else:
                return {
                    "verification_status": "UNVERIFIED",
                    "confidence_score": round(score, 2),
                    "verification_warning": (
                        f"LOW CONFIDENCE: Could not verify '{company_name}' "
                        f"as a real company (confidence: {score:.2f}/1.00). "
                        f"Web search returned insufficient evidence of this "
                        f"company's existence. Results may be unreliable or "
                        f"hallucinated."
                    ),
                }
        except Exception as exc:
            print(
                f"[company-verification] Tavily search failed for "
                f"'{company_name}': {exc}",
                file=sys.stderr,
                flush=True,
            )
            return {
                "verification_status": "SEARCH_FAILED",
                "confidence_score": None,
                "verification_warning": (
                    f"Verification search failed for '{company_name}': {exc}. "
                    f"Could not confirm company existence."
                ),
            }

    # ------------------------------------------------------------------
    # Company name extraction helpers
    # ------------------------------------------------------------------

    def _extract_company_names(
        self,
        results: list[dict],
        answer_text: str | None,
        max_names: int,
    ) -> list[str]:
        """Extract likely company names from Tavily search results.

        Parses the AI-generated answer text (most structured) and result
        titles to find capitalized phrases that look like company names.
        Deduplicates and filters out generic terms.
        """
        candidates: dict[str, int] = {}  # lowercase -> score
        display: dict[str, str] = {}  # lowercase -> original casing

        sources: list[tuple[str, int]] = []
        if answer_text:
            sources.append((answer_text, 2))
        for r in results:
            sources.append((r.get("title", ""), 1))

        for text, weight in sources:
            # Find capitalized phrases (1-4 words starting with uppercase).
            # Allow dots only when followed by letters (for names like Pony.ai).
            for match in re.finditer(
                r"\b([A-Z][a-zA-Z&'-]*(?:\.[a-zA-Z]+)*"
                r"(?:\s+[A-Z][a-zA-Z&'-]*(?:\.[a-zA-Z]+)*){0,3})\b",
                text,
            ):
                name = match.group(1).strip()
                if len(name) < 2:
                    continue
                # Strip trailing stop words from multi-word matches
                words = name.split()
                while len(words) > 1 and words[-1].lower() in _DISCOVERY_STOP_WORDS:
                    words.pop()
                name = " ".join(words)
                # Skip if every remaining word is a stop word
                if all(w.lower() in _DISCOVERY_STOP_WORDS for w in words):
                    continue
                key = name.lower()
                display.setdefault(key, name)
                candidates[key] = candidates.get(key, 0) + weight

        ranked = sorted(candidates, key=lambda k: candidates[k], reverse=True)
        return [display[k] for k in ranked[:max_names]]

    # ------------------------------------------------------------------
    # Main tool methods
    # ------------------------------------------------------------------

    def validate_companies(self, identifiers: str) -> str:
        """Classify a comma-separated list of company identifiers.

        Each identifier can be a stock ticker (e.g., "AAPL") or a company
        name (e.g., "Anthropic"). The tool checks YFinance first; if the
        identifier is not found, it is classified as a private company
        and verified via web search.

        Args:
            identifiers: Comma-separated tickers or company names
                         (e.g., "NVDA,Anthropic,AAPL,OpenAI")

        Returns:
            JSON with public_companies, private_companies, and details.
        """
        id_list = [t.strip() for t in identifiers.split(",") if t.strip()]

        if not id_list:
            return json.dumps(
                {
                    "error": (
                        "No company identifiers provided. Please provide "
                        "comma-separated tickers or company names "
                        "(e.g. 'AAPL,Anthropic,NVDA')."
                    ),
                    "public_companies": [],
                    "private_companies": [],
                }
            )

        public: list[dict[str, str]] = []
        private: list[dict[str, Any]] = []

        for identifier in id_list:
            resolved = self._resolve_identifier(identifier)
            if resolved:
                public.append(resolved)
            else:
                entry: dict[str, Any] = {
                    "company_name": identifier,
                    "company_type": "PRIVATE",
                    "reason": (
                        f"'{identifier}' not found on Yahoo Finance. "
                        f"Treating as private company."
                    ),
                }

                # Verify existence via web search
                verification = self._verify_company_exists(identifier)
                entry.update(verification)

                if verification["verification_status"] == "VERIFIED":
                    entry["reason"] = (
                        f"'{identifier}' not found on Yahoo Finance. "
                        f"Verified as a real company via web search. "
                        f"Treating as private company."
                    )

                private.append(entry)

        unverified = [
            p
            for p in private
            if p.get("verification_status") == "UNVERIFIED"
        ]

        result: dict[str, Any] = {
            "public_companies": public,
            "private_companies": private,
            "summary": {
                "total": len(id_list),
                "public_count": len(public),
                "private_count": len(private),
                "unverified_count": len(unverified),
            },
        }

        if unverified:
            result["warnings"] = [
                f"UNVERIFIED COMPANY: '{u['company_name']}' could not be "
                f"verified as a real company "
                f"(confidence: {u.get('confidence_score', 'N/A')}). "
                f"Proceed with extreme caution - data may be hallucinated."
                for u in unverified
            ]

        if private:
            names = ", ".join(p["company_name"] for p in private)
            result["note"] = (
                f"The following are classified as private companies: {names}. "
                "Use web search (Tavily) instead of YFinance for data gathering."
            )

        return json.dumps(result, indent=2)

    def discover_companies(
        self, sector: str, count: str, company_type: str
    ) -> str:
        """Discover companies in a sector or niche via web search.

        Searches for companies matching the given sector/niche and validates
        them. Use this when the user asks to FIND or DISCOVER companies
        rather than providing specific company names.

        Args:
            sector: The sector, niche, or industry to search
                    (e.g., "autonomous driving", "synthetic biology")
            count: Number of companies to discover (e.g., "3")
            company_type: "PUBLIC" for publicly traded companies,
                          "PRIVATE" for startups/private companies

        Returns:
            JSON with discovered companies in the same format as
            validate_companies, plus discovery_query metadata.
        """
        # Parse and clamp count
        try:
            n = min(int(count), MAX_DISCOVERY_COUNT)
            if n < 1:
                n = 1
        except (ValueError, TypeError):
            return json.dumps(
                {
                    "error": (
                        f"Invalid count '{count}'. "
                        f"Provide a positive integer (e.g., '3')."
                    ),
                    "public_companies": [],
                    "private_companies": [],
                }
            )

        ct = company_type.strip().upper()
        if ct not in ("PUBLIC", "PRIVATE"):
            return json.dumps(
                {
                    "error": (
                        f"Invalid company_type '{company_type}'. "
                        f"Must be PUBLIC or PRIVATE."
                    ),
                    "public_companies": [],
                    "private_companies": [],
                }
            )

        client = self._get_tavily_client()
        if client is None:
            return json.dumps(
                {
                    "error": (
                        "Cannot discover companies: "
                        "TAVILY_API_KEY not configured."
                    ),
                    "public_companies": [],
                    "private_companies": [],
                }
            )

        # Build search query biased toward active, thriving companies
        if ct == "PRIVATE":
            query = f"best {sector} startups 2025 2024 funding raised active"
        else:
            query = f"top {sector} stocks best performing companies 2025 2024"

        try:
            response = client.search(
                query=query,
                search_depth="basic",
                max_results=10,
                include_answer=True,
            )
        except Exception as exc:
            print(
                f"[company-discovery] Tavily search failed for "
                f"'{sector}': {exc}",
                file=sys.stderr,
                flush=True,
            )
            return json.dumps(
                {
                    "error": f"Discovery search failed for '{sector}': {exc}",
                    "public_companies": [],
                    "private_companies": [],
                }
            )

        results = response.get("results", [])
        answer_text = response.get("answer")

        # Extract candidate names (request extra for filtering)
        candidates = self._extract_company_names(results, answer_text, n * 3)

        if not candidates:
            return json.dumps(
                {
                    "error": (
                        f"No companies found for sector '{sector}'. "
                        f"Try a different or broader search term."
                    ),
                    "public_companies": [],
                    "private_companies": [],
                    "discovery_query": {
                        "sector": sector,
                        "requested_count": n,
                        "company_type_filter": ct,
                    },
                }
            )

        # Validate each candidate
        public: list[dict[str, str]] = []
        private: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        seen_tickers: set[str] = set()

        for name in candidates:
            if len(public) + len(private) >= n:
                break

            key = name.lower()
            if key in seen_names:
                continue
            seen_names.add(key)

            resolved = self._resolve_identifier(name)

            if ct == "PUBLIC":
                if resolved:
                    ticker_key = resolved["ticker"].lower()
                    if ticker_key not in seen_tickers:
                        seen_tickers.add(ticker_key)
                        public.append(resolved)
            else:  # PRIVATE
                if resolved:
                    # Actually a public company — skip
                    continue
                verification = self._verify_company_exists(name)
                if verification["verification_status"] == "VERIFIED":
                    entry: dict[str, Any] = {
                        "company_name": name,
                        "company_type": "PRIVATE",
                        "reason": (
                            f"Discovered '{name}' in '{sector}' sector. "
                            f"Verified as a real company via web search."
                        ),
                    }
                    entry.update(verification)
                    private.append(entry)

        total = len(public) + len(private)

        result: dict[str, Any] = {
            "discovery_query": {
                "sector": sector,
                "requested_count": n,
                "company_type_filter": ct,
            },
            "public_companies": public,
            "private_companies": private,
            "summary": {
                "total": total,
                "public_count": len(public),
                "private_count": len(private),
                "discovery_note": (
                    f"Discovered {total} companies in "
                    f"'{sector}' sector via web search."
                ),
            },
        }

        if total < n:
            result["summary"]["discovery_note"] = (
                f"Only found {total} of {n} requested companies "
                f"in '{sector}' sector."
            )

        if private:
            names = ", ".join(p["company_name"] for p in private)
            result["note"] = (
                f"The following are classified as private companies: "
                f"{names}. "
                "Use web search (Tavily) instead of YFinance for "
                "data gathering."
            )

        return json.dumps(result, indent=2)

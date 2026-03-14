from pydantic import BaseModel, Field, field_validator


# --- Allowed values for constrained enum-like fields ---
SEVERITY_VALUES = {"HIGH", "MEDIUM", "LOW"}
RECOMMENDATION_VALUES = {"BUY", "HOLD", "SELL", "INVEST", "PASS", "WATCH"}
CONFIDENCE_VALUES = {"HIGH", "MEDIUM", "LOW"}
RISK_CATEGORY_VALUES = {"MARKET", "COMPANY_SPECIFIC", "SECTOR", "MACRO", "REGULATORY"}
COMPANY_TYPE_VALUES = {"PUBLIC", "PRIVATE"}
VERIFICATION_STATUS_VALUES = {"VERIFIED", "UNVERIFIED", "SEARCH_FAILED", "NOT_APPLICABLE"}

# Common LLM variations of category names
_CATEGORY_ALIASES: dict[str, str] = {
    "COMPANY-SPECIFIC": "COMPANY_SPECIFIC",
    "COMPANY SPECIFIC": "COMPANY_SPECIFIC",
    "COMPANYSPECIFIC": "COMPANY_SPECIFIC",
}


def _normalize_enum(
    value: str, allowed: set[str], aliases: dict[str, str] | None = None
) -> str:
    """Normalize a string to match allowed enum values.

    Auto-corrects casing and common formatting variations before rejecting.
    """
    if not isinstance(value, str):
        raise ValueError(f"Expected string, got {type(value)}")

    upper = value.strip().upper()

    # Direct match after uppercasing
    if upper in allowed:
        return upper

    # Try alias lookup
    if aliases and upper in aliases:
        return aliases[upper]

    # Try replacing hyphens/spaces with underscores
    normalized = upper.replace("-", "_").replace(" ", "_")
    if normalized in allowed:
        return normalized

    raise ValueError(f"'{value}' is not one of {sorted(allowed)}")


class CompanyResearch(BaseModel):
    """Research data for a single company, gathered by the Research Agent."""

    company_name: str = Field(..., description="Full company name")
    company_type: str = Field(
        "PUBLIC",
        description="PUBLIC for publicly traded companies, PRIVATE for private companies",
    )
    ticker: str | None = Field(
        None, description="Stock ticker symbol (None for private companies)"
    )
    sector: str = Field(..., description="Industry sector")

    # Public company fields (populated from YFinance)
    current_price: float | None = Field(None, description="Current stock price in USD")
    market_cap: str | None = Field(None, description="Market capitalization")
    pe_ratio: float | None = Field(None, description="Price-to-earnings ratio")
    revenue_growth: str | None = Field(None, description="Year-over-year revenue growth")
    analyst_consensus: str | None = Field(None, description="Analyst consensus rating")

    # Private company fields (populated from web search)
    latest_funding_round: str | None = Field(
        None, description="Latest funding round (e.g., Series D, $2B)"
    )
    total_funding: str | None = Field(None, description="Total funding raised")
    latest_valuation: str | None = Field(None, description="Latest known valuation")
    key_investors: list[str] = Field(
        default_factory=list, description="Key investors and backers"
    )
    estimated_revenue: str | None = Field(
        None, description="Estimated annual revenue or ARR if available"
    )
    funding_stage: str | None = Field(
        None, description="Current funding stage (Seed, Series A, etc.)"
    )

    # Verification fields (populated by CompanyValidationTool for private companies)
    verification_status: str | None = Field(
        None,
        description=(
            "Verification status for private companies: "
            "VERIFIED, UNVERIFIED, SEARCH_FAILED, or NOT_APPLICABLE. "
            "None if verification was not performed."
        ),
    )
    confidence_score: float | None = Field(
        None,
        description="Confidence score (0.0-1.0) that this company actually exists.",
    )

    # Shared fields
    recent_news: list[str] = Field(
        default_factory=list,
        description="3-5 recent news headlines (positive and negative)",
    )
    key_products: list[str] = Field(
        default_factory=list, description="Main products or services"
    )
    competitive_position: str | None = Field(
        None, description="Brief competitive position summary"
    )
    negative_news: list[str] = Field(
        default_factory=list,
        description="Negative news: lawsuits, controversies, regulatory issues",
    )

    @field_validator("company_type", mode="before")
    @classmethod
    def normalize_company_type(cls, v: str) -> str:
        return _normalize_enum(v, COMPANY_TYPE_VALUES)

    @field_validator("verification_status", mode="before")
    @classmethod
    def normalize_verification_status(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _normalize_enum(v, VERIFICATION_STATUS_VALUES)


class CompanyResearchSet(BaseModel):
    """Research data for all companies being evaluated."""

    sector: str = Field(..., description="The sector being analyzed")
    companies: list[CompanyResearch] = Field(
        ..., description="Research data for each company"
    )
    research_date: str = Field(..., description="Date research was conducted")


class CompanyAnalysis(BaseModel):
    """Analysis of a single company by the Analyst Agent."""

    company_name: str = Field(..., description="Company name or ticker symbol")
    company_type: str = Field("PUBLIC", description="PUBLIC or PRIVATE")
    strengths: list[str] = Field(..., description="2-4 key strengths")
    weaknesses: list[str] = Field(..., description="2-4 key weaknesses")
    valuation_assessment: str = Field(
        ...,
        description="For public: overvalued/fairly valued/undervalued. "
        "For private: assessment of latest valuation relative to fundamentals.",
    )
    growth_outlook: str = Field(
        ..., description="Growth outlook for next 12-18 months"
    )

    @field_validator("company_type", mode="before")
    @classmethod
    def normalize_company_type(cls, v: str) -> str:
        return _normalize_enum(v, COMPANY_TYPE_VALUES)


class FinancialAnalysis(BaseModel):
    """Comparative financial analysis across all companies."""

    sector: str = Field(..., description="Sector analyzed")
    company_analyses: list[CompanyAnalysis] = Field(
        ..., description="Analysis per company"
    )
    comparative_summary: str = Field(
        ..., description="How companies compare to each other"
    )
    top_pick: str = Field(
        ..., description="Name or ticker of the top pick with brief justification"
    )


class RiskFactor(BaseModel):
    """A single identified risk."""

    category: str = Field(
        ...,
        description="Risk category: MARKET, COMPANY_SPECIFIC, SECTOR, MACRO, or REGULATORY",
    )
    description: str = Field(..., description="Description of the risk")
    severity: str = Field(..., description="HIGH, MEDIUM, or LOW")
    affected_companies: list[str] = Field(
        ..., description="Which companies (by name or ticker) are affected"
    )

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: str) -> str:
        return _normalize_enum(v, RISK_CATEGORY_VALUES, _CATEGORY_ALIASES)

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v: str) -> str:
        return _normalize_enum(v, SEVERITY_VALUES)


class RiskAssessment(BaseModel):
    """Risk assessment produced by the Critic/Risk Agent."""

    risks: list[RiskFactor] = Field(..., description="Identified risk factors")
    assumptions_challenged: list[str] = Field(
        ..., description="Assumptions in the analysis that may not hold"
    )
    data_gaps: list[str] = Field(
        ...,
        description="Missing data that could change the conclusion",
    )
    contrarian_view: str = Field(
        ..., description="A contrarian argument against the top pick"
    )
    overall_confidence: str = Field(
        ...,
        description="HIGH, MEDIUM, or LOW confidence in the analysis",
    )

    @field_validator("overall_confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, v: str) -> str:
        return _normalize_enum(v, CONFIDENCE_VALUES)


class CompanyDecision(BaseModel):
    """Investment decision for a single company."""

    company_name: str = Field(..., description="Company name or ticker symbol")
    company_type: str = Field("PUBLIC", description="PUBLIC or PRIVATE")
    recommendation: str = Field(
        ...,
        description="For public companies: BUY, HOLD, or SELL. "
        "For private companies: INVEST, PASS, or WATCH.",
    )
    confidence: str = Field(
        ...,
        description="Confidence in the recommendation: HIGH, MEDIUM, or LOW",
    )
    reasoning: str = Field(
        ...,
        description="Brief reasoning for the recommendation, weighing analysis against risks",
    )

    @field_validator("company_type", mode="before")
    @classmethod
    def normalize_company_type(cls, v: str) -> str:
        return _normalize_enum(v, COMPANY_TYPE_VALUES)

    @field_validator("recommendation", mode="before")
    @classmethod
    def normalize_recommendation(cls, v: str) -> str:
        return _normalize_enum(v, RECOMMENDATION_VALUES)

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, v: str) -> str:
        return _normalize_enum(v, CONFIDENCE_VALUES)


class InvestmentDecision(BaseModel):
    """Structured investment decision produced by the Decision Agent."""

    sector: str = Field(..., description="Sector analyzed")
    company_decisions: list[CompanyDecision] = Field(
        ..., description="Investment decision for each company"
    )
    top_pick: str = Field(
        ..., description="Name or ticker of the overall top pick"
    )
    top_pick_justification: str = Field(
        ...,
        description="Full justification for the top pick, incorporating both "
        "the analyst's case and the critic's concerns",
    )
    investment_thesis: str = Field(
        ...,
        description="2-3 sentence summary of the overall investment thesis for the sector",
    )
    key_conditions: list[str] = Field(
        ...,
        description="Conditions or catalysts that could change these recommendations",
    )

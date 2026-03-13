from pydantic import BaseModel, Field


class CompanyResearch(BaseModel):
    """Research data for a single company, gathered by the Research Agent."""

    ticker: str = Field(..., description="Stock ticker symbol")
    company_name: str = Field(..., description="Full company name")
    sector: str = Field(..., description="Industry sector")
    current_price: float | None = Field(None, description="Current stock price in USD")
    market_cap: str | None = Field(None, description="Market capitalization")
    pe_ratio: float | None = Field(None, description="Price-to-earnings ratio")
    revenue_growth: str | None = Field(None, description="Year-over-year revenue growth")
    analyst_consensus: str | None = Field(None, description="Analyst consensus rating")
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


class CompanyResearchSet(BaseModel):
    """Research data for all companies being evaluated."""

    sector: str = Field(..., description="The sector being analyzed")
    companies: list[CompanyResearch] = Field(
        ..., description="Research data for each company"
    )
    research_date: str = Field(..., description="Date research was conducted")


class CompanyAnalysis(BaseModel):
    """Analysis of a single company by the Analyst Agent."""

    ticker: str = Field(..., description="Stock ticker symbol")
    strengths: list[str] = Field(..., description="2-4 key strengths")
    weaknesses: list[str] = Field(..., description="2-4 key weaknesses")
    valuation_assessment: str = Field(
        ...,
        description="Overvalued, fairly valued, or undervalued with reasoning",
    )
    growth_outlook: str = Field(
        ..., description="Growth outlook for next 12-18 months"
    )


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
        ..., description="Ticker of the top pick with brief justification"
    )


class RiskFactor(BaseModel):
    """A single identified risk."""

    category: str = Field(
        ...,
        description="Risk category: market, company-specific, sector, or macro",
    )
    description: str = Field(..., description="Description of the risk")
    severity: str = Field(..., description="high, medium, or low")
    affected_tickers: list[str] = Field(
        ..., description="Which tickers are affected"
    )


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
        description="high, medium, or low confidence in the analysis",
    )

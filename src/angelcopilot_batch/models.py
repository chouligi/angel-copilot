from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class DealInput:
    deal_id: str
    path: Path
    supported_files: list[Path]
    latest_modified_at: datetime


@dataclass
class EvidenceBlock:
    source_path: Path
    text: str


@dataclass
class EvidenceBundle:
    evidence_blocks: list[EvidenceBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class InvestorProfile:
    region: str = ""
    currency: str = ""
    inferred_risk_level: str = ""
    ticket_typical: int = 0
    sectors_themes: list[str] = field(default_factory=list)
    geo_focus: list[str] = field(default_factory=list)


@dataclass
class AssessmentResult:
    deal_id: str
    company_name: str
    category_scores: dict[str, float]
    risk_flags: list[str]
    sectors: list[str]
    geographies: list[str]
    rationale: str
    citations: list[dict[str, object] | str] = field(default_factory=list)
    category_rationales: dict[str, str] = field(default_factory=dict)
    web_sweep_findings: list[dict[str, object] | str] = field(default_factory=list)
    web_sweep_sources: list[dict[str, object] | str] = field(default_factory=list)
    milestones_to_monitor: list[str] = field(default_factory=list)
    key_unknowns: list[str] = field(default_factory=list)
    return_scenarios: list[dict[str, object]] = field(default_factory=list)
    assessment_limitations: str = ""
    assessment_process: dict[str, object] = field(default_factory=dict)
    evidence_sources: list[str] = field(default_factory=list)
    extraction_warnings: list[str] = field(default_factory=list)
    hypothetical_investment: float = 10000.0
    investment_currency: str = "USD"
    investment_basis: str = "default_10000"
    dilution_assumption: str = "Excluded by default (gross multiples, pre-dilution assumption)."
    verdict_one_liner: str = ""
    why_not_invest_now: list[str] = field(default_factory=list)
    what_would_upgrade_to_invest: list[str] = field(default_factory=list)
    weighted_score: float = 0.0
    verdict: str = ""
    attention_flag: bool = False
    attention_reason: str = ""
    profile_fit: float = 0.0

    def to_json_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class BatchOutputPaths:
    markdown_path: Path
    csv_path: Path
    json_path: Path
    html_path: Path | None = None
    pdf_path: Path | None = None

"""Datamodeller: SignalItem (ett raadatum fra en kilde) og Case (en klynge)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SignalItem:
    """Ett normalisert signal fra en kilde (nyhet, reddit-post, trend)."""

    source: str          # f.eks. "Stavanger Aftenblad" / "r/stavanger"
    source_type: str     # "news" | "reddit" | "trends"
    title: str
    url: str
    published: datetime  # UTC
    summary: str = ""
    geo: str = "nasjonal"          # "lokal" (Stavanger/Rogaland) | "nasjonal"
    outlet_local: bool = False     # kilden er en lokalavis (svak lokal-indikasjon)
    score: int = 0                 # ekstra signalstyrke (f.eks. reddit-oppstemmer)
    topics: list[str] = field(default_factory=list)  # settes av scoring

    @property
    def text(self) -> str:
        return f"{self.title} {self.summary}".strip()


@dataclass
class Case:
    """Et saksforslag ("lead"). Kan vaere datadrevet (SSB) eller grasrot (Trends/Reddit).

    Kjerneidé v2: leadet skal helst vaere ORIGINALT - noe ingen medier har skrevet
    ennaa. Derfor baerer hvert lead en dekningsstatus (green/yellow/red).
    """

    key: str                       # nokkel/tema som binder saken
    title: str                     # kort tittel til dashboardet
    score: float                   # rangeringsscore (hoyere = varmere)
    geo: str                       # "lokal" | "nasjonal"
    topics: list[str]              # tema-tags (18-34)
    angle: str                     # foreslaatt vinkling til journalisten
    why: str                       # kort begrunnelse ("hvorfor na")
    signals: list[SignalItem]      # kildene bak saken (tom for rene datafunn)
    created_at: datetime

    # v2-felter (datadrevne leads + originalitet)
    kind: str = "grasrot"          # "data" (SSB) | "grasrot" (Trends/Reddit) | "schibsted"
    target_relevance: str = ""     # relevans for 20-39: "høy" | "middels" | "lav"
    finding: str = ""              # selve tallet/funnet i klartekst (fullsetning)
    metric_value: str = ""         # kort tall til "Funn"-boksen, f.eks. "−3,4 %"
    metric_period: str = ""        # periode til "Funn"-boksen, f.eks. "2025–2026"
    data_source: str = ""          # f.eks. "SSB (befolkning, 07459)"
    data_url: str = ""             # lenke til datakilden
    coverage_status: str = "unknown"   # "green" | "yellow" | "red" | "unknown"
    coverage_examples: list[dict] = field(default_factory=list)  # {title,source,date}
    coverage_query: str = ""       # sokestreng brukt i dekningssjekken

    # v3-felter (redaksjonell KI-arbeidsflyt)
    ai_mode: str = "none"          # "llm" | "mal" | "none"
    analyst_reason: str = ""       # analytikerens begrunnelse for at funnet er interessant
    editor: dict = field(default_factory=dict)   # {is_story, confidence, headline, angle, verdict, novelty}
    draft: dict = field(default_factory=dict)     # foerste vinkel (bakoverkompatibelt)
    angles: list[dict] = field(default_factory=list)  # TRE komplette pakker fra journalisten

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "score": round(self.score, 1),
            "geo": self.geo,
            "topics": self.topics,
            "angle": self.angle,
            "why": self.why,
            "kind": self.kind,
            "target_relevance": self.target_relevance,
            "finding": self.finding,
            "metric_value": self.metric_value,
            "metric_period": self.metric_period,
            "data_source": self.data_source,
            "data_url": self.data_url,
            "coverage_status": self.coverage_status,
            "coverage_examples": self.coverage_examples,
            "ai_mode": self.ai_mode,
            "analyst_reason": self.analyst_reason,
            "editor": self.editor,
            "draft": self.draft,
            "angles": self.angles,
            "sources": [
                {
                    "source": s.source,
                    "source_type": s.source_type,
                    "title": s.title,
                    "url": s.url,
                    "published": s.published.isoformat(),
                }
                for s in self.signals
            ],
        }

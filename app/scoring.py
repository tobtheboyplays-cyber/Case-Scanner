"""Scoring og case-klynging.

Gjor raa signaler om til rangerte "caser" (saksforslag). Bevisst enkelt og
gjennomsiktig: hvert steg er lett a forklare til en journalist.

Nokkelideer for a faa MENINGSFULLE caser:
- Geografi avgjores av INNHOLD (nevnes et Rogaland-sted?), ikke av hvilken avis.
- Vi klynger saker rundt NAVN/ENTITETER (egennavn i tittelen) og TEMA (18-34),
  ikke rundt tilfeldige felles ord som "store" eller "fredag".

Steg:
1. Tag hvert signal med geografi (lokal/nasjonal) og tema (18-34).
2. Finn kandidat-nokler per signal: entiteter (egennavn) + tema.
3. Klyng signaler som deler en nokkel -> en Case.
4. Ranger casene (kildebredde, ferskhet, lokal- og demografi-boost, trend-boost).
5. Lag en foreslaatt vinkling + kort "hvorfor naa".
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import timedelta

from app.collectors.base import now_utc
from app.config import (
    DEMOGRAPHIC_TOPICS,
    ENTITY_STOPWORDS,
    STAVANGER_TERMS,
    STAVANGER_TERMS_EXACT,
    STOPWORDS,
)
from app.models import Case, SignalItem

_WORD_RE = re.compile(r"[a-zæøåA-ZÆØÅ0-9\-]+")


def _normalize(text: str) -> str:
    """Sma bokstaver + bytt ae/oe/aa slik at ordlistene matcher robust."""
    t = text.lower()
    return t.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")


def tokenize(text: str) -> list[str]:
    """Nokkelord: ord >= 4 tegn som ikke er stoppord."""
    out = []
    for w in _WORD_RE.findall(text.lower()):
        norm = _normalize(w)
        if len(w) >= 4 and norm not in STOPWORDS and w not in STOPWORDS:
            out.append(norm)
    return out


def is_local_text(text: str) -> bool:
    """True hvis teksten nevner et entydig Rogaland-sted."""
    norm = _normalize(text)
    for term in STAVANGER_TERMS:
        t = _normalize(term)
        if re.search(rf"\b{re.escape(t)}\b", norm):
            return True
    for term in STAVANGER_TERMS_EXACT:
        if re.search(rf"\b{re.escape(term)}\b", norm):
            return True
    return False


def detect_topics(text: str) -> list[str]:
    """Tema-tags for 18-34. Prefiks-match handterer sammensatte ord
    (f.eks. «boligkrise» -> «bolig og leie», «leiemarkedet» -> «leie»)."""
    tokens = tokenize(text)
    norm_tokens = set(tokens)
    topics: list[str] = []
    for topic, keywords in DEMOGRAPHIC_TOPICS.items():
        hit = False
        for kw in keywords:
            k = _normalize(kw)
            if " " in k:  # flerords-nokkel: sjekk i hele teksten
                if k in _normalize(text):
                    hit = True
                    break
                continue
            for tok in norm_tokens:
                if tok == k or (len(k) >= 4 and tok.startswith(k)):
                    hit = True
                    break
            if hit:
                break
        if hit:
            topics.append(topic)
    return topics


def extract_entities(title: str) -> set[str]:
    """Egennavn i tittelen (store forbokstaver, ikke forste ord).

    Returnerer normaliserte former som brukes som klynge-nokler.
    """
    tokens = title.split()
    ents: set[str] = set()
    for i, raw in enumerate(tokens):
        clean = raw.strip(".,:;!?«»\"'()–—-")
        if i == 0:  # forste ord er alltid stor forbokstav -> hopp over
            continue
        # Hopp over ord som star forst i en ny setning (etter . : – — ! ?),
        # de er stor-forbokstav pga. setningsstart, ikke fordi de er egennavn.
        prev = tokens[i - 1]
        if prev and (prev[-1] in ".:!?" or prev in {"–", "—", "-", ":"}):
            continue
        if len(clean) < 4 or not clean[0].isupper():
            continue
        norm = _normalize(clean)
        if norm in STOPWORDS or norm in ENTITY_STOPWORDS:
            continue
        # Slaa sammen bindestreks-navn til egennavn-delen:
        # "Ingebrigtsen-brotet" -> "ingebrigtsen" (matcher "Ingebrigtsen").
        if "-" in norm:
            lead = norm.split("-", 1)[0]
            if len(lead) >= 4 and lead not in STOPWORDS and lead not in ENTITY_STOPWORDS:
                ents.add(lead)
                continue
        ents.add(norm)
    return ents


def tag_signal(sig: SignalItem) -> None:
    """Sett geo (innholdsbasert) og tema-tags paa et signal (in-place)."""
    if is_local_text(sig.text):
        sig.geo = "lokal"
    sig.topics = detect_topics(sig.text)


def _recency_weight(sig: SignalItem) -> float:
    """1.0 for helt ferskt, faller mot ~0.2 over 3 dogn."""
    age_h = (now_utc() - sig.published).total_seconds() / 3600.0
    if age_h <= 24:
        return 1.0
    if age_h <= 48:
        return 0.7
    if age_h <= 72:
        return 0.4
    return 0.2


def build_cases(signals: list[SignalItem], *, limit: int = 25) -> list[Case]:
    """Klyng signaler til rangerte caser."""
    for sig in signals:
        tag_signal(sig)

    trend_terms = {_normalize(s.title) for s in signals if s.source_type == "trends"}

    # Kandidat-nokler per signal: entiteter + tema. Tema-nokler prefikses "tema:".
    key_signals: dict[str, list[SignalItem]] = defaultdict(list)
    key_is_entity: dict[str, bool] = {}
    for sig in signals:
        for ent in extract_entities(sig.title):
            key_signals[ent].append(sig)
            key_is_entity[ent] = True
        for topic in sig.topics:
            k = f"tema:{topic}"
            key_signals[k].append(sig)
            key_is_entity.setdefault(k, False)

    def distinct_sources(items: list[SignalItem]) -> int:
        return len({s.source for s in items})

    # Ranger nokler: bredest kildedekning foerst; ved likhet prioriter
    # spesifikke entiteter (egennavn) over brede tema-klynger.
    ranked = sorted(
        key_signals.items(),
        key=lambda kv: (distinct_sources(kv[1]), key_is_entity[kv[0]], len(kv[1])),
        reverse=True,
    )

    cases: list[Case] = []
    used: set[int] = set()

    for key, items in ranked:
        fresh = [s for s in items if id(s) not in used]
        if not fresh:
            continue
        n_sources = distinct_sources(fresh)
        has_local = any(s.geo == "lokal" for s in fresh)
        topics = sorted({t for s in fresh for t in s.topics})
        is_entity = key_is_entity[key]

        # Filter for a unngaa stoy:
        if is_entity:
            # Egennavn-case: krever korroborering fra >= 2 kilder.
            if n_sources < 2:
                continue
        else:
            # Tema-case: lokal + tematisk enkeltsak er OK; ellers krever
            # nasjonale tema-klynger bredde (>= 3 kilder).
            if n_sources < 2 and not (has_local and topics):
                continue
            if not has_local and n_sources < 3:
                continue

        display = _display_key(key, topics)
        score = _score_case(fresh, key, trend_terms)
        geo = "lokal" if has_local else "nasjonal"
        # For tema-caser er noekkelen selve temaet -> vis kun det (unngaa stoyete
        # union). For entitet-caser: vis de faa faktiske temaene (maks 3).
        display_topics = [display] if not is_entity else topics[:3]
        cases.append(
            Case(
                key=key,
                title=_case_title(fresh),
                score=score,
                geo=geo,
                topics=display_topics,
                angle=_suggest_angle(display, topics, geo, is_entity),
                why=_explain(fresh, n_sources, geo, trend_terms, key),
                signals=sorted(fresh, key=lambda s: s.published, reverse=True)[:6],
                created_at=now_utc(),
            )
        )
        for s in fresh:
            used.add(id(s))

    cases.sort(key=lambda c: c.score, reverse=True)
    return cases[:limit]


def _display_key(key: str, topics: list[str]) -> str:
    if key.startswith("tema:"):
        return key.split(":", 1)[1]
    return key


def _score_case(items: list[SignalItem], key: str, trend_terms: set[str]) -> float:
    n_sources = len({s.source for s in items})
    recency = max(_recency_weight(s) for s in items)
    local = any(s.geo == "lokal" for s in items)
    outlet_local = any(s.outlet_local for s in items)
    topical = any(s.topics for s in items)
    reddit_heat = sum(s.score for s in items if s.source_type == "reddit")
    on_trend = _normalize(key) in {_normalize(t) for t in trend_terms}

    score = 0.0
    score += n_sources * 3.0
    score += recency * 4.0
    score += 6.0 if local else 0.0            # innholdsbasert lokal = sterkt signal
    score += 1.5 if outlet_local else 0.0     # lokalavis-hint (svakt)
    score += 3.0 if topical else 0.0
    score += min(reddit_heat / 100.0, 5.0)
    score += 4.0 if on_trend else 0.0
    return score


def _case_title(items: list[SignalItem]) -> str:
    newest = max(items, key=lambda s: s.published)
    return newest.title[:140]


def _suggest_angle(display: str, topics: list[str], geo: str, is_entity: bool) -> str:
    sted = "Stavanger/Rogaland" if geo == "lokal" else "Norge"
    if is_entity:
        base = f"«{display}» går igjen i flere kilder nå."
    else:
        base = f"Temaet «{display}» er hett på tvers av kilder nå."
    if topics and geo == "lokal":
        return (
            f"{base} Lokal vinkling for unge (18-34) i {sted}: finn en case-person "
            f"som merker det, pluss en ekspertkilde."
        )
    if geo == "lokal":
        return f"{base} Ring en lokal kilde i {sted} og finn vinkelen for unge lesere."
    if topics:
        return (
            f"{base} Se etter den lokale {sted}-vinkelen og hva det betyr for unge her."
        )
    return f"{base} Vurder om det finnes en lokal {sted}-vinkel for unge lesere."


def _explain(
    items: list[SignalItem],
    n_sources: int,
    geo: str,
    trend_terms: set[str],
    key: str,
) -> str:
    parts = []
    if n_sources >= 2:
        parts.append(f"{n_sources} kilder omtaler det")
    if geo == "lokal":
        parts.append("nevner Stavanger/Rogaland")
    elif any(s.outlet_local for s in items):
        parts.append("plukket opp av lokalavis")
    if _normalize(key) in {_normalize(t) for t in trend_terms}:
        parts.append("stiger i Google-søk")
    reddit_heat = sum(s.score for s in items if s.source_type == "reddit")
    if reddit_heat > 50:
        parts.append(f"engasjement på Reddit ({reddit_heat} poeng)")
    fresh = min(items, key=lambda s: (now_utc() - s.published))
    age_h = int((now_utc() - fresh.published).total_seconds() / 3600)
    parts.append(f"ferskeste sak {age_h}t gammel")
    return "; ".join(parts).capitalize() + "."


def within_last(items: list[SignalItem], hours: int) -> list[SignalItem]:
    cutoff = now_utc() - timedelta(hours=hours)
    return [s for s in items if s.published >= cutoff]


COVERAGE_DELTA = {"green": 12.0, "yellow": 2.0, "red": -10.0, "unknown": 0.0}


def finalize_scores(cases: list[Case]) -> None:
    """Legg originalitet (dekningsstatus) paa toppen av basisscoren, in-place.

    Dette gjor at USKREVNE saker (gronn) rangeres hoyt og allerede dekkede
    (rod) faller ned - kjerneidéen i v2.
    """
    for c in cases:
        c.score += COVERAGE_DELTA.get(c.coverage_status, 0.0)


def topic_distribution(signals: list[SignalItem]) -> list[dict]:
    """Tell hvor mange signaler som treffer hvert tema (18-34), + lokal-andel.

    Brukes til prioriterings-/trenddiagrammet: hvilke temaer rører seg mest nå,
    og hvor mye av det er lokalt for Stavanger/Rogaland.
    """
    counts: dict[str, int] = defaultdict(int)
    local_counts: dict[str, int] = defaultdict(int)
    for s in signals:
        for t in s.topics:
            counts[t] += 1
            if s.geo == "lokal":
                local_counts[t] += 1
    dist = [
        {"name": t, "count": c, "local": local_counts[t]}
        for t, c in counts.items()
    ]
    dist.sort(key=lambda d: d["count"], reverse=True)
    return dist

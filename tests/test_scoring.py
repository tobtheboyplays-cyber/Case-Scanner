"""Tester for scoring/klynging - kjorer uten nettverk (syntetiske signaler)."""

from __future__ import annotations

from datetime import timezone

from app.collectors.base import now_utc
from app.models import SignalItem
from app.scoring import build_cases, tag_signal, tokenize


def _sig(source, title, geo="nasjonal", stype="news", score=0):
    return SignalItem(
        source=source, source_type=stype, title=title, url="http://x",
        published=now_utc(), geo=geo, score=score,
    )


def test_tokenize_removes_stopwords_and_short_words():
    toks = tokenize("Det er en stor boligkrise i Stavanger")
    assert "boligkrise" in toks
    assert "stavanger" in toks
    assert "er" not in toks
    assert "en" not in toks


def test_tag_signal_detects_local_and_topic():
    sig = _sig("VG", "Ny boligkrise rammer studenter i Stavanger")
    tag_signal(sig)
    assert sig.geo == "lokal"          # Stavanger nevnt
    assert "studentliv" in sig.topics or "bolig og leie" in sig.topics


def test_build_cases_clusters_by_theme():
    signals = [
        _sig("VG", "Boligkrise for unge i Norge"),
        _sig("NRK", "Ekspert om boligkrise og renter"),
        _sig("Aftenbladet", "Boligkrise rammer Stavanger"),
    ]
    cases = build_cases(signals)
    assert cases, "forventet minst en case"
    # "boligkrise" -> tema «bolig og leie» deles av 3 kilder -> tema-case
    assert any("bolig" in c.key for c in cases)
    # Stavanger nevnes i innholdet -> klyngen skal bli lokal
    assert any(c.geo == "lokal" for c in cases)


def test_build_cases_clusters_by_entity():
    signals = [
        _sig("VG", "Dramatisk avslutning for Ingebrigtsen i mesterskapet"),
        _sig("NRK", "Slik reagerer Ingebrigtsen etter løpet"),
    ]
    cases = build_cases(signals)
    assert any(c.key == "ingebrigtsen" for c in cases), "egennavn skal bli en case"


def test_local_topical_single_source_still_surfaces():
    # En enkelt lokal + tematisk sak skal kunne bli case selv uten flere kilder.
    signals = [_sig("Aftenbladet", "Leiemarkedet i Stavanger sprenger for studenter", geo="lokal")]
    cases = build_cases(signals)
    assert cases, "lokal + tematisk enkeltsak skal overleve filteret"


def test_weak_national_singleton_is_filtered():
    signals = [_sig("VG", "Tilfeldig overskrift uten tema")]
    cases = build_cases(signals)
    assert cases == [], "svak nasjonal enkeltsak skal filtreres bort"

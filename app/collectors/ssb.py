"""SSB-statistikkmotor - primaerkilde for ORIGINALE, datadrevne leads.

Henter tall fra SSB sitt apne API (gratis, ingen nokkel), oppdager notable
endringer og gjor dem om til saksforslag. Dette er "originalt" fordi det er
raadata journalisten selv vinkler - ikke en ferdig artikkel fra en annen avis.

Fail-soft: en tabell som er nede stopper ikke resten.
"""

from __future__ import annotations

import httpx

from app.collectors.base import now_utc
from app.config import (
    ENABLE_SSB,
    SSB_API,
    SSB_PROBES,
    SSB_REGIONS,
    USER_AGENT,
    demografi_for,
)
from app.models import Case


def _build_query(spec: dict) -> dict:
    query = []
    for code, sel in spec.items():
        if isinstance(sel, dict) and "top" in sel:
            query.append(
                {"code": code,
                 "selection": {"filter": "top", "values": [str(sel["top"])]}}
            )
        else:
            query.append({"code": code, "selection": {"filter": "item", "values": list(sel)}})
    return {"query": query, "response": {"format": "json-stat2"}}


def _fetch(table: str, spec: dict) -> dict:
    url = f"{SSB_API}/{table}"
    resp = httpx.post(url, json=_build_query(spec), headers={"User-Agent": USER_AGENT}, timeout=25)
    resp.raise_for_status()
    return resp.json()


def _series_by_region(data: dict) -> tuple[dict[str, list[tuple[str, float]]], list[str]]:
    """Parse json-stat2 -> {region_code: [(aar, sum_over_alder), ...]} sortert paa tid.

    Summerer over alle Alder-koder (og evt. andre dims) slik at hvert (Region, Tid)
    faar én verdi. Returnerer ogsaa aarsliste.
    """
    dims = data["id"]
    sizes = data["size"]
    values = data["value"]
    cats = {d: data["dimension"][d]["category"] for d in dims}

    # Indeksrekkefolge for hver dimensjon (json-stat "index")
    order = {d: sorted(cats[d]["index"], key=lambda k: cats[d]["index"][k]) for d in dims}
    tid_codes = order["Tid"]
    reg_codes = order["Region"]

    # Strides for row-major flat array
    strides = [1] * len(dims)
    for i in range(len(dims) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    dpos = {d: i for i, d in enumerate(dims)}

    def flat_index(coord: dict[str, int]) -> int:
        return sum(coord[d] * strides[dpos[d]] for d in dims)

    series: dict[str, list[tuple[str, float]]] = {}
    for rc in reg_codes:
        pts = []
        for tc in tid_codes:
            total = 0.0
            # summer over alle kombinasjoner av ovrige dims (typisk bare Alder)
            other = [d for d in dims if d not in ("Region", "Tid")]
            for combo in _iter_combos(order, other):
                coord = {"Region": order["Region"].index(rc), "Tid": tid_codes.index(tc)}
                for d, code in combo.items():
                    coord[d] = order[d].index(code)
                v = values[flat_index(coord)]
                if v is not None:
                    total += v
            pts.append((tc, total))
        series[rc] = pts
    return series, tid_codes


def _iter_combos(order: dict, dims: list[str]):
    if not dims:
        yield {}
        return
    head, rest = dims[0], dims[1:]
    for code in order[head]:
        for tail in _iter_combos(order, rest):
            yield {head: code, **tail}


def _pct(new: float, old: float) -> float:
    return 0.0 if old == 0 else (new - old) / old * 100.0


def _make_case(probe: dict, series: dict, tids: list[str]) -> Case | None:
    """Recipe 'sum_age_trend': sammenlign siste vs forrige aar for Stavanger,
    med Rogaland og Hele landet som kontekst. Lag ett lead."""
    local = series.get("1103")
    if not local or len(local) < 2:
        return None

    latest_t, latest_v = local[-1]
    prev_t, prev_v = local[-2]
    change = latest_v - prev_v
    pct = _pct(latest_v, prev_v)

    # Kontekst: nasjonal endring samme periode
    nat = series.get("0")
    nat_pct = _pct(nat[-1][1], nat[-2][1]) if nat and len(nat) >= 2 else None
    rog = series.get("11")
    rog_pct = _pct(rog[-1][1], rog[-2][1]) if rog and len(rog) >= 2 else None

    label = probe["label"]
    arrow = "opp" if change > 0 else "ned"

    def _n(x: float) -> str:
        return f"{int(round(x)):,}".replace(",", " ")  # 1 855 (tynt mellomrom)

    finding = (
        f"{label} i Stavanger: {_n(latest_v)} i {latest_t} "
        f"({'+' if change >= 0 else '−'}{abs(pct):.1f}% fra {prev_t} — {arrow} {_n(abs(change))})."
    )

    context_bits = []
    if nat_pct is not None:
        context_bits.append(f"hele landet {'+' if nat_pct >= 0 else ''}{nat_pct:.1f}%")
    if rog_pct is not None:
        context_bits.append(f"Rogaland {'+' if rog_pct >= 0 else ''}{rog_pct:.1f}%")
    context = ("Til sammenligning: " + ", ".join(context_bits) + ".") if context_bits else ""

    # Er Stavanger et avvik fra landet? Det er ofte den beste vinkelen.
    divergence = ""
    if nat_pct is not None and abs(pct - nat_pct) >= 1.0:
        retning = "sterkere" if abs(pct) > abs(nat_pct) else "svakere"
        divergence = f" Stavanger endrer seg {retning} enn landet."

    table = probe["table"]
    angle = (
        f"Datadrevet sak: «{label}» i Stavanger {arrow} {abs(pct):.1f}% på ett år.{divergence} "
        f"Ring SSB/kommunen for aarsak, finn en ung case-person som merker det, "
        f"og sett tallet i lokal sammenheng."
    )
    why = (finding + " " + context).strip()

    # Basisscore = storrelsen paa avviket + lokal + tema + divergens fra landet.
    # Dekningsjustering (originalitet) legges paa i scoring.finalize_scores.
    base = 5.0 + min(abs(pct), 30.0) * 0.6
    base += 6.0                       # alltid lokal (Stavanger)
    if probe.get("topics"):
        base += 3.0
    if divergence:
        base += 4.0

    metric_value = f"{'+' if change >= 0 else '−'}{abs(pct):.1f} %".replace(".", ",")
    metric_period = f"{prev_t}–{latest_t}"
    _table_labels = {"07459": "befolkning"}
    source_label = f"{_table_labels.get(table, 'tabell')}, {table}"

    return Case(
        key=f"ssb:{probe['id']}",
        title=f"{label} i Stavanger {arrow} {abs(pct):.1f} %".replace(".", ","),
        score=base,
        geo="lokal",
        topics=list(probe.get("topics", [])),
        angle=angle,
        why=why,
        signals=[],
        created_at=now_utc(),
        kind="data",
        target_relevance="høy" if probe.get("topics") else "middels",
        finding=finding + (" " + context if context else ""),
        metric_value=metric_value,
        metric_period=metric_period,
        data_source=f"SSB ({source_label})",
        data_url=f"https://www.ssb.no/statbank/table/{table}",
        coverage_query=probe.get("coverage_query", f"Stavanger {label}"),
        # HELE tidsserien for Stavanger, ikke bare de to siste punktene. SSB
        # sender fem perioder i det samme svaret; vi brukte to og kastet resten.
        # Det er den forskjellen som avgjor om trendlinja er der foerste dag
        # eller om den maa bygge seg opp over maaneder av morgenskann.
        serie=[[t, float(v)] for t, v in local],
    )


def collect(temaer: list[str] | None = None) -> tuple[list[Case], list[str]]:
    """Faste befolkningsprober, filtrert paa journalistens temavalg.

    Eieren 26.07.2026: «Den gir ikke det jeg velger i menyen.» Han hadde rett -
    bare soekesystemet (ssb_sok) leste valget. Disse fem probene kjorte uansett,
    og fordi de scorer hoyt, la de seg oeverst og tok KI-plassene fra det han
    faktisk hadde bedt om.

    Tomt valg = alle prober, som foer."""
    if not ENABLE_SSB:
        return [], ["SSB: avslaatt (CASE_RADAR_ENABLE_SSB=false)"]

    onsket = demografi_for(temaer)
    prober = SSB_PROBES
    if onsket:
        prober = [p for p in SSB_PROBES if onsket & set(p.get("topics", []))]

    cases: list[Case] = []
    status: list[str] = []
    if onsket:
        status.append(
            f"SSB: {len(prober)} av {len(SSB_PROBES)} befolkningsprober "
            "passer temavalget"
        )
    for probe in prober:
        try:
            data = _fetch(probe["table"], probe["query"])
            series, tids = _series_by_region(data)
            case = _make_case(probe, series, tids)
            if case:
                # lagre endrings-magnitude for scoring via topics-uavhengig felt
                cases.append(case)
                status.append(f"SSB {probe['table']}/{probe['id']}: ok")
            else:
                status.append(f"SSB {probe['id']}: for lite data")
        except Exception as exc:  # noqa: BLE001 - fail-soft per probe
            status.append(f"[FEIL] SSB {probe['id']}: {type(exc).__name__}")
    return cases, status

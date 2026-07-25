"""Enkel SQLite-lagring av siste skann (stdlib, ingen ORM-avhengighet).

Vi lagrer hvert skann som en JSON-blob slik at dashboardet kan vise siste
resultat uten a hente kilder paa nytt ved hver sidelast.
"""

from __future__ import annotations

import json
import os
import sqlite3
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.config import DB_PATH


def _connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS approved (
            key TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS decisions (
            key TEXT PRIMARY KEY,
            status TEXT NOT NULL
        )
        """
    )
    # Redaksjonell kalender: planlagt publiseringsdato + status per godkjent sak.
    # Lagt til med ALTER slik at eksisterende databaser oppgraderes uten tap.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(approved)")}
    if "planned_for" not in cols:
        conn.execute("ALTER TABLE approved ADD COLUMN planned_for TEXT")
    if "start_date" not in cols:
        conn.execute("ALTER TABLE approved ADD COLUMN start_date TEXT")
    if "deadline" not in cols:
        conn.execute("ALTER TABLE approved ADD COLUMN deadline TEXT")
    # Eldre rader hadde bare planned_for - la den bli startdato.
    conn.execute(
        "UPDATE approved SET start_date = planned_for "
        "WHERE start_date IS NULL AND planned_for IS NOT NULL"
    )
    if "stage" not in cols:
        conn.execute("ALTER TABLE approved ADD COLUMN stage TEXT NOT NULL DEFAULT 'ide'")
    # Arkiv: sveiper man bort et utkast skal det kunne hentes tilbake. Vi setter
    # et tidsstempel i stedet for aa slette - et utkast som er borte for godt er
    # en time med arbeid som er borte for godt.
    if "arkivert_at" not in cols:
        conn.execute("ALTER TABLE approved ADD COLUMN arkivert_at TEXT")
    # Timer per dag saken krever. Kalenderen legger dem sammen per dag, saa
    # journalisten ser at fire saker med tre timer hver ikke faar plass i én dag.
    if "timer_per_dag" not in cols:
        conn.execute(
            f"ALTER TABLE approved ADD COLUMN timer_per_dag REAL NOT NULL "
            f"DEFAULT {TIMER_STANDARD}"
        )
    # Ferdig er noe annet enn arkivert. Arkivert = «denne ville jeg ikke ha».
    # Ferdig = «denne er gjort». Begge forsvinner fra kalenderen, men de betyr
    # ikke det samme, og en ferdig sak skal kunne aapnes igjen uten aa se ut som
    # om den ble forkastet.
    if "fullfort_at" not in cols:
        conn.execute("ALTER TABLE approved ADD COLUMN fullfort_at TEXT")
    conn.commit()
    return conn


# Antatt tid per sak per arbeidsdag naar journalisten ikke har sagt noe annet.
TIMER_STANDARD = 2.0
# Hvor mye han faktisk kan jobbe paa en dag. Justerbart - en frilanser og en
# fast ansatt har ikke samme dag.
DAGSKAPASITET_STANDARD = 7.5
MAKS_TIMER = 24.0


def dagskapasitet() -> float:
    try:
        return max(0.5, min(MAKS_TIMER, float(meta_get("dagskapasitet", ""))))
    except (TypeError, ValueError):
        return DAGSKAPASITET_STANDARD


def sett_dagskapasitet(timer: float) -> float:
    ny = max(0.5, min(MAKS_TIMER, float(timer)))
    meta_set("dagskapasitet", f"{ny:g}")
    return ny


# Hvor mange skann vi tar vare paa. Bare det nyeste leses noen gang, men noen
# fa gamle er greit aa ha hvis noe ser rart ut. Uten taket vokser tabellen for
# alltid: hvert skann OG hvert utkast skriver en full kopi, saa ett skann i
# timen ble rundt 90 MB paa ett aar - paa en liten VPS er det ren sloesing.
MAKS_SKANN = 20


def save_scan(payload: dict) -> None:
    payload = {**payload, "created_at": datetime.now(tz=UTC).isoformat()}
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO scans (created_at, payload) VALUES (?, ?)",
            (payload["created_at"], json.dumps(payload, ensure_ascii=False)),
        )
        conn.execute(
            "DELETE FROM scans WHERE id NOT IN "
            "(SELECT id FROM scans ORDER BY id DESC LIMIT ?)",
            (MAKS_SKANN,),
        )
        conn.commit()
    finally:
        conn.close()


def load_latest() -> dict | None:
    if not os.path.exists(DB_PATH):
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT payload FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def approve_lead(key: str, lead: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO approved (key, created_at, payload) VALUES (?, ?, ?)",
            (key, _now(), json.dumps(lead, ensure_ascii=False)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO decisions (key, status) VALUES (?, 'approved')", (key,)
        )
        conn.commit()
    finally:
        conn.close()


def reject_lead(key: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM approved WHERE key = ?", (key,))
        conn.execute(
            "INSERT OR REPLACE INTO decisions (key, status) VALUES (?, 'rejected')", (key,)
        )
        conn.commit()
    finally:
        conn.close()


def list_approved(*, arkiverte: bool = False, fullforte: bool | None = None) -> list[dict]:
    """Godkjente saker. Arkiverte (sveipet bort) er ute av veien som standard.

    Ferdige saker er IKKE ute av veien her. «Ferdig» betyr ute av KALENDEREN -
    artikkelen ligger fortsatt under Lagrede utkast, for det er der journalisten
    finner igjen det han har skrevet. Bare kalenderen og oppgavelista filtrerer
    dem bort (`fullforte=False`)."""
    if not os.path.exists(DB_PATH):
        return []
    conn = _connect()
    try:
        if arkiverte:
            hvor = "arkivert_at IS NOT NULL"
        elif fullforte is True:
            hvor = "fullfort_at IS NOT NULL AND arkivert_at IS NULL"
        elif fullforte is False:
            hvor = "arkivert_at IS NULL AND fullfort_at IS NULL"
        else:
            hvor = "arkivert_at IS NULL"
        rows = conn.execute(
            "SELECT payload, created_at, start_date, deadline, stage, arkivert_at, "
            f"timer_per_dag, fullfort_at FROM approved WHERE {hvor} "
            "ORDER BY COALESCE(deadline, start_date, created_at) ASC"
        ).fetchall()
        out = []
        for payload, created, start, deadline, stage, arkivert, timer, fullfort in rows:
            lead = json.loads(payload)
            lead["_approved_at"] = created
            lead["_start"] = start or ""
            lead["_deadline"] = deadline or ""
            lead["_stage"] = stage or "ide"
            lead["_arkivert"] = arkivert or ""
            lead["_fullfort"] = fullfort or ""
            lead["_timer"] = float(timer if timer is not None else TIMER_STANDARD)
            out.append(lead)
        return out
    finally:
        conn.close()


def fullfor(key: str) -> bool:
    """«Ferdig». Saken forsvinner fra kalenderen og oppgavelista.

    Vi sletter ikke og nullstiller ikke datoene: trykker han feil, skal ett trykk
    paa «angre» sette den tilbake nøyaktig der den sto."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE approved SET fullfort_at = ? WHERE key = ? AND fullfort_at IS NULL",
            (_now(), key),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def gjenapne(key: str) -> bool:
    """Angre «Ferdig» - saken tilbake i kalenderen med datoer og timer i behold."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE approved SET fullfort_at = NULL WHERE key = ?", (key,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def oppgaver() -> list[dict]:
    """Saker som ligger i kalenderen, med naermeste frist foerst.

    Uten dato er den ikke lagt inn i kalenderen enda, og hoerer derfor ikke
    hjemme i oppgavelista - den staar under «Uten dato» paa kalendersida."""
    med_dato = [
        x for x in list_approved(fullforte=False)
        if x.get("_deadline") or x.get("_start")
    ]
    # Frist foerst. Mangler frist, sorterer vi paa startdato - da er den fortsatt
    # planlagt, bare uten sluttstrek.
    return sorted(med_dato, key=lambda x: (x.get("_deadline") or x.get("_start") or "9999"))


def arkiver(key: str) -> bool:
    """Sveip venstre: legg saken bort. Returnerer False hvis den ikke fantes.

    Vi sletter ikke. Et utkast representerer bade KI-kvote og journalistens
    vurdering; en feilsveip paa mobil skal koste ett trykk aa angre, ikke en ny
    runde med skriving."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE approved SET arkivert_at = ? WHERE key = ? AND arkivert_at IS NULL",
            (_now(), key),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def gjenopprett(key: str) -> bool:
    """Angre en sveip - saken tilbake i lista, med datoer og stadium i behold."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE approved SET arkivert_at = NULL WHERE key = ?", (key,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ── Redaksjonell kalender ────────────────────────────────────────────────────
# Stadier en sak gaar gjennom. Rekkefolgen er bevisst: den speiler arbeidsflyten
# i en redaksjon, og UI-et bruker samme rekkefolge.
STAGES: tuple[str, ...] = ("ide", "research", "skriving", "publisert")
STAGE_LABELS: dict[str, str] = {
    "ide": "Idé",
    "research": "Research",
    "skriving": "Skriving",
    "publisert": "Publisert",
}


def set_plan(
    key: str,
    *,
    start_date: str | None = None,
    deadline: str | None = None,
    stage: str | None = None,
    timer: float | str | None = None,
) -> None:
    """Sett startdato, deadline og/eller stadium for en godkjent sak.

    Tom streng fjerner datoen. Ugyldige datoer ignoreres i stedet for aa kaste -
    UI skal aldri kunne laase seg paa en skrivefeil. Er deadline foer start,
    byttes de om: det er aapenbart hva brukeren mente."""
    def _clean(v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return ""
        try:
            date.fromisoformat(v)
        except ValueError:
            return None
        return v

    s, d = _clean(start_date), _clean(deadline)
    if s and d and d < s:
        s, d = d, s

    conn = _connect()
    try:
        if s is not None:
            conn.execute(
                "UPDATE approved SET start_date = ?, planned_for = ? WHERE key = ?",
                (s or None, s or None, key),
            )
        if d is not None:
            conn.execute("UPDATE approved SET deadline = ? WHERE key = ?", (d or None, key))
        if stage is not None and stage in STAGES:
            conn.execute("UPDATE approved SET stage = ? WHERE key = ?", (stage, key))
        if timer is not None and str(timer).strip():
            # Ugyldig tall ignoreres i stedet for aa kaste - samme regel som
            # datoene. UI-et skal aldri laase seg paa en skrivefeil.
            try:
                t = max(0.0, min(MAKS_TIMER, float(str(timer).replace(",", ".").strip())))
            except ValueError:
                t = None
            if t is not None:
                conn.execute(
                    "UPDATE approved SET timer_per_dag = ? WHERE key = ?", (t, key)
                )
        conn.commit()
    finally:
        conn.close()


def timer_per_dag(dager: dict[str, list[dict]]) -> dict[str, float]:
    """Sum timer per dag. Fire saker à tre timer er tolv timer - det skal synes."""
    return {
        iso: round(sum(float(x.get("_timer") or 0) for x in saker), 2)
        for iso, saker in dager.items()
    }


def calendar_month(year: int, month: int) -> dict[str, list[dict]]:
    """Godkjente saker plassert paa hver dag de er i arbeid.

    En sak med start 3. og deadline 6. vises paa 3, 4, 5 OG 6 - slik at kalenderen
    faktisk viser arbeidsbelastning, ikke bare to prikker. Hver oppfoering merkes
    med om dagen er start, deadline, begge, eller midt i loepet."""
    out: dict[str, list[dict]] = {}
    last_day = monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)

    # Ferdige saker skal ut av kalenderen - det er hele poenget med «Ferdig».
    for lead in list_approved(fullforte=False):
        s_raw, d_raw = lead.get("_start") or "", lead.get("_deadline") or ""
        if not s_raw and not d_raw:
            continue
        try:
            start = date.fromisoformat(s_raw) if s_raw else date.fromisoformat(d_raw)
            end = date.fromisoformat(d_raw) if d_raw else start
        except ValueError:
            continue
        if end < start:
            start, end = end, start
        # Klipp til maaneden vi viser.
        span_start = max(start, month_start)
        span_end = min(end, month_end)
        if span_start > span_end:
            continue
        day = span_start
        while day <= span_end:
            iso = day.isoformat()
            out.setdefault(iso, []).append(
                {
                    **lead,
                    "_is_start": day == start,
                    "_is_deadline": day == end,
                }
            )
            day += timedelta(days=1)
    return out


# ── Nytt siden sist ──────────────────────────────────────────────────────────
# Et skann henter de samme kildene hver gang, saa de samme funnene dukker opp igjen.
# Vi husker naar en sak ble sett foerste gang, slik at UI kan loefte fram det som
# faktisk er NYTT - og la det gamle synke.


def mark_seen(keys: list[str]) -> dict[str, str]:
    """Registrer saker som sett. Returnerer {key: forste_gang_sett} for ALLE."""
    conn = _connect()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, first_seen TEXT NOT NULL)"
        )
        now = _now()
        conn.executemany(
            "INSERT OR IGNORE INTO seen (key, first_seen) VALUES (?, ?)",
            [(k, now) for k in keys],
        )
        conn.commit()
        rows = conn.execute("SELECT key, first_seen FROM seen").fetchall()
        return {k: v for k, v in rows}
    finally:
        conn.close()


def seen_map() -> dict[str, str]:
    """{key: forste_gang_sett} uten aa registrere noe nytt."""
    if not os.path.exists(DB_PATH):
        return {}
    conn = _connect()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, first_seen TEXT NOT NULL)"
        )
        rows = conn.execute("SELECT key, first_seen FROM seen").fetchall()
        return {k: v for k, v in rows}
    finally:
        conn.close()


# ── SSB-utforskning ──────────────────────────────────────────────────────────
# Soekesystemet leter etter STATISTIKK vi ikke har sett paa foer. For at et nytt
# soek skal gi noe nytt maa vi huske hvilke tabeller som allerede er provd - og
# hvorfor de ble forkastet. Noen avslag er permanente (tabellen har ikke
# kommunetall), andre er ferskvare (tallet laa under terskel DENNE gangen, men
# SSB oppdaterer tabellen fire ganger i aaret).

# Avslag som aldri endrer seg: strukturen i tabellen blir ikke en annen av at
# den oppdateres. Disse probes aldri paa nytt.
PERMANENTE_AVSLAG: frozenset[str] = frozenset(
    {"ingen-kommune", "ikke-eliminerbar", "for-kort", "ingen-tid", "delvis-periode"}
)


def _ssb_tabell(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ssb_tabeller (
            id TEXT PRIMARY KEY,
            utforsket_at TEXT NOT NULL,
            verdikt TEXT NOT NULL,
            oppdatert TEXT NOT NULL DEFAULT '',
            notat TEXT NOT NULL DEFAULT ''
        )
        """
    )


def ssb_utforsket() -> dict[str, dict[str, str]]:
    """{tabell-id: {verdikt, oppdatert, notat, utforsket_at}}."""
    if not os.path.exists(DB_PATH):
        return {}
    conn = _connect()
    try:
        _ssb_tabell(conn)
        rows = conn.execute(
            "SELECT id, verdikt, oppdatert, notat, utforsket_at FROM ssb_tabeller"
        ).fetchall()
        return {
            r[0]: {
                "verdikt": r[1],
                "oppdatert": r[2],
                "notat": r[3],
                "utforsket_at": r[4],
            }
            for r in rows
        }
    finally:
        conn.close()


def marker_ssb_tabell(
    tabell_id: str, verdikt: str, *, oppdatert: str = "", notat: str = ""
) -> None:
    """Skriv ned hva som skjedde da vi provde denne tabellen."""
    conn = _connect()
    try:
        _ssb_tabell(conn)
        conn.execute(
            "INSERT OR REPLACE INTO ssb_tabeller "
            "(id, utforsket_at, verdikt, oppdatert, notat) VALUES (?, ?, ?, ?, ?)",
            (tabell_id, _now(), verdikt, oppdatert, notat),
        )
        conn.commit()
    finally:
        conn.close()


def bor_probes(tabell_id: str, oppdatert: str, utforsket: dict[str, dict[str, str]]) -> bool:
    """Er det verdt aa bruke et API-kall paa denne tabellen naa?

    Ja hvis vi aldri har sett den. Ja hvis avslaget var midlertidig OG SSB har
    publisert nye tall siden sist. Nei ellers - da bruker vi kallet paa noe annet.
    """
    kjent = utforsket.get(tabell_id)
    if kjent is None:
        return True
    if kjent["verdikt"] in PERMANENTE_AVSLAG:
        return False
    # Midlertidig avslag eller tidligere treff: bare interessant med nye tall.
    return bool(oppdatert) and oppdatert != kjent.get("oppdatert", "")


def _meta_tabell(conn: sqlite3.Connection) -> None:
    """Enkel noekkel/verdi-tabell for markorer (hvor langt vi har lett i katalogen)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta (nokkel TEXT PRIMARY KEY, verdi TEXT NOT NULL)"
    )


def meta_get(nokkel: str, standard: str = "") -> str:
    if not os.path.exists(DB_PATH):
        return standard
    conn = _connect()
    try:
        _meta_tabell(conn)
        row = conn.execute("SELECT verdi FROM meta WHERE nokkel = ?", (nokkel,)).fetchone()
        return row[0] if row else standard
    finally:
        conn.close()


def meta_set(nokkel: str, verdi: str) -> None:
    conn = _connect()
    try:
        _meta_tabell(conn)
        conn.execute("INSERT OR REPLACE INTO meta (nokkel, verdi) VALUES (?, ?)", (nokkel, verdi))
        conn.commit()
    finally:
        conn.close()


def neste_i_rotasjon(nokkel: str, elementer: list[str], antall: int) -> list[str]:
    """Plukk `antall` elementer og flytt markoeren - saa neste skann tar de neste.

    Dette er kjernen i «trykker jeg soek igjen, skal jeg faa noe nytt»: vi leter
    ikke i den samme delen av SSBs katalog to ganger paa rad.
    """
    if not elementer or antall <= 0:
        return []
    try:
        start = int(meta_get(nokkel, "0"))
    except ValueError:
        start = 0
    start %= len(elementer)
    valgt = [elementer[(start + i) % len(elementer)] for i in range(min(antall, len(elementer)))]
    meta_set(nokkel, str((start + len(valgt)) % len(elementer)))
    return valgt


def decisions_map() -> dict[str, str]:
    """{key: "approved"|"rejected"} for aa vise status paa radaren."""
    if not os.path.exists(DB_PATH):
        return {}
    conn = _connect()
    try:
        rows = conn.execute("SELECT key, status FROM decisions").fetchall()
        return {k: s for k, s in rows}
    finally:
        conn.close()

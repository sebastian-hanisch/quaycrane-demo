"""Schedule-Konstruktion aus einer Einfüge-Reihenfolge, Machbarkeitsprüfung und Kennzahlen.

Eine Lösung wird als `order` repräsentiert: eine Liste von (bay, crane)-Paaren in der
Reihenfolge, in der sie einem Kran zugewiesen werden. Diese Reihenfolge legt sowohl die
Kranzuordnung als auch - je Kran - die Bearbeitungsreihenfolge fest (Teilfolge der `order`,
eingeschränkt auf diesen Kran). `build_schedule` baut daraus einen konkreten Zeitplan.

Konstruktionsprinzip (bewusst EIN einziger, durchgängig verifizierter Weg statt eines
"optimistischen" Pfads mit Sicherheitsnetz - siehe [[feedback_interval_avoidance_vs_iterative_pushing]]
für die allgemeine Lehre dahinter): jede Aufgabe wird einzeln eingefügt, und für jeden
Kandidaten-Zeitpunkt wird die tatsächliche, resultierende Trajektorie GEGEN DIE ECHTEN, bereits
committeten Segmente anderer Kräne geprüft (`_safe_breakpoint_departure`) - nicht gegen eine
Formel, von der bloß angenommen wird, dass sie sicher ist. Damit ist per Konstruktion jeder
zurückgegebene Zeitplan zulässig, sofern für die gegebene KRANZUORDNUNG überhaupt irgendeine
zulässige Zeitplanung existiert. Eigener Fund: die Kranzuordnung selbst kann - unabhängig von
jeder Zeitplanung - strukturell unmöglich sein (z.B. weist ein rein lastbasiertes Greedy-
Verfahren wie LPT zwei benachbarten Kränen Bays zu, die bei engem Sicherheitsabstand keinerlei
gemeinsame sichere Zeitplanung mehr zulassen - siehe `ScheduleInfeasibleError`); das ist keine
Lücke in der Konstruktion, sondern eine Eigenschaft der `order` selbst - `build_schedule` meldet
das dann, statt eine unzulässige Lösung zurückzugeben."""

from collections import defaultdict
from dataclasses import dataclass


class ScheduleInfeasibleError(Exception):
    """Für DIESE Kranzuordnung (`order`) existiert keine zulässige Zeitplanung, für keinen
    Einfügezeitpunkt - unabhängig davon, wie clever konstruiert wird (siehe
    `_safe_breakpoint_departure`s Dokumentation für ein konkretes Beispiel: zwei benachbarte
    Kräne, deren zugewiesene Bays bei engem Sicherheitsabstand keinen gemeinsamen sicheren
    Zeitplan mehr zulassen). Aufrufer, die mehrere Kandidaten-`order`s vergleichen (siehe
    quaycrane_heuristic.py), behandeln dies als "unendlich schlecht" statt abzustürzen."""


@dataclass(frozen=True)
class Task:
    bay: int
    crane: int
    start: float
    end: float
    wait: float  # durch Kran-Interferenz verursachte zusätzliche Wartezeit (>= 0)
    departure: float = None  # wann der Kran fuer DIESE Aufgabe von seiner vorherigen Position
    # losgefahren ist - explizit statt aus `wait` rueckgerechnet, weil ein einzelner
    # `wait`-Skalar nicht unterscheidet, OB gewartet wurde, weil der Kran am Ursprung blieb, am
    # Ziel wartete, oder eine Mischung aus beidem - `crane_position_segments` braucht die
    # tatsaechlich gewaehlte Abfahrt, um dieselbe Trajektorie zu zeichnen/pruefen, die beim
    # Bauen als sicher bestaetigt wurde. None (Default) bedeutet "unbekannt, nimm
    # spaetestmoegliche Abfahrt an" - sicher fuer CP-SAT-Ergebnisse (siehe quaycrane_cp_solver.py,
    # das genau dieses Fenster erzwingt) und fuer Tests, die Task() direkt mit fertigen
    # start/end-Werten bauen.


def _intervals_overlap(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def _construction_horizon(instance):
    """Großzügige, aber endliche obere Schranke für die Gesamtdauer - dieselbe Größenordnung wie
    der Horizont im CP-SAT-Modell (siehe quaycrane_cp_solver.py), hier nur in echten Minuten
    statt skalierten Ganzzahlen. Dient `_safe_breakpoint_departure` als garantiert sicherer
    letzter Kandidat, falls die tatsächlich schon eingeplanten Aktivitäten das nicht selbst schon
    hergeben."""
    total_work = sum(b.duration for b in instance.bays)
    max_travel = instance.travel_time_per_bay * instance.n_bays
    return total_work + instance.n_bays * max_travel + 1.0


def _task_segments(crane, prev_t, prev_pos, departure, bay, travel_time, start, end):
    """Zerlegt EINE Aufgabe in ihre Positions-Segmente (crane, t0, pos0, t1, pos1, kind), kind in
    {"wait", "travel", "work"}: optional Warten am Ursprung, optional Fahrt, optional Warten am
    Ziel, immer Bearbeitung. Reiner, zustandsloser Baustein - sowohl für die vollständige
    Rekonstruktion eines fertigen Schedules (`crane_position_segments`) als auch für die
    inkrementelle Konstruktion (`build_schedule`) genutzt, damit beide GARANTIERT dieselbe
    Trajektorien-Konvention verwenden (eigener Fund vom 2026-09-04: zwei unabhängige
    Rekonstruktionen derselben Sache liefen früher schon einmal auseinander - siehe README)."""
    departure = max(departure, prev_t)  # Sicherheitsnetz gegen Rundungsfehler
    segments = []
    if departure > prev_t + 1e-9:
        segments.append((crane, prev_t, prev_pos, departure, prev_pos, "wait"))
    arrival = departure + travel_time
    if bay != prev_pos:
        segments.append((crane, departure, prev_pos, arrival, bay, "travel"))
    if start > arrival + 1e-9:
        segments.append((crane, arrival, bay, start, bay, "wait"))
    segments.append((crane, start, bay, end, bay, "work"))
    return segments


def _ordered_margin_violation(seg_a, seg_b, margin):
    """`_segments_violate_margin` erwartet das Segment des Krans mit dem KLEINEREN Index zuerst -
    kleiner Wrapper, der das unabhängig von der Aufrufreihenfolge sicherstellt."""
    if seg_a[0] < seg_b[0]:
        return _segments_violate_margin(seg_a, seg_b, margin)
    return _segments_violate_margin(seg_b, seg_a, margin)


def _safe_breakpoint_departure(instance, other_segments, crane, bay, prev_end, prev_pos, travel, verified):
    """Probiert als Abfahrtszeit JEDEN Zeitpunkt durch, an dem sich der Sicherheitsstatus
    irgendeines bereits eingeplanten (ECHTEN, in `other_segments` übergebenen) Segments ändern
    KÖNNTE (dessen Start oder Ende) - dazwischen kann sich nichts ändern, da jede Position eine
    affine Funktion der Zeit ist (siehe `_segments_violate_margin`), die Liste deckt also
    lückenlos jede mögliche sicher/unsicher-Grenze ab. Der letzte Kandidat (nach dem Ende JEDER
    bislang eingeplanten echten Aktivität) ist per Konstruktion sicher - die Suche geht also nie
    leer aus, außer wenn selbst das nicht hilft (siehe unten).

    Zwei einfachere Formel-Fallbacks wurden verworfen: weder "sofort losfahren" noch "warten bis
    zum Ende der spätesten bislang eingeplanten Aktivität" ist für sich pauschal sicher - im
    ersten Fall kann die Fahrt selbst noch verletzen, im zweiten Fall verletzt schon das WARTEN
    am Ursprung, wenn diese Position dauerhaft (nicht nur vorübergehend) zu nah an einer bereits
    eingeplanten Aktivität eines anderen Krans liegt (spätere Abfahrt hilft dann nicht - der
    Kran war während der Störung ohnehin die ganze Zeit dort). Erst das tatsächliche AUSPROBIEREN
    jedes in Frage kommenden Zeitpunkts, jeweils per `verified` gegen die echten Segmente
    geprüft, ist wasserdicht."""
    # Eigener Fund: die Margin-Prüfung (`_segments_violate_margin`) wertet beide Fensterenden
    # EINSCHLIESSLICH aus (kein offenes Intervall) - eine Abfahrt GENAU auf das Ende eines
    # gefährlichen Segments gelegt gilt dort noch als "während" dessen Aktivität und bleibt
    # verletzt. Jeder Kandidat, der von einem Segmentende abgeleitet ist, braucht deshalb einen
    # winzigen Sicherheitsabstand danach, um wirklich STRIKT danach zu liegen.
    epsilon = 1e-6
    other_ends = [s[3] for s in other_segments]
    horizon = max([_construction_horizon(instance), prev_end] + other_ends) + epsilon
    breakpoints = {prev_end, horizon}
    for seg in other_segments:
        if seg[1] >= prev_end:
            breakpoints.add(seg[1])
        if seg[3] >= prev_end:
            breakpoints.add(seg[3] + epsilon)

    for candidate_departure in sorted(breakpoints):
        candidate_start = candidate_departure + travel
        if verified(candidate_departure, candidate_start):
            return candidate_departure, candidate_start
    # Selbst der "horizon"-Kandidat (nach dem Ende JEDER bislang eingeplanten echten Aktivität)
    # scheitert nur, wenn schon das bloße WARTEN an `prev_pos` (unsere erzwungene, feste
    # Position, solange wir nicht abgefahren sind) dauerhaft zu nah an einer bereits
    # eingeplanten Aktivität liegt - dann hilft KEINE Abfahrtszeit, da wir während der ganzen
    # Störung ohnehin dort waren. Das ist keine lösbare Zeitplanungsfrage mehr, sondern zeigt:
    # DIESE Kranzuordnung selbst (`crane` auf `bay`, im Kontext der bereits committeten
    # Nachbar-Aufgaben) lässt für keinen Zeitpunkt eine sichere Lösung zu.
    raise ScheduleInfeasibleError(
        f"Für Kran {crane} an Bay {bay} existiert keine sichere Zeitplanung, gegeben die bereits "
        "eingeplanten Aufgaben anderer Kräne - die Kranzuordnung selbst ist hier unschedulierbar."
    )


def _round_robin_interleave(instance, order):
    """Ordnet `order` (unverändert in Kranzuordnung UND je Kran relativer Reihenfolge) so um,
    dass die erste Aufgabe jedes Krans zuerst kommt, dann die zweite jedes Krans, usw. - reine
    EINFÜGEreihenfolge für die Konstruktion, ändert weder welcher Kran welche Bay bekommt noch
    die Reihenfolge INNERHALB eines Krans.

    Reine Qualitäts-, keine Korrektheits-Maßnahme (`build_schedule` ist für JEDE Einfügereihen-
    folge korrekt, da jede Platzierung ohnehin gegen die echten, bereits committeten Segmente
    verifiziert wird): baut man stattdessen blockweise (ein Kran komplett, dann der nächste),
    kann ein früh eingeplanter Kran einen riesigen, unnötigen Umweg um das GESAMTE bereits
    fertige Arbeitspensum eines noch gar nicht an der Reihe gewesenen Nachbarn nehmen, sobald der
    doch noch drankommt - rundenweises Verschränken gibt jedem Kran seine erste (meist
    ausschlaggebende) Aufgabe früh und hält solche Umwege klein."""
    by_crane = defaultdict(list)
    for bay, crane in order:
        by_crane[crane].append((bay, crane))

    interleaved = []
    round_idx = 0
    remaining = True
    while remaining:
        remaining = False
        for crane in range(instance.n_cranes):
            bays = by_crane.get(crane, [])
            if round_idx < len(bays):
                interleaved.append(bays[round_idx])
                remaining = True
        round_idx += 1
    return interleaved


def build_schedule(instance, order):
    """Baut den Zeitplan in EINEM Durchgang, Aufgabe für Aufgabe (rundenweise verschränkt, siehe
    `_round_robin_interleave`): für jede Aufgabe sucht `_safe_breakpoint_departure` einen gegen
    die bereits committeten Segmente ALLER anderen Kräne verifizierten Abfahrtszeitpunkt. Jede
    Platzierung ist damit beim Einfügen bereits bewiesen sicher - kein optimistischer Bau-Schritt
    mit nachträglicher Prüfung und separatem Sicherheitsnetz nötig (frühere Fassung hatte genau
    das: einen schnellen, aber nicht durchgängig korrekten Konstruktionspfad plus einen
    langsameren, korrekten Fallback - siehe README für die Geschichte dahinter). Ist für die
    gegebene Kranzuordnung an irgendeiner Stelle keine sichere Platzierung mehr möglich, wird das
    als `ScheduleInfeasibleError` gemeldet statt eine unzulässige Lösung zurückzugeben (siehe
    dessen Docstring)."""
    tasks = {}
    crane_last_end = [0.0] * instance.n_cranes
    crane_last_pos = list(instance.crane_start_positions)
    segments_by_crane = [[] for _ in range(instance.n_cranes)]

    for bay, crane in _round_robin_interleave(instance, order):
        prev_end, prev_pos = crane_last_end[crane], crane_last_pos[crane]
        duration = instance.bays[bay].duration
        travel = instance.travel_time(prev_pos, bay)
        margin = instance.safety_margin
        # Nur die Segmente ANDERER Kräne sind für die Sicherheitsprüfung relevant - eigene,
        # bereits committete Aufgaben können sich per Konstruktion (jede neue startet frühestens
        # beim Ende der vorherigen) nie mit der neuen überlappen.
        other_segments = [s for c in range(instance.n_cranes) if c != crane for s in segments_by_crane[c]]

        def verified(departure, start, _prev_end=prev_end, _prev_pos=prev_pos, _travel=travel, _duration=duration):
            new_segments = _task_segments(crane, _prev_end, _prev_pos, departure, bay, _travel, start, start + _duration)
            return not any(
                _ordered_margin_violation(seg, other, margin) for seg in new_segments for other in other_segments
            )

        departure, start = _safe_breakpoint_departure(
            instance, other_segments, crane, bay, prev_end, prev_pos, travel, verified
        )

        end = start + duration
        wait = max(0.0, start - (prev_end + travel))
        tasks[bay] = Task(bay=bay, crane=crane, start=start, end=end, wait=wait, departure=departure)
        segments_by_crane[crane].extend(_task_segments(crane, prev_end, prev_pos, departure, bay, travel, start, end))
        crane_last_end[crane] = end
        crane_last_pos[crane] = bay
    return tasks


def crane_position_segments(instance, tasks):
    """Liefert je Kran eine Liste von Segmenten (crane, t0, pos0, t1, pos1, kind), kind in
    {"wait", "travel", "work"}: Warten (Position konstant, am Ursprung ODER am Ziel), Fahrt
    (Position ändert sich linear) und Bearbeitung (Position konstant) - siehe `_task_segments`
    für die eigentliche Zerlegung, hier nur je Kran chronologisch aneinandergereiht.

    Nutzt `t.departure`, falls gesetzt (von `build_schedule` bewusst mitgeführt - siehe
    `Task.departure`-Docstring: ein einzelner `wait`-Skalar reicht dafür nicht). Ist `t.departure`
    None (CP-SAT-Ergebnisse, direkt aus `Task()` gebaute Testfälle), fällt es auf "so spät wie
    möglich losfahren" zurück (`t.start - Fahrzeit`) - für CP-SAT ist das sicher, weil genau
    dieses Fenster dort aktiv erzwungen wird (siehe quaycrane_cp_solver.py).

    Wird sowohl von check_feasible als auch vom Trajektorien-Chart genutzt, damit Prüfung und
    Darstellung nie auseinanderlaufen."""
    by_crane = defaultdict(list)
    for t in tasks.values():
        by_crane[t.crane].append(t)

    segments = []
    for crane, ts in by_crane.items():
        ts = sorted(ts, key=lambda t: t.start)
        prev_t, prev_pos = 0.0, instance.crane_start_positions[crane]
        for t in ts:
            travel_time = instance.travel_time(prev_pos, t.bay)
            departure = t.departure if t.departure is not None else t.start - travel_time
            segments.extend(_task_segments(crane, prev_t, prev_pos, departure, t.bay, travel_time, t.start, t.end))
            prev_t, prev_pos = t.end, t.bay
    return segments


def _position_on_segment(t0, p0, t1, p1, t):
    if t1 <= t0:
        return p0
    return p0 + (p1 - p0) * (t - t0) / (t1 - t0)


def _segments_violate_margin(seg_left, seg_right, margin):
    """seg_left gehört zum Kran mit dem kleineren Index (muss links bleiben). Da beide Segmente
    linear in der Zeit sind, ist ihre Differenz über dem gemeinsamen Zeitfenster ebenfalls
    linear - es reicht, die beiden Fensterenden zu prüfen (Extrema einer affinen Funktion)."""
    _, t0a, p0a, t1a, p1a, _ = seg_left
    _, t0b, p0b, t1b, p1b, _ = seg_right
    lo, hi = max(t0a, t0b), min(t1a, t1b)
    if lo >= hi:
        return False
    left_lo = _position_on_segment(t0a, p0a, t1a, p1a, lo)
    right_lo = _position_on_segment(t0b, p0b, t1b, p1b, lo)
    left_hi = _position_on_segment(t0a, p0a, t1a, p1a, hi)
    right_hi = _position_on_segment(t0b, p0b, t1b, p1b, hi)
    tol = 1e-6
    return (left_lo + margin > right_lo + tol) or (left_hi + margin > right_hi + tol)


def _crossing_and_overlap_violations(instance, tasks):
    """Kern von `check_feasible` OHNE die Vollständigkeits-Prüfung (jede Bay genau einmal) -
    eigenständig nutzbar, um auch ein UNVOLLSTÄNDIGES Zwischenergebnis auf Sicherheit zu prüfen.
    Dient hauptsächlich als von der Konstruktion unabhängige Prüfinstanz für Tests und den
    CP-SAT-Cross-Check; `build_schedule` selbst verifiziert inzwischen inkrementell (siehe
    dessen Docstring) und braucht diese Funktion nicht mehr als Sicherheitsnetz."""
    violations = []
    by_crane = defaultdict(list)
    for t in tasks.values():
        by_crane[t.crane].append(t)

    for crane, ts in by_crane.items():
        for a in ts:
            for b in ts:
                if a.bay != b.bay and _intervals_overlap(a.start, a.end, b.start, b.end):
                    violations.append(f"Kran {crane}: Überlappung Bay {a.bay}/{b.bay}.")

    cranes = sorted(by_crane.keys())
    segments_by_crane = defaultdict(list)
    for seg in crane_position_segments(instance, tasks):
        segments_by_crane[seg[0]].append(seg)

    for pi in range(len(cranes)):
        for qi in range(pi + 1, len(cranes)):
            p, q = cranes[pi], cranes[qi]
            for seg_p in segments_by_crane[p]:
                for seg_q in segments_by_crane[q]:
                    if _segments_violate_margin(seg_p, seg_q, instance.safety_margin):
                        violations.append(
                            f"Non-Crossing verletzt (Fahrt/Warten eingeschlossen): Kran {p} "
                            f"(t={seg_p[1]:.1f}-{seg_p[3]:.1f}, Pos {seg_p[2]:.1f}->{seg_p[4]:.1f}) "
                            f"vs. Kran {q} (t={seg_q[1]:.1f}-{seg_q[3]:.1f}, "
                            f"Pos {seg_q[2]:.1f}->{seg_q[4]:.1f})."
                        )
    return violations


def check_feasible(instance, tasks):
    violations = []
    if set(tasks.keys()) != set(range(instance.n_bays)):
        violations.append("Nicht jede Bay genau einmal abgedeckt.")
    violations.extend(_crossing_and_overlap_violations(instance, tasks))
    return len(violations) == 0, violations


def evaluate(instance, tasks, label=""):
    makespan = max((t.end for t in tasks.values()), default=0.0)
    by_crane = defaultdict(list)
    for t in tasks.values():
        by_crane[t.crane].append(t)

    crane_stats = {}
    total_travel = 0.0
    total_wait = 0.0
    for c in range(instance.n_cranes):
        ts = sorted(by_crane.get(c, []), key=lambda t: t.start)
        busy = sum(t.end - t.start for t in ts)
        wait = sum(t.wait for t in ts)
        finish = ts[-1].end if ts else 0.0
        travel = 0.0
        pos = instance.crane_start_positions[c]
        for t in ts:
            travel += instance.travel_time(pos, t.bay)
            pos = t.bay
        idle_after = makespan - finish
        crane_stats[c] = {
            "n_bays": len(ts),
            "busy_time": busy,
            "travel_time": travel,
            "wait_time": wait,
            "finish_time": finish,
            "idle_after": idle_after,
        }
        total_travel += travel
        total_wait += wait

    loads = [crane_stats[c]["busy_time"] for c in range(instance.n_cranes)]
    imbalance = (max(loads) - min(loads)) if loads else 0.0

    return {
        "label": label,
        "tasks": tasks,
        "makespan": makespan,
        "crane_stats": crane_stats,
        "total_travel_time": total_travel,
        "total_wait_time": total_wait,
        "load_imbalance": imbalance,
    }


def finalize_tasks(instance, raw):
    """raw: dict bay -> (crane, start, end), z.B. aus dem CP-SAT-Löser. Ergänzt je Kran anhand
    der chronologischen Reihenfolge die `wait`-Kennzahl (Wartezeit durch Interferenz) - dieselbe
    Definition wie in build_schedule, nur nachträglich statt während der Konstruktion."""
    by_crane = defaultdict(list)
    for bay, (crane, start, end) in raw.items():
        by_crane[crane].append((bay, start, end))

    tasks = {}
    for crane, items in by_crane.items():
        items.sort(key=lambda x: x[1])
        pos = instance.crane_start_positions[crane]
        t = 0.0
        for bay, start, end in items:
            unconstrained = t + instance.travel_time(pos, bay)
            tasks[bay] = Task(bay=bay, crane=crane, start=start, end=end, wait=max(0.0, start - unconstrained))
            pos, t = bay, end
    return tasks


def comparison_table(results):
    """Werte bleiben echte Floats (nicht als String formatiert) - Streamlit bekommt über
    `COMPARISON_TABLE_COLUMN_CONFIG` (app.py) explizit gesagt, mit fest einer Nachkommastelle
    zu rendern. Eigener Fund: eine frühere Fassung formatierte hier selbst als String
    (`f"{x:.1f}"`), aber Streamlits Dataframe-Renderer erkennt zahlenartige Strings und
    formatiert sie NOCHMAL selbst - dabei fällt bei einem GLATTEN Wert (z.B. 107.0) die ".0"
    wieder weg, bei einem echten Bruchwert (z.B. 112.5) nicht. In derselben Spalte standen
    dadurch mal "107", mal "112.5" nebeneinander - uneinheitlich und verwirrend, obwohl beides
    dieselbe Metrik mit derselben Rundung ist. Erst `column_config.NumberColumn(format="%.1f")`
    erzwingt zuverlässig dieselbe Anzahl Nachkommastellen wie die App-Kacheln
    (`app.py`/`quaycrane_ui_panel.py`) und der PDF-Export."""
    import pandas as pd

    rows = []
    for r in results:
        rows.append(
            {
                "Methode": r["label"],
                "Liegezeit (min)": r["makespan"],
                "Wartezeit durch Interferenz (min)": r["total_wait_time"],
                "Fahrzeit gesamt (min)": r["total_travel_time"],
                "Lastungleichgewicht (min)": r["load_imbalance"],
            }
        )
    return pd.DataFrame(rows)

"""Schedule-Konstruktion aus einer Einfüge-Reihenfolge, Machbarkeitsprüfung und Kennzahlen.

Eine Lösung wird als `order` repräsentiert: eine Liste von (bay, crane)-Paaren in der
Reihenfolge, in der sie einem Kran zugewiesen werden. Diese Reihenfolge legt sowohl die
Kranzuordnung als auch - je Kran - die Bearbeitungsreihenfolge fest (Teilfolge der `order`,
eingeschränkt auf diesen Kran). `build_schedule` baut daraus einen konkreten Zeitplan, der per
Konstruktion IMMER machbar ist: jede Aufgabe startet frühestens, wenn ihr Kran frei ist (inkl.
Fahrzeit von der letzten Position), und wird zusätzlich so weit nach hinten geschoben, bis kein
bereits eingeplanter Kran verletzt wird (Non-Crossing-Regel)."""

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    bay: int
    crane: int
    start: float
    end: float
    wait: float  # durch Kran-Interferenz verursachte zusätzliche Wartezeit (>= 0)


def _intervals_overlap(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def earliest_feasible_start(instance, tasks_so_far, crane, bay, min_start):
    """Frühester Start >= min_start für `crane` an `bay`, ohne eine bereits eingeplante
    Aufgabe eines anderen Krans zeitlich-räumlich zu verletzen (Non-Crossing).

    Deckt nur die Aufgabe SELBST ab (Kran steht bei `bay` während [start,end]), nicht die
    Fahrt/Wartephase davor - siehe README ("bekannte Einschränkung: Non-Crossing während sehr
    langer Wartezeit"). Ein Versuch, die Wartephase per erweitertem Push-Fenster ebenfalls
    abzudecken, erwies sich als nicht konvergent: das Wartefenster wächst mit jedem Push
    selbst, sodass ein einmal erkannter Konflikt sich nicht durch Vorschieben auflösen lässt
    (anders als bei der Aufgabe selbst, wo `start = t.end` das Fenster garantiert über den
    Konflikt hinausschiebt). Der exakte CP-SAT-Löser braucht dieses Problem nicht auf dieselbe
    Art zu lösen und ist davon nicht betroffen (siehe quaycrane_cp_solver.py)."""
    duration = instance.bays[bay].duration
    start = min_start
    changed = True
    while changed:
        changed = False
        end = start + duration
        for t in tasks_so_far.values():
            if t.crane == crane:
                continue
            if not _intervals_overlap(start, end, t.start, t.end):
                continue
            if crane < t.crane:
                ok = bay + instance.safety_margin <= t.bay
            else:
                ok = t.bay + instance.safety_margin <= bay
            if not ok:
                start = t.end
                changed = True
                break
    return start


def build_schedule(instance, order):
    tasks = {}
    crane_last_end = {c: 0.0 for c in range(instance.n_cranes)}
    crane_last_pos = {c: instance.crane_start_positions[c] for c in range(instance.n_cranes)}
    for bay, crane in order:
        unconstrained_start = crane_last_end[crane] + instance.travel_time(crane_last_pos[crane], bay)
        start = earliest_feasible_start(instance, tasks, crane, bay, unconstrained_start)
        end = start + instance.bays[bay].duration
        tasks[bay] = Task(bay=bay, crane=crane, start=start, end=end, wait=start - unconstrained_start)
        crane_last_end[crane] = end
        crane_last_pos[crane] = bay
    return tasks


def crane_position_segments(instance, tasks):
    """Liefert je Kran eine Liste von Segmenten (crane, t0, pos0, t1, pos1, kind), kind in
    {"wait", "travel", "work"}: abwechselnd Warten am Ursprung (Position konstant), Fahrt
    (Position ändert sich linear) und Bearbeitung (Position konstant). Konvention: der Kran
    bleibt so lange wie möglich an seiner letzten Position stehen und fährt erst im
    letztmöglichen Moment los, sodass er genau zum Aufgabenbeginn ankommt - nicht "sofort
    losfahren, dann am Ziel warten". Das ist die physikalisch naheliegendere Wahl (ein Kran hat
    keinen Grund, sich einer noch unklaren Zielposition anzunähern, solange er nicht losmuss)
    und vermeidet unnötige Non-Crossing-Verletzungen, die die andere Konvention bei langer
    Wartezeit erzeugen kann, wenn die Zielposition währenddessen zeitweise zu nah an einem
    Nachbarkran liegt (Fund vom 2026-09-04: ohne diese Fahrsegmente überhaupt zu prüfen fehlte
    die ursprüngliche, rein aufgabenbasierte Prüfung unten Non-Crossing-Verletzungen während
    einer Fahrt komplett - diese Konvention behebt zusätzlich einen Folgefund, dass die
    naheliegendste Konvention ("sofort losfahren") bei sehr langer Wartezeit selbst wieder
    Verletzungen erzeugen kann). Wird sowohl von check_feasible als auch vom Trajektorien-Chart
    genutzt, damit Prüfung und Darstellung nie auseinanderlaufen."""
    by_crane = defaultdict(list)
    for t in tasks.values():
        by_crane[t.crane].append(t)

    segments = []
    for crane, ts in by_crane.items():
        ts = sorted(ts, key=lambda t: t.start)
        prev_t, prev_pos = 0.0, instance.crane_start_positions[crane]
        for t in ts:
            travel_time = instance.travel_time(prev_pos, t.bay)
            departure = t.start - travel_time
            if departure > prev_t + 1e-9:
                segments.append((crane, prev_t, prev_pos, departure, prev_pos, "wait"))
            departure = max(departure, prev_t)
            if t.bay != prev_pos:
                segments.append((crane, departure, prev_pos, t.start, t.bay, "travel"))
            segments.append((crane, t.start, t.bay, t.end, t.bay, "work"))
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


def check_feasible(instance, tasks):
    violations = []
    if set(tasks.keys()) != set(range(instance.n_bays)):
        violations.append("Nicht jede Bay genau einmal abgedeckt.")

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
    import pandas as pd

    rows = []
    for r in results:
        rows.append(
            {
                "Methode": r["label"],
                "Liegezeit (min)": round(r["makespan"], 1),
                "Wartezeit durch Interferenz (min)": round(r["total_wait_time"], 1),
                "Fahrzeit gesamt (min)": round(r["total_travel_time"], 1),
                "Lastungleichgewicht (min)": round(r["load_imbalance"], 1),
            }
        )
    return pd.DataFrame(rows)

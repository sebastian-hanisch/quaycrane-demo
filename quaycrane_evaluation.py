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
    Aufgabe eines anderen Krans zeitlich-räumlich zu verletzen (Non-Crossing)."""
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
    for pi in range(len(cranes)):
        for qi in range(pi + 1, len(cranes)):
            p, q = cranes[pi], cranes[qi]
            for tp in by_crane[p]:
                for tq in by_crane[q]:
                    if _intervals_overlap(tp.start, tp.end, tq.start, tq.end):
                        if tp.bay + instance.safety_margin > tq.bay:
                            violations.append(
                                f"Non-Crossing verletzt: Kran {p}@Bay{tp.bay} vs. Kran {q}@Bay{tq.bay}."
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

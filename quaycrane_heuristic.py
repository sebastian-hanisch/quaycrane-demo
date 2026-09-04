"""Drei selbst gebaute Verfahren, alle auf derselben `order`-Repräsentation (Liste von
(bay, crane)-Paaren in Einfüge-Reihenfolge, siehe quaycrane_evaluation.build_schedule):

- naive_construction: gleichmäßige, rein positionale Aufteilung ohne Rücksicht auf Arbeitslast.
- greedy_construction: LPT-Listenscheduling - schwerste Bays zuerst, jede an den Kran mit
  frühestmöglicher Fertigstellung (inkl. Fahrzeit und Non-Crossing-Wartezeit).
- greedy_and_polish: die bessere von zwei Greedy-Startlösungen (LPT- und Positions-Reihenfolge),
  anschließend lokale Suche (Kran-Tausch und Kran-Verlagerung einzelner Bays)."""

import random

from quaycrane_evaluation import Task, build_schedule, earliest_feasible_start


def naive_construction(instance):
    """Gleichmäßige, zusammenhängende Aufteilung nach Bay-Index - ignoriert Arbeitslast pro
    Bay komplett. Dient als naiver Vergleichspunkt: so würde man ohne Optimierung planen."""
    order = []
    base, rem = divmod(instance.n_bays, instance.n_cranes)
    idx = 0
    for c in range(instance.n_cranes):
        count = base + (1 if c < rem else 0)
        for _ in range(count):
            order.append((idx, c))
            idx += 1
    return order


def balanced_zone_construction(instance):
    """Kontinuierliche, lastbalancierte Aufteilung: das Schiff wird per dynamischer Programmierung
    (klassisches "minimiere die größte Teilsumme"-Problem) in `n_cranes` zusammenhängende Zonen
    geschnitten, sodass die größte Zonenarbeitslast minimal ist. Zonen berühren sich nur an der
    Grenze - anders als bei frei über das ganze Schiff verteilten Zuordnungen bleibt
    Kran-Interferenz dadurch fast immer aus."""
    n, k = instance.n_bays, instance.n_cranes
    prefix = [0.0] * (n + 1)
    for i, bay in enumerate(instance.bays):
        prefix[i + 1] = prefix[i] + bay.duration

    inf = float("inf")
    dp = [[inf] * (n + 1) for _ in range(k + 1)]
    parent = [[0] * (n + 1) for _ in range(k + 1)]
    dp[0][0] = 0.0
    for c in range(1, k + 1):
        for i in range(c, n + 1):
            for j in range(c - 1, i):
                val = max(dp[c - 1][j], prefix[i] - prefix[j])
                if val < dp[c][i]:
                    dp[c][i] = val
                    parent[c][i] = j

    bounds = []
    i, c = n, k
    while c > 0:
        j = parent[c][i]
        bounds.append((j, i))
        i, c = j, c - 1
    bounds.reverse()

    order = []
    for crane, (lo, hi) in enumerate(bounds):
        for bay in range(lo, hi):
            order.append((bay, crane))
    return order


def _greedy_order(instance, bay_sequence):
    tasks = {}
    crane_last_end = {c: 0.0 for c in range(instance.n_cranes)}
    crane_last_pos = {c: instance.crane_start_positions[c] for c in range(instance.n_cranes)}
    order = []
    for bay in bay_sequence:
        best_crane, best_start, best_end = None, None, None
        for c in range(instance.n_cranes):
            unconstrained = crane_last_end[c] + instance.travel_time(crane_last_pos[c], bay)
            start = earliest_feasible_start(instance, tasks, c, bay, unconstrained)
            end = start + instance.bays[bay].duration
            if best_end is None or end < best_end:
                best_crane, best_start, best_end = c, start, end
        tasks[bay] = Task(
            bay=bay,
            crane=best_crane,
            start=best_start,
            end=best_end,
            wait=best_start - (crane_last_end[best_crane] + instance.travel_time(crane_last_pos[best_crane], bay)),
        )
        crane_last_end[best_crane] = best_end
        crane_last_pos[best_crane] = bay
        order.append((bay, best_crane))
    return order


def greedy_construction(instance, priority="lpt"):
    if priority == "lpt":
        bay_sequence = sorted(range(instance.n_bays), key=lambda i: -instance.bays[i].duration)
    else:  # "spatial": Bays in Schiffsreihenfolge, Kranwahl bleibt trotzdem adaptiv
        bay_sequence = list(range(instance.n_bays))
    return _greedy_order(instance, bay_sequence)


def _makespan_of(instance, order):
    tasks = build_schedule(instance, order)
    return max((t.end for t in tasks.values()), default=0.0)


def local_search(instance, order, rng=None, max_moves=400):
    """Hill-Climbing mit zwei Zugtypen: Kran-Tausch (zwei Bays tauschen ihre Kranzuordnung) und
    Kran-Verlagerung (eine Bay bekommt einen anderen Kran). Akzeptiert nur echte Verbesserungen,
    endet bei Konvergenz oder erschöpftem Zugbudget - nie schlechter als der Startpunkt."""
    rng = rng or random.Random(0)
    best_order = list(order)
    best_makespan = _makespan_of(instance, best_order)
    moves_used = 0
    improved = True

    while improved and moves_used < max_moves:
        improved = False
        n = len(best_order)

        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        rng.shuffle(pairs)
        for i, j in pairs:
            if moves_used >= max_moves:
                break
            moves_used += 1
            bay_i, crane_i = best_order[i]
            bay_j, crane_j = best_order[j]
            if crane_i == crane_j:
                continue
            candidate = list(best_order)
            candidate[i], candidate[j] = (bay_i, crane_j), (bay_j, crane_i)
            ms = _makespan_of(instance, candidate)
            if ms < best_makespan - 1e-9:
                best_order, best_makespan, improved = candidate, ms, True

        if moves_used >= max_moves:
            break

        relocations = [(i, c) for i in range(n) for c in range(instance.n_cranes)]
        rng.shuffle(relocations)
        for i, c in relocations:
            if moves_used >= max_moves:
                break
            moves_used += 1
            bay_i, crane_i = best_order[i]
            if crane_i == c:
                continue
            candidate = list(best_order)
            candidate[i] = (bay_i, c)
            ms = _makespan_of(instance, candidate)
            if ms < best_makespan - 1e-9:
                best_order, best_makespan, improved = candidate, ms, True

    return best_order


def greedy_and_polish(instance, seed=0, max_moves=400):
    rng = random.Random(seed)
    candidates = [
        balanced_zone_construction(instance),
        greedy_construction(instance, "lpt"),
        greedy_construction(instance, "spatial"),
    ]
    start_order = min(candidates, key=lambda o: _makespan_of(instance, o))
    return local_search(instance, start_order, rng, max_moves=max_moves)

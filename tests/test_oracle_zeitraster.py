"""Orakel auf anderem Rechenweg: exakte Suche im Zeitraster statt CP-SAT.

Rasterschritt dt = Fahrzeit je Bay / 2: ein Kran fährt genau einen halben Bay je Schritt, Positionen sind ganze Halb-Bays. Jeder Kran wartet, fährt (immer mit voller Geschwindigkeit bis zum
Ziel), wartet am Ziel oder bearbeitet eine Bay; der Sicherheitsabstand wird in jedem Schritt für alle Kranpaare geprüft (die Differenz zweier Positionen ist zwischen zwei Rasterpunkten linear,
die Enden genügen). Breitensuche über (Krane, begonnene Bays, fertige Bays): die erste Schicht mit allen Bays fertig ist die kleinste Liegezeit. Kräne ohne Aufgabe verschwinden (wie im Modell).
Alle Zeiten der Testinstanzen sind Vielfache von dt, dann liegt das stetige Optimum auf dem Raster."""
import itertools
import random

import pytest

import quaycrane_scenario as SC
from quaycrane_cp_solver import solve_exact
from quaycrane_evaluation import ScheduleInfeasibleError, build_schedule, check_feasible
from quaycrane_heuristic import balanced_zone_construction, greedy_and_polish, naive_construction


def grid_optimum(inst):
    n, k = inst.n_bays, inst.n_cranes
    dt = inst.travel_time_per_bay / 2
    dur = [round(b.duration / dt) for b in inst.bays]
    start_pos = [round(2 * p) for p in inst.crane_start_positions]
    m2 = 2 * inst.safety_margin
    full = (1 << n) - 1

    def position(s):
        if s[0] in ("I", "T"):
            return s[1]
        return 2 * s[1] if s[0] in ("W", "K") else None

    def spaced(cranes):
        last = None
        for s in cranes:
            p = position(s)
            if p is None:
                continue
            if last is not None and last + m2 > p:
                return False
            last = p
        return True

    def crane_options(s, claimed):
        kind = s[0]
        if kind == "X":
            return [(s, 0, 0)]
        if kind == "K":
            rest = s[2] - 1
            return [(("K", s[1], rest), 0, 0)] if rest else [(("I", 2 * s[1]), 0, 1 << s[1])]
        if kind == "W":
            b = s[1]
            rest = dur[b] - 1
            return [(s, 0, 0), (("K", b, rest), 0, 0) if rest else (("I", 2 * b), 0, 1 << b)]
        if kind == "T":
            b = s[2]
            p = s[1] + (1 if 2 * b > s[1] else -1)
            if p == 2 * b:
                return [(("K", b, dur[b]), 0, 0), (("W", b), 0, 0)]
            return [(("T", p, b), 0, 0)]
        p = s[1]
        out = [(s, 0, 0), (("X",), 0, 0)]
        for b in range(n):
            if claimed >> b & 1:
                continue
            if p == 2 * b:
                rest = dur[b] - 1
                out.append((("K", b, rest), 1 << b, 0) if rest else (("I", p), 1 << b, 1 << b))
            else:
                q = p + (1 if 2 * b > p else -1)
                if q == 2 * b:
                    out += [(("K", b, dur[b]), 1 << b, 0), (("W", b), 1 << b, 0)]       # angekommen: sofort bearbeiten oder am Ziel warten
                else:
                    out.append((("T", q, b), 1 << b, 0))
        return out

    layer = []
    for used in range(1, 1 << k):
        cranes = tuple(("I", start_pos[c]) if used >> c & 1 else ("X",) for c in range(k))
        if spaced(cranes):
            layer.append((cranes, 0, 0))
    seen, t = set(layer), 0
    while layer:
        if any(done == full for _, _, done in layer):
            return t * dt
        nxt = []
        for cranes, claimed, done in layer:
            for combo in itertools.product(*(crane_options(s, claimed) for s in cranes)):
                c2, d2, ok = claimed, done, True
                for _, claim, fin in combo:
                    if claim & c2:
                        ok = False
                        break
                    c2 |= claim
                    d2 |= fin
                new = tuple(s for s, _, _ in combo)
                if ok and spaced(new) and (new, c2, d2) not in seen:
                    seen.add((new, c2, d2))
                    nxt.append((new, c2, d2))
        layer, t = nxt, t + 1
    return None


def tiny(seed):
    rng = random.Random(seed)
    k = rng.choice([1, 2, 2, 3])
    n = rng.choice([3, 4, 5]) if k == 1 else k * 2
    return SC.generate_instance(n, k, rng.choice([2, 3]), 0.6, rng.choice([0.5, 1.0, 1.5]), 1.0, rng.choice([0, 1, 2]), rng.randint(0, 10**6))


def test_hand_example_for_the_grid_search():
    # ein Kran (Startposition 1.0 bei zwei Bays), zwei Bays zu je 2 min, Fahrzeit 1 min je Bay: erst zu Bay 1 (1 min), 2 min, zu Bay 0 (1 min), 2 min = 6 min
    inst = SC.Instance(n_bays=2, n_cranes=1, bays=(SC.Bay(0, 2, 2.0), SC.Bay(1, 2, 2.0)), time_per_move=1.0, travel_time_per_bay=1.0, safety_margin=0, crane_start_positions=(1.0,))
    assert grid_optimum(inst) == pytest.approx(5.0) and solve_exact(inst, 5).makespan == pytest.approx(5.0)     # Start auf Bay 1 (Position 1.0): 2 + 1 + 2


@pytest.mark.parametrize("seed", range(9))
def test_exact_makespan_equals_the_grid_optimum_and_no_heuristic_beats_it(seed):
    inst = tiny(seed)
    if inst.is_trivially_infeasible():
        pytest.skip("Szenario unlösbar")
    best = grid_optimum(inst)
    res = solve_exact(inst, 20)
    assert res.optimal and res.makespan == pytest.approx(best, abs=1e-6)
    for order in (naive_construction(inst), balanced_zone_construction(inst), greedy_and_polish(inst)):
        try:
            tasks = build_schedule(inst, order)
        except ScheduleInfeasibleError:
            continue
        assert check_feasible(inst, tasks)[0]
        assert max(t.end for t in tasks.values()) >= best - 1e-6

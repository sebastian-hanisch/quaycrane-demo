"""Belegt die Messwerte der README (Fund LPT, Presets, Wartezeit, Extremfall). Alle Instanzen deterministisch (feste Zufalls-Seeds),
Standardwerte sonst: 14 Moves +- 40 %, 2,0 min je Move, 0,5 min je Bay Fahrzeit. Nur Heuristiken und kleine exakte Läufe, keine Zeitassertionen."""

import statistics as st

import pytest

import quaycrane_constants as C
import quaycrane_scenario as SC
from quaycrane_cp_solver import solve_exact
from quaycrane_evaluation import ScheduleInfeasibleError, build_schedule, check_feasible, evaluate
from quaycrane_heuristic import balanced_zone_construction, greedy_and_polish, greedy_construction, naive_construction

DEF = dict(moves_avg=C.MOVES_AVG_DEFAULT, moves_variability=C.MOVES_VARIABILITY_DEFAULT, time_per_move=C.TIME_PER_MOVE_DEFAULT, travel_time_per_bay=C.TRAVEL_TIME_PER_BAY_DEFAULT)


def _eval(inst, order):
    """(Liegezeit, Wartezeit) oder None, wenn `build_schedule` die Zuordnung ablehnt."""
    try:
        tasks = build_schedule(inst, order)
    except ScheduleInfeasibleError:
        return None
    assert check_feasible(inst, tasks)[0]
    e = evaluate(inst, tasks)
    return e["makespan"], e["total_wait_time"]


def _preset(name):
    return SC.generate_instance(**C.PRESETS[name])


@pytest.mark.parametrize(
    "name, naive, zone, polish",
    [
        ("Kleines Feederschiff", 102.5, 102.5, 101.5),
        ("Mittleres Schiff, Normalbetrieb", 112.5, 112.5, 107.0),
        ("Großes Schiff, viele Kräne", 150.5, 150.5, 145.0),
        ("Enge Sicherheitsabstände", 116.85, 112.85, 110.05),
    ],
)
def test_preset_heuristic_makespans(name, naive, zone, polish):
    inst = _preset(name)
    assert _eval(inst, naive_construction(inst))[0] == pytest.approx(naive, abs=0.01)
    assert _eval(inst, balanced_zone_construction(inst))[0] == pytest.approx(zone, abs=0.01)
    assert _eval(inst, greedy_and_polish(inst))[0] == pytest.approx(polish, abs=0.01)


def test_lpt_loses_to_naive_on_the_feeder_preset():
    """Kleines Feederschiff: LPT 105,5 min mit 2,0 min Wartezeit gegen naive 102,5 min ohne Wartezeit."""
    inst = _preset("Kleines Feederschiff")
    lpt, naive = _eval(inst, greedy_construction(inst, "lpt")), _eval(inst, naive_construction(inst))
    assert lpt[0] == pytest.approx(105.5, abs=0.01) and lpt[1] == pytest.approx(2.0, abs=0.01)
    assert naive[0] == pytest.approx(102.5, abs=0.01) and naive[1] == 0.0


def test_lpt_assignment_is_mostly_rejected_by_build_schedule():
    """240 Instanzen (Bays 8/10/12/16 x Kräne 2/3/4 x Zufalls-Seeds 0-19), Sicherheitsabstand 1: LPT 220 abgelehnt (92 %), die naive
    Aufteilung nie; wo beide zulässig sind (20), ist LPT in 12 länger, in 8 kürzer, im Mittel 4,3 % länger, mit Wartezeit 12,5 gegen 0,0 min."""
    total = rejected = naive_rejected = worse = better = 0
    ratios, waits = [], []
    for nb in (8, 10, 12, 16):
        for nc in (2, 3, 4):
            for seed in range(20):
                inst = SC.generate_instance(n_bays=nb, n_cranes=nc, safety_margin=1, seed=seed, **DEF)
                if inst.is_trivially_infeasible():
                    continue
                total += 1
                lpt, naive = _eval(inst, greedy_construction(inst, "lpt")), _eval(inst, naive_construction(inst))
                rejected += lpt is None
                naive_rejected += naive is None
                if lpt is not None and naive is not None:
                    ratios.append(lpt[0] / naive[0])
                    waits.append(lpt[1])
                    worse += lpt[0] > naive[0] + 1e-9
                    better += lpt[0] < naive[0] - 1e-9
    assert (total, rejected, naive_rejected, len(ratios), worse, better) == (240, 220, 0, 20, 12, 8)
    assert st.mean(ratios) == pytest.approx(1.043, abs=0.001) and st.mean(waits) == pytest.approx(12.5, abs=0.05)


def test_exact_matches_readme_on_small_presets():
    """Kleines Feederschiff 101,0 min, Mittleres Schiff 106,0 min (je beweisbar optimal); Mittleres Schiff ohne Wartezeit."""
    for name, expected in (("Kleines Feederschiff", 101.0), ("Mittleres Schiff, Normalbetrieb", 106.0)):
        inst = _preset(name)
        r = solve_exact(inst, time_limit_seconds=30)
        assert r.optimal and r.makespan == pytest.approx(expected, abs=0.01)
        assert evaluate(inst, r.tasks)["total_wait_time"] == pytest.approx(0.0, abs=1e-6)


def test_extreme_case_all_three_heuristics_feasible():
    """18 Bays, 5 Kräne, Abstand 3 (Regler-Maximum), 12 Moves, Seed 5: naive 114,4 min (Wartezeit 4,3), Zonenbalance und lokale Suche je 99,0 min (Wartezeit 10,3)."""
    inst = SC.generate_instance(n_bays=18, n_cranes=5, moves_avg=12, moves_variability=0.4, time_per_move=2.0, travel_time_per_bay=0.5, safety_margin=3, seed=5)
    got = [_eval(inst, f(inst)) for f in (naive_construction, balanced_zone_construction, greedy_and_polish)]
    assert [round(g[0], 1) for g in got] == [114.4, 99.0, 99.0] and [round(g[1], 1) for g in got] == [4.3, 10.3, 10.3]

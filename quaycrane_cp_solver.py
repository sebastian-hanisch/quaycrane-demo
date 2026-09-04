"""Exakter Referenzlöser (Google OR-Tools CP-SAT) für das Quay-Crane-Scheduling-Problem.

Modell: jede Bay wird genau einem Kran zugewiesen (x[i][c]) und bekommt Start-/Endzeit
(start[i]/end[i], Dauer fix). Zwei Arten paarweiser Constraints zwischen je zwei Bays i<j
(Bay-Index == Position auf der Schiffsseite):

- Gleicher Kran: die beiden Aufgaben dürfen sich zeitlich nicht überlappen und brauchen
  zusätzlich die Fahrzeit zwischen den Bays als Rüstzeit dazwischen (Sequencing mit
  sequenzabhängigen Rüstzeiten, klassisch über Reihenfolge-Bools "i vor j" / "j vor i").
- Unterschiedliche Kräne: Non-Crossing (Kim & Park 2004). Da die Kranreihenfolge auf der
  Schiene fix ist (Kranindex == physische Position), unterscheiden wir zwei Fälle: die
  Zuordnung ist "konsistent" (linkere Bay bekommt einen Kran mit kleinerem oder gleichem
  Index) - dann reicht bei zeitlicher Übrschneidung schon der Sicherheitsabstand in Bays;
  oder "gekreuzt" (linkere Bay bekommt den Kran mit dem größeren Index) - das ist eine
  physische Unmöglichkeit und wird bei zeitlicher Überschneidung komplett verboten.
- Fahrt zwischen zwei UNMITTELBAR aufeinanderfolgenden Aufgaben desselben Krans (kein
  drittes Bay desselben Krans dazwischen): der Kran durchquert dabei zwangsläufig jede Bay
  zwischen den beiden Positionen. Ohne eigene Constraint dafür stimmt das Modell zwar bei
  reiner Aufgaben-Bearbeitung, kann eine Fahrt aber ungehindert durch einen Bereich führen,
  in dem gerade ein anderer Kran bearbeitet - siehe Docstring-Abschnitt weiter unten
  ("Fund: Fahrt-Überschneidung").

Minimiert wird primär der Makespan (= Schiffsliegezeit); als lexikografisches
Tie-Breaking-Ziel zusätzlich die Summe aller Endzeiten. Ohne dieses zweite Ziel ist dem Solver
unter mehreren gleich-optimalen Makespan-Lösungen jede davon gleich lieb - er kann (und tut es
in der Praxis, je nachdem welcher der parallelen Suchpfade zuerst eine optimale Lösung findet)
eine mit unnötiger Wartezeit auf einem unkritischen Kran zurückgeben, obwohl eine
wartezeitfreie Lösung mit demselben Makespan existiert. Das zweite Ziel drückt jede Aufgabe so
früh wie möglich, ohne den Makespan zu verschlechtern, und eliminiert solche Artefakte."""

import math
import os
import time
from dataclasses import dataclass

from ortools.sat.python import cp_model

from quaycrane_evaluation import finalize_tasks

SCALE = 10  # interne Zeitauflösung: 1 CP-SAT-Einheit = 0.1 Minuten

# Eigener Fund: fest auf 8 verdrahtet lief hier lokal gut, ließ aber die CI (GitHub-gehostete
# Runner, nur 2 vCPUs) innerhalb der Zeitlimits nicht mehr fertig werden bzw. nicht mehr
# beweisbar optimal lösen - 8 Suchpfade auf 2 echten Kernen konkurrieren nur noch um Kontext-
# Wechsel, statt zu parallelisieren. `os.cpu_count()` (mit Fallback 1, falls nicht ermittelbar)
# passt das automatisch an die tatsächliche Hardware an, statt eine feste Dev-Maschine anzunehmen.
NUM_SEARCH_WORKERS = min(8, os.cpu_count() or 1)


def _add_travel_non_crossing_constraints(model, instance, n, k, x, start, end, crane_of, pair_same, pair_before, scaled):
    """Fund (2026-09-04, Nutzerhinweis): die reine Aufgaben-vs-Aufgaben-Prüfung oben reicht
    nicht - ein Kran, der unmittelbar von Bay a zu Bay b fährt, durchquert dabei zwangsläufig
    jede Position zwischen a und b, auch wenn dort gerade keine EIGENE Aufgabe liegt. Ohne
    diese Funktion konnte die Fahrt eines Krans ungehindert durch die Position führen, an der
    ein anderer Kran gerade noch arbeitet (reproduziert: fünf Löser-Läufe derselben Instanz,
    Makespan immer optimal, aber eine der Lösungen ließ Kran 2 mitten durch die Position
    fahren, an der Kran 1 gerade Bay 3 bearbeitete).

    Für jedes geordnete Aufgabenpaar (a, b) wird "next_ab" abgeleitet (b folgt unmittelbar auf
    a beim selben Kran - kein drittes Bay desselben Krans zeitlich dazwischen). Ist next_ab
    wahr, belegt der Kran im Fenster [end_a, end_a + Fahrzeit(a,b)] jede Position zwischen a
    und b (worst-case, da das Modell den genauen Abfahrtszeitpunkt innerhalb der Lücke nicht
    festlegt - siehe App-Visualisierung, die stattdessen "sofort losfahren, am Ziel warten"
    als Konvention zeichnet; die Fahrzeit selbst ist ohnehin nicht verkürzbar). Für jede dritte
    Aufgabe k eines ANDEREN Krans mit zeitlicher Übrschneidung wird dann - wie beim
    Aufgaben-vs-Aufgaben-Fall oben - je nach Kranreihenfolge Sicherheitsabstand oder komplettes
    Verbot durchgesetzt."""
    for a in range(n):
        for b in range(n):
            if a == b:
                continue
            same_ab = pair_same[a, b]
            a_before_b = pair_before[a, b]

            not_between = []
            for c in range(n):
                if c == a or c == b:
                    continue
                between_c = model.NewBoolVar(f"between_{a}_{c}_{b}")
                model.AddBoolAnd([pair_same[a, c], pair_before[a, c], pair_before[c, b]]).OnlyEnforceIf(between_c)
                model.AddBoolOr(
                    [pair_same[a, c].Not(), pair_before[a, c].Not(), pair_before[c, b].Not()]
                ).OnlyEnforceIf(between_c.Not())
                not_between.append(between_c.Not())

            next_ab = model.NewBoolVar(f"next_{a}_{b}")
            model.AddBoolAnd([same_ab, a_before_b] + not_between).OnlyEnforceIf(next_ab)
            model.AddBoolOr([same_ab.Not(), a_before_b.Not()] + [nb.Not() for nb in not_between]).OnlyEnforceIf(
                next_ab.Not()
            )

            lo, hi = (a, b) if a < b else (b, a)
            travel_ab = scaled(instance.travel_time(a, b))

            # Konvention (muss zu quaycrane_evaluation.crane_position_segments passen, sonst
            # prüft check_feasible/die Chart ein anderes Fenster als der Solver garantiert -
            # genau das war ein eigener Fund vom 2026-09-04): der Kran bleibt bei `a` stehen und
            # fährt erst im letztmöglichen Moment los, kommt also genau bei start[b] an. Fahrt
            # damit im Fenster [start[b]-travel_ab, start[b]] (Position schwenkt lo..hi), davor
            # im Fenster [end[a], start[b]-travel_ab] fest bei Position `a`.
            for kk in range(n):
                if kk == a or kk == b:
                    continue
                margin_ok_travel_right = (hi + instance.safety_margin) <= kk
                margin_ok_travel_left = (kk + instance.safety_margin) <= lo
                margin_ok_wait_right = (a + instance.safety_margin) <= kk
                margin_ok_wait_left = (kk + instance.safety_margin) <= a

                a_left_of_k = k_left_of_a = None
                if not (margin_ok_travel_right and margin_ok_wait_right):
                    a_left_of_k = model.NewBoolVar(f"alk_{a}_{b}_{kk}")
                    model.Add(crane_of[a] < crane_of[kk]).OnlyEnforceIf(a_left_of_k)
                    model.Add(crane_of[a] >= crane_of[kk]).OnlyEnforceIf(a_left_of_k.Not())
                if not (margin_ok_travel_left and margin_ok_wait_left):
                    k_left_of_a = model.NewBoolVar(f"kla_{a}_{b}_{kk}")
                    model.Add(crane_of[kk] < crane_of[a]).OnlyEnforceIf(k_left_of_a)
                    model.Add(crane_of[kk] >= crane_of[a]).OnlyEnforceIf(k_left_of_a.Not())

                if not margin_ok_travel_right or not margin_ok_travel_left:
                    k_before = model.NewBoolVar(f"kbtr_{a}_{b}_{kk}")
                    after_k = model.NewBoolVar(f"tatr_{a}_{b}_{kk}")
                    model.Add(end[kk] <= start[b] - travel_ab).OnlyEnforceIf(k_before)
                    model.Add(end[kk] > start[b] - travel_ab).OnlyEnforceIf(k_before.Not())
                    model.Add(start[kk] >= start[b]).OnlyEnforceIf(after_k)
                    model.Add(start[kk] < start[b]).OnlyEnforceIf(after_k.Not())
                    disjoint = [k_before, after_k]
                    if not margin_ok_travel_right:
                        model.AddBoolOr(disjoint).OnlyEnforceIf([next_ab, a_left_of_k])
                    if not margin_ok_travel_left:
                        model.AddBoolOr(disjoint).OnlyEnforceIf([next_ab, k_left_of_a])

                if not margin_ok_wait_right or not margin_ok_wait_left:
                    k_before = model.NewBoolVar(f"kbwr_{a}_{b}_{kk}")
                    after_k = model.NewBoolVar(f"tawr_{a}_{b}_{kk}")
                    model.Add(end[kk] <= end[a]).OnlyEnforceIf(k_before)
                    model.Add(end[kk] > end[a]).OnlyEnforceIf(k_before.Not())
                    model.Add(start[kk] >= start[b] - travel_ab).OnlyEnforceIf(after_k)
                    model.Add(start[kk] < start[b] - travel_ab).OnlyEnforceIf(after_k.Not())
                    disjoint = [k_before, after_k]
                    if not margin_ok_wait_right:
                        model.AddBoolOr(disjoint).OnlyEnforceIf([next_ab, a_left_of_k])
                    if not margin_ok_wait_left:
                        model.AddBoolOr(disjoint).OnlyEnforceIf([next_ab, k_left_of_a])

    # Zweiter Fall, anfangs übersehen (derselbe Nutzerhinweis deckte ihn beim "Großes Schiff"-
    # Preset auf): die ALLERERSTE Fahrt eines Krans, von seiner Startposition zu seiner ersten
    # Aufgabe, hat kein vorangehendes "a" - der obige Block deckt sie deshalb nicht ab.
    for b in range(n):
        for crane_id in range(k):
            not_earlier = []
            for a2 in range(n):
                if a2 == b:
                    continue
                earlier = model.NewBoolVar(f"earlier_{a2}_{b}_{crane_id}")
                model.AddBoolAnd([x[a2, crane_id], pair_before[a2, b]]).OnlyEnforceIf(earlier)
                model.AddBoolOr([x[a2, crane_id].Not(), pair_before[a2, b].Not()]).OnlyEnforceIf(earlier.Not())
                not_earlier.append(earlier.Not())

            is_first = model.NewBoolVar(f"first_{b}_{crane_id}")
            model.AddBoolAnd([x[b, crane_id]] + not_earlier).OnlyEnforceIf(is_first)
            model.AddBoolOr([x[b, crane_id].Not()] + [ne.Not() for ne in not_earlier]).OnlyEnforceIf(is_first.Not())

            start_pos = instance.crane_start_positions[crane_id]
            lo, hi = (start_pos, b) if start_pos < b else (b, start_pos)
            travel0 = scaled(instance.travel_time(start_pos, b))

            # Dieselbe Konvention wie oben: der Kran bleibt bis zuletzt bei `start_pos` stehen
            # und fährt erst los, um genau bei start[b] anzukommen - Fahrt im Fenster
            # [start[b]-travel0, start[b]], davor Warten fest bei `start_pos` im Fenster
            # [0, start[b]-travel0].
            for kk in range(n):
                if kk == b:
                    continue
                margin_ok_travel_right = (hi + instance.safety_margin) <= kk
                margin_ok_travel_left = (kk + instance.safety_margin) <= lo
                margin_ok_wait_right = (start_pos + instance.safety_margin) <= kk
                margin_ok_wait_left = (kk + instance.safety_margin) <= start_pos

                crane_lt_k = crane_gt_k = None
                if not (margin_ok_travel_right and margin_ok_wait_right):
                    crane_lt_k = model.NewBoolVar(f"clt_{b}_{crane_id}_{kk}")
                    model.Add(crane_id < crane_of[kk]).OnlyEnforceIf(crane_lt_k)
                    model.Add(crane_id >= crane_of[kk]).OnlyEnforceIf(crane_lt_k.Not())
                if not (margin_ok_travel_left and margin_ok_wait_left):
                    crane_gt_k = model.NewBoolVar(f"cgt_{b}_{crane_id}_{kk}")
                    model.Add(crane_id > crane_of[kk]).OnlyEnforceIf(crane_gt_k)
                    model.Add(crane_id <= crane_of[kk]).OnlyEnforceIf(crane_gt_k.Not())

                if not margin_ok_travel_right or not margin_ok_travel_left:
                    k_after = model.NewBoolVar(f"katr_{b}_{crane_id}_{kk}")
                    model.Add(start[kk] >= start[b]).OnlyEnforceIf(k_after)
                    model.Add(start[kk] < start[b]).OnlyEnforceIf(k_after.Not())
                    # Fahrtfenster endet bei start[b] - "k komplett danach" reicht als
                    # Ausweichmöglichkeit (vorher kann k nicht enden, da es sonst mit dem
                    # Wartefenster [0, start[b]-travel0] kollidieren würde, siehe unten).
                    if not margin_ok_travel_right:
                        model.Add(k_after == 1).OnlyEnforceIf([is_first, crane_lt_k])
                    if not margin_ok_travel_left:
                        model.Add(k_after == 1).OnlyEnforceIf([is_first, crane_gt_k])

                if not margin_ok_wait_right or not margin_ok_wait_left:
                    k_after_wait = model.NewBoolVar(f"kawr_{b}_{crane_id}_{kk}")
                    model.Add(start[kk] >= start[b] - travel0).OnlyEnforceIf(k_after_wait)
                    model.Add(start[kk] < start[b] - travel0).OnlyEnforceIf(k_after_wait.Not())
                    if not margin_ok_wait_right:
                        model.Add(k_after_wait == 1).OnlyEnforceIf([is_first, crane_lt_k])
                    if not margin_ok_wait_left:
                        model.Add(k_after_wait == 1).OnlyEnforceIf([is_first, crane_gt_k])


@dataclass
class ExactResult:
    feasible: bool
    optimal: bool
    tasks: dict
    makespan: float
    wall_time_ms: float


def solve_exact(instance, time_limit_seconds=8, hint_tasks=None):
    """hint_tasks: optionales bereits bekanntes machbares Schedule (z.B. von einer Heuristik,
    Format wie `quaycrane_evaluation.build_schedule`s Rückgabe) - als CP-SAT-Hint übergeben, gibt
    dem Solver sofort einen gültigen Startpunkt statt bei null zu suchen. Wird ab ca. 16+ Bays
    bei 5 Kränen spürbar wichtig: die Non-Crossing-während-Fahrt-Constraints (siehe oben)
    machen selbst das reine FINDEN einer ersten zulässigen Lösung merklich schwerer als vorher
    - ohne Hint fand der Solver für das Preset "Großes Schiff, viele Kräne" (20 Bays, 5 Kräne)
    manchmal innerhalb der 8s-Zeitschranke gar keine gültige Lösung mehr (Status UNKNOWN statt
    FEASIBLE), obwohl vor Einführung dieser Constraints zumindest eine brauchbare, wenn auch
    nicht bewiesen optimale Lösung gefunden wurde. Mit Hint bekommt der Solver diese sofort."""
    t0 = time.perf_counter()
    n, k = instance.n_bays, instance.n_cranes
    model = cp_model.CpModel()

    def scaled(x):
        # Eigener Fund: `round()` rundet auch mal AB (u.a. Bankers Rounding bei exakten .5-
        # Werten, z.B. rundete round(0.25*10)==round(2.5) auf 2 statt 3) - das lässt das
        # SKALIERTE Modell eine Fahrzeit oder Bearbeitungsdauer für einen Sekundenbruchteil KÜRZER
        # annehmen, als sie in der stetigen (unskalierten) Welt tatsächlich ist. Bei sehr engem
        # Sicherheitsabstand reicht genau diese winzige Differenz, damit eine vom Solver als
        # "optimal und zulässig" gemeldete Lösung nach dem Zurückskalieren die (strengere,
        # stetige) `check_feasible`-Prüfung knapp verfehlt. Aufrunden statt runden schließt das
        # aus: das Modell nimmt dann nie eine kürzere Zeit an, als real gebraucht wird - die
        # winzige Konservativität (< 0.1 min) fällt makespan-seitig nicht ins Gewicht.
        return math.ceil(x * SCALE - 1e-6)

    durations = [scaled(b.duration) for b in instance.bays]
    total_work = sum(durations)
    max_travel = scaled(instance.travel_time_per_bay) * max(1, n)
    horizon = total_work + n * max_travel + 1

    x = {(i, c): model.NewBoolVar(f"x_{i}_{c}") for i in range(n) for c in range(k)}
    for i in range(n):
        model.AddExactlyOne(x[i, c] for c in range(k))

    crane_of = [model.NewIntVar(0, k - 1, f"crane_of_{i}") for i in range(n)]
    for i in range(n):
        model.Add(crane_of[i] == sum(c * x[i, c] for c in range(k)))

    start = [model.NewIntVar(0, horizon, f"start_{i}") for i in range(n)]
    end = [model.NewIntVar(0, horizon, f"end_{i}") for i in range(n)]
    for i in range(n):
        model.Add(end[i] == start[i] + durations[i])
        for c in range(k):
            travel0 = scaled(instance.travel_time(instance.crane_start_positions[c], i))
            model.Add(start[i] >= travel0).OnlyEnforceIf(x[i, c])

    pair_same = {}
    pair_before = {}  # pair_before[(a, b)]: BoolVar "a vor b" - fuer JEDE Reihenfolge von a, b abrufbar

    for i in range(n):
        for j in range(i + 1, n):
            i_before_j = model.NewBoolVar(f"ibj_{i}_{j}")
            j_before_i = model.NewBoolVar(f"jbi_{i}_{j}")
            model.Add(end[i] <= start[j]).OnlyEnforceIf(i_before_j)
            model.Add(end[i] > start[j]).OnlyEnforceIf(i_before_j.Not())
            model.Add(end[j] <= start[i]).OnlyEnforceIf(j_before_i)
            model.Add(end[j] > start[i]).OnlyEnforceIf(j_before_i.Not())
            model.Add(i_before_j + j_before_i <= 1)

            same = model.NewBoolVar(f"same_{i}_{j}")
            model.Add(crane_of[i] == crane_of[j]).OnlyEnforceIf(same)
            model.Add(crane_of[i] != crane_of[j]).OnlyEnforceIf(same.Not())
            pair_same[i, j] = pair_same[j, i] = same
            pair_before[i, j] = i_before_j
            pair_before[j, i] = j_before_i

            travel_ij = scaled(instance.travel_time(i, j))
            model.AddBoolOr([i_before_j, j_before_i]).OnlyEnforceIf(same)
            model.Add(end[i] + travel_ij <= start[j]).OnlyEnforceIf([same, i_before_j])
            model.Add(end[j] + travel_ij <= start[i]).OnlyEnforceIf([same, j_before_i])

            if k > 1:
                crossed = model.NewBoolVar(f"crossed_{i}_{j}")
                model.Add(crane_of[i] > crane_of[j]).OnlyEnforceIf(crossed)
                model.Add(crane_of[i] <= crane_of[j]).OnlyEnforceIf(crossed.Not())

                model.AddBoolOr([i_before_j, j_before_i]).OnlyEnforceIf([same.Not(), crossed])

                margin_ok = (i + instance.safety_margin) <= j
                if not margin_ok:
                    model.AddBoolOr([i_before_j, j_before_i]).OnlyEnforceIf([same.Not(), crossed.Not()])

    if k > 1:
        _add_travel_non_crossing_constraints(model, instance, n, k, x, start, end, crane_of, pair_same, pair_before, scaled)

    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, end)

    # Lexikografisches Tie-Breaking: unter allen Lösungen mit optimalem Makespan die mit der
    # kleinsten Summe aller Endzeiten waehlen (siehe Docstring oben). tie_break_weight ist eine
    # sichere obere Schranke fuer die Summe aller Endzeiten (jede einzelne <= horizon, n Aufgaben)
    # plus 1 - so kostet ein einziger Zeitschritt mehr Makespan garantiert mehr, als das
    # Tie-Breaking-Ziel je einsparen koennte, ändert also nie die primäre Optimallösung.
    tie_break_weight = n * horizon + 1
    model.Minimize(makespan * tie_break_weight + sum(end))

    if hint_tasks:
        for i in range(n):
            t = hint_tasks[i]
            for c in range(k):
                model.AddHint(x[i, c], 1 if c == t.crane else 0)
            model.AddHint(crane_of[i], t.crane)
            model.AddHint(start[i], scaled(t.start))
            model.AddHint(end[i], scaled(t.end))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = NUM_SEARCH_WORKERS
    status = solver.Solve(model)
    wall_time_ms = (time.perf_counter() - t0) * 1000

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return ExactResult(feasible=False, optimal=False, tasks={}, makespan=0.0, wall_time_ms=wall_time_ms)

    raw = {}
    for i in range(n):
        c = next(c for c in range(k) if solver.Value(x[i, c]))
        raw[i] = (c, solver.Value(start[i]) / SCALE, solver.Value(end[i]) / SCALE)
    tasks = finalize_tasks(instance, raw)

    return ExactResult(
        feasible=True,
        optimal=status == cp_model.OPTIMAL,
        tasks=tasks,
        makespan=solver.Value(makespan) / SCALE,
        wall_time_ms=wall_time_ms,
    )

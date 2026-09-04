"""Drei selbst gebaute Verfahren, alle auf derselben `order`-Repräsentation (Liste von
(bay, crane)-Paaren in Einfüge-Reihenfolge, siehe quaycrane_evaluation.build_schedule):

- naive_construction: gleichmäßige, rein positionale Aufteilung ohne Rücksicht auf Arbeitslast.
- greedy_construction: LPT-Listenscheduling - schwerste Bays zuerst, jede an den Kran mit
  frühestmöglicher Fertigstellung (inkl. Fahrzeit und Non-Crossing-Wartezeit).
- greedy_and_polish: die bessere von zwei Greedy-Startlösungen (LPT- und Positions-Reihenfolge),
  anschließend lokale Suche (Kran-Tausch und Kran-Verlagerung einzelner Bays)."""

import random

from quaycrane_evaluation import ScheduleInfeasibleError, build_schedule


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
    """LPT-/positionsbasiertes Listenscheduling: jede Bay (in `bay_sequence`) an den Kran mit der
    frühesten GESCHÄTZTEN Fertigstellung, ohne Rücksicht auf Kran-Interferenz - reine, schnelle
    Rangfolge-Heuristik. Die tatsächliche, sichere Zeitplanung (inkl. aller durch Interferenz
    erzwungenen Wartezeiten) baut `build_schedule` später ohnehin von Grund auf und unabhängig
    davon; hier zählt nur, WER welche Bay bekommt, nicht WANN genau."""
    crane_last_end = [0.0] * instance.n_cranes
    crane_last_pos = list(instance.crane_start_positions)
    order = []
    for bay in bay_sequence:
        best_crane = min(
            range(instance.n_cranes),
            key=lambda c: crane_last_end[c] + instance.travel_time(crane_last_pos[c], bay),
        )
        crane_last_end[best_crane] += instance.travel_time(crane_last_pos[best_crane], bay) + instance.bays[bay].duration
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
    """`build_schedule` kann feststellen, dass eine Kranzuordnung strukturell unschedulierbar ist
    (siehe `ScheduleInfeasibleError`-Dokumentation in quaycrane_evaluation.py) - dieselbe
    Kranzuordnung KANN dann für keine Zeitplanung mehr zulässig sein, egal wie konstruiert wird.
    Hier als "unendlich schlecht" behandelt statt den Aufrufer (Kandidatenvergleich in
    `greedy_and_polish`, Züge in `local_search`) abstürzen zu lassen - ein rein lastbasiertes
    Greedy-Verfahren wie LPT kann bei engem Sicherheitsabstand durchaus so eine Zuordnung
    produzieren; sie fällt dann einfach aus der Auswahl heraus, statt die App zu crashen."""
    try:
        tasks = build_schedule(instance, order)
    except ScheduleInfeasibleError:
        return float("inf")
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
    """`balanced_zone_construction`s zusammenhängende Zonenaufteilung ist als einzige der drei
    Kandidaten-Konstruktionen DAFÜR gebaut, Kran-Interferenz durch Konstruktion zu vermeiden
    (siehe deren Docstring) - LPT und positionsbasiertes Greedy können bei engem
    Sicherheitsabstand dagegen eine Kranzuordnung erzeugen, für die überhaupt keine zulässige
    Zeitplanung mehr existiert (siehe `ScheduleInfeasibleError`). `_makespan_of` behandelt das
    bereits als "unendlich schlecht", so dass `min` einen solchen Kandidaten nie wählt UND
    `local_search` einen solchen Zug nie akzeptiert - als letztes Sicherheitsnetz wird das
    Endergebnis hier trotzdem nochmal geprüft: bliebe (in der Praxis nie beobachtet, da
    `balanced_zone_construction` immer als Kandidat dabei ist) dennoch ein unschedulierbares
    Ergebnis übrig, greift explizit die Zonenaufteilung selbst."""
    rng = random.Random(seed)
    candidates = [
        balanced_zone_construction(instance),
        greedy_construction(instance, "lpt"),
        greedy_construction(instance, "spatial"),
    ]
    start_order = min(candidates, key=lambda o: _makespan_of(instance, o))
    polished = local_search(instance, start_order, rng, max_moves=max_moves)
    if _makespan_of(instance, polished) == float("inf"):
        return balanced_zone_construction(instance)
    return polished


def build_schedule_robust(instance, order):
    """Versucht `order` (typischerweise das Ergebnis von `naive_construction` oder
    `balanced_zone_construction` für eine bestimmte Vergleichs-Kachel in der App); schlägt das
    ausnahmsweise fehl (siehe `ScheduleInfeasibleError` - eine rein lastbasierte oder rein
    positionale Konstruktion kann bei engem Sicherheitsabstand eine strukturell
    unschedulierbare Kranzuordnung erzeugen), weicht der Reihe nach auf andere Konstruktionen
    aus, bis eine davon eine zulässige Zeitplanung liefert. `balanced_zone_construction` steht
    dabei bewusst an erster Ausweich-Stelle: ihre zusammenhängenden, lastbalancierten Zonen sind
    strukturell am robustesten gegen genau dieses Problem (siehe deren Docstring).

    Setzt voraus, dass das SZENARIO selbst überhaupt lösbar ist (siehe
    `Instance.is_trivially_infeasible` - das muss VOR jedem Konstruktionsversuch geprüft werden,
    hier wird es nicht wiederholt); ist es das nicht, schlägt zwangsläufig auch dieser Fallback
    am Ende fehl, und die `ScheduleInfeasibleError` wird bewusst durchgereicht - kein
    Konstruktionstrick kann eine Lösung erzwingen, wo keine existiert."""
    for candidate_order in [order, balanced_zone_construction(instance), naive_construction(instance)]:
        try:
            return build_schedule(instance, candidate_order)
        except ScheduleInfeasibleError:
            continue
    raise ScheduleInfeasibleError(
        "Keine der Standard-Konstruktionen liefert für dieses Szenario eine zulässige Zeitplanung."
    )

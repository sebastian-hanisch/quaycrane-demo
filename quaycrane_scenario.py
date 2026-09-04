"""Instanzerzeugung: Schiff mit Bays (Ladeluken) entlang der Kaischiene, Containerbrücken mit
fester Start-Position auf der Schiene."""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Bay:
    index: int
    moves: int
    duration: float  # Minuten, = moves * time_per_move


@dataclass(frozen=True)
class Instance:
    n_bays: int
    n_cranes: int
    bays: tuple
    time_per_move: float
    travel_time_per_bay: float
    safety_margin: int
    crane_start_positions: tuple  # Länge n_cranes, aufsteigend sortiert - Kran 0 ist immer der
    # linkeste, Kran n_cranes-1 der rechteste; diese Reihenfolge ändert sich nie (Kräne
    # hängen an derselben Schiene und können sich nicht überholen)

    def travel_time(self, pos_a, pos_b):
        return abs(pos_a - pos_b) * self.travel_time_per_bay

    def total_workload(self):
        return sum(b.duration for b in self.bays)

    def min_crane_gap(self):
        """Kleinster Abstand zwischen zwei benachbarten Kran-Startpositionen - der Abstand, den
        JEDE zulässige Zeitplanung mindestens einhalten müsste, selbst wenn beide Kräne für
        immer regungslos an ihrer Startposition stehen blieben (ein Aufenthalt zählt für die
        Sicherheitsabstands-Prüfung genauso wie Fahrt oder Bearbeitung, siehe
        `quaycrane_evaluation._segments_violate_margin`). Ist dieser Abstand kleiner als
        `safety_margin`, ist das SZENARIO SELBST unlösbar - unabhängig von jeder noch so
        cleveren Zeitplanung (siehe `is_trivially_infeasible`)."""
        positions = self.crane_start_positions
        if len(positions) < 2:
            return float("inf")
        return min(b - a for a, b in zip(positions, positions[1:]))

    def is_trivially_infeasible(self):
        """True, wenn schon die bloße GLEICHZEITIGE ANWESENHEIT zweier benachbarter Kräne an
        ihren fest vorgegebenen Startpositionen den Sicherheitsabstand verletzt - dann existiert
        für diese Kombination aus Bay-Anzahl, Kranzahl und Sicherheitsabstand KEINE zulässige
        Lösung, auch nicht der exakte Löser (CP-SAT) fände eine. Eigener Fund: die
        Schieberegler-Bereiche der App erlauben Kombinationen (z.B. wenige Bays, viele Kräne,
        maximaler Sicherheitsabstand), bei denen die gleichmäßig verteilten Kran-Startpositionen
        (siehe `generate_instance`) enger beieinander liegen als der geforderte
        Sicherheitsabstand - das muss VOR jedem Konstruktionsversuch erkannt und dem Nutzer
        erklärt werden, statt eine Ausnahme bis zum Absturz durchzureichen."""
        return self.min_crane_gap() < self.safety_margin


def generate_instance(
    n_bays,
    n_cranes,
    moves_avg,
    moves_variability,
    time_per_move,
    travel_time_per_bay,
    safety_margin,
    seed,
):
    rng = random.Random(seed)
    spread = max(1, round(moves_avg * moves_variability))
    lo, hi = max(1, moves_avg - spread), moves_avg + spread
    moves = [rng.randint(lo, hi) for _ in range(n_bays)]
    bays = tuple(Bay(index=i, moves=m, duration=m * time_per_move) for i, m in enumerate(moves))
    # Startpositionen gleichmäßig über die Schiffslänge verteilt (Kräne stehen typischerweise
    # dort, wo sie das vorherige Schiff verlassen hat) - aufsteigend, damit Kranindex ==
    # physische Reihenfolge auf der Schiene bleibt.
    crane_start_positions = tuple(
        (c + 0.5) * n_bays / n_cranes for c in range(n_cranes)
    )
    return Instance(
        n_bays=n_bays,
        n_cranes=n_cranes,
        bays=bays,
        time_per_move=time_per_move,
        travel_time_per_bay=travel_time_per_bay,
        safety_margin=safety_margin,
        crane_start_positions=crane_start_positions,
    )

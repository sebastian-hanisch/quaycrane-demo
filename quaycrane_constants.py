"""Defaults, Regler-Grenzen, Farben und Beispielszenarien."""

N_BAYS_DEFAULT = 12
N_BAYS_RANGE = (6, 24)

N_CRANES_DEFAULT = 3
N_CRANES_RANGE = (1, 5)

MOVES_AVG_DEFAULT = 14
MOVES_AVG_RANGE = (4, 30)

MOVES_VARIABILITY_DEFAULT = 0.4
MOVES_VARIABILITY_RANGE = (0.0, 1.0)

TIME_PER_MOVE_DEFAULT = 2.0
TIME_PER_MOVE_RANGE = (1.0, 4.0)

TRAVEL_TIME_PER_BAY_DEFAULT = 0.5
TRAVEL_TIME_PER_BAY_RANGE = (0.1, 2.0)

SAFETY_MARGIN_DEFAULT = 1
SAFETY_MARGIN_RANGE = (0, 3)

RANDOM_SEED_DEFAULT = 7
RANDOM_SEED_RANGE = (0, 2_000_000_000)

EXACT_SOLVE_TIME_LIMIT_SECONDS = 8  # ab ca. 18-20 Bays / 5 Kränen wird das Modell so groß, dass
# der Löser das Zeitlimit statt eines Optimalitätsbeweises erreicht (siehe README) - die App
# kennzeichnet das dann korrekt als "Zeitlimit erreicht", nicht als bewiesenes Optimum

CRANE_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

PRESETS = {
    "Kleines Feederschiff": dict(
        n_bays=8, n_cranes=2, moves_avg=12, moves_variability=0.3, time_per_move=2.0,
        travel_time_per_bay=0.5, safety_margin=1, seed=3,
    ),
    "Mittleres Schiff, Normalbetrieb": dict(
        n_bays=12, n_cranes=3, moves_avg=14, moves_variability=0.4, time_per_move=2.0,
        travel_time_per_bay=0.5, safety_margin=1, seed=7,
    ),
    "Großes Schiff, viele Kräne": dict(
        n_bays=20, n_cranes=5, moves_avg=16, moves_variability=0.4, time_per_move=2.0,
        travel_time_per_bay=0.5, safety_margin=1, seed=11,
    ),
    "Enge Sicherheitsabstände": dict(
        n_bays=14, n_cranes=4, moves_avg=14, moves_variability=0.3, time_per_move=2.0,
        travel_time_per_bay=0.6, safety_margin=3, seed=5,
    ),
}

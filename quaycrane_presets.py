"""SETTING_SPECS-Permalink-Muster, Presets und Zufalls-Seed-Button (Standardmuster aus dem
OR-Demo-Portfolio, siehe z.B. linehaul_presets.py)."""

import math
import random
from dataclasses import dataclass
from typing import Callable, Optional

import streamlit as st

import quaycrane_constants as C


@dataclass(frozen=True)
class SettingSpec:
    url_param: str
    caster: Callable
    default: object
    lo: Optional[float] = None
    hi: Optional[float] = None


SETTING_SPECS = {
    "n_bays_slider": SettingSpec("nb", int, C.N_BAYS_DEFAULT, *C.N_BAYS_RANGE),
    "n_cranes_slider": SettingSpec("nc", int, C.N_CRANES_DEFAULT, *C.N_CRANES_RANGE),
    "moves_avg_slider": SettingSpec("ma", int, C.MOVES_AVG_DEFAULT, *C.MOVES_AVG_RANGE),
    "moves_variability_slider": SettingSpec("mv", float, C.MOVES_VARIABILITY_DEFAULT, *C.MOVES_VARIABILITY_RANGE),
    "time_per_move_slider": SettingSpec("tpm", float, C.TIME_PER_MOVE_DEFAULT, *C.TIME_PER_MOVE_RANGE),
    "travel_time_per_bay_slider": SettingSpec(
        "ttb", float, C.TRAVEL_TIME_PER_BAY_DEFAULT, *C.TRAVEL_TIME_PER_BAY_RANGE
    ),
    "safety_margin_slider": SettingSpec("sm", int, C.SAFETY_MARGIN_DEFAULT, *C.SAFETY_MARGIN_RANGE),
    "seed_input": SettingSpec("seed", int, C.RANDOM_SEED_DEFAULT, *C.RANDOM_SEED_RANGE),
}


def bounds(state_key):
    spec = SETTING_SPECS[state_key]
    return spec.lo, spec.hi


def init_session_state_defaults():
    for state_key, spec in SETTING_SPECS.items():
        if state_key not in st.session_state:
            st.session_state[state_key] = spec.default
    if "force_regen" not in st.session_state:
        st.session_state["force_regen"] = False


def load_permalink_settings():
    if "permalink_loaded" in st.session_state:
        return
    qp = st.query_params
    for state_key, spec in SETTING_SPECS.items():
        if spec.url_param in qp:
            try:
                value = spec.caster(qp[spec.url_param])
                if isinstance(value, float) and not math.isfinite(value):
                    continue
                if spec.lo is not None:
                    value = max(spec.lo, value)
                if spec.hi is not None:
                    value = min(spec.hi, value)
                st.session_state[state_key] = value
            except (ValueError, TypeError):
                pass
    st.session_state["permalink_loaded"] = True


def sync_query_params(n_bays, n_cranes, moves_avg, moves_variability, time_per_move,
                       travel_time_per_bay, safety_margin, seed):
    try:
        st.query_params["nb"] = str(int(n_bays))
        st.query_params["nc"] = str(int(n_cranes))
        st.query_params["ma"] = str(int(moves_avg))
        st.query_params["mv"] = str(moves_variability)
        st.query_params["tpm"] = str(time_per_move)
        st.query_params["ttb"] = str(travel_time_per_bay)
        st.query_params["sm"] = str(int(safety_margin))
        st.query_params["seed"] = str(int(seed))
    except Exception:
        pass


def apply_preset(name):
    p = C.PRESETS[name]
    st.session_state["n_bays_slider"] = p["n_bays"]
    st.session_state["n_cranes_slider"] = p["n_cranes"]
    st.session_state["moves_avg_slider"] = p["moves_avg"]
    st.session_state["moves_variability_slider"] = p["moves_variability"]
    st.session_state["time_per_move_slider"] = p["time_per_move"]
    st.session_state["travel_time_per_bay_slider"] = p["travel_time_per_bay"]
    st.session_state["safety_margin_slider"] = p["safety_margin"]
    st.session_state["seed_input"] = p["seed"]
    st.session_state["force_regen"] = True


def randomize_seed():
    st.session_state["seed_input"] = random.randint(0, 2_000_000_000)
    st.session_state["force_regen"] = True

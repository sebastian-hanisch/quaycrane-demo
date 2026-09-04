import streamlit as st

import quaycrane_constants as C
from quaycrane_cp_solver import solve_exact
from quaycrane_evaluation import build_schedule, comparison_table, evaluate
from quaycrane_heuristic import balanced_zone_construction, greedy_and_polish, naive_construction
from quaycrane_pdf_export import generate_crane_plan_pdf
from quaycrane_presets import (
    apply_preset,
    bounds,
    init_session_state_defaults,
    load_permalink_settings,
    randomize_seed,
    sync_query_params,
)
from quaycrane_scenario import generate_instance
from quaycrane_ui_panel import render_crane_panel
from quaycrane_visualization import build_crane_trajectory_chart, build_makespan_comparison_chart

st.set_page_config(page_title="Containerbrücken-Einsatzplanung – Sebastian Hanisch", layout="wide")


@st.cache_data(show_spinner=False)
def _compute_all(n_bays, n_cranes, moves_avg, moves_variability, time_per_move, travel_time_per_bay,
                  safety_margin, seed, run_exact):
    instance = generate_instance(
        n_bays, n_cranes, moves_avg, moves_variability, time_per_move, travel_time_per_bay, safety_margin, seed
    )

    results = [
        evaluate(instance, build_schedule(instance, naive_construction(instance)), label="Naive (gleichmäßige Aufteilung)"),
        evaluate(instance, build_schedule(instance, balanced_zone_construction(instance)), label="Greedy (Zonenbalance)"),
        evaluate(instance, build_schedule(instance, greedy_and_polish(instance, seed=seed)), label="Greedy + lokale Suche"),
    ]

    exact_result = None
    if run_exact:
        solve = solve_exact(instance, time_limit_seconds=C.EXACT_SOLVE_TIME_LIMIT_SECONDS)
        if solve.feasible:
            exact_label = "Exakt (OR-Tools)" if solve.optimal else "Exakt (OR-Tools, Zeitlimit)"
            exact_eval = evaluate(instance, solve.tasks, label=exact_label)
            exact_result = {"eval": exact_eval, "optimal": solve.optimal, "wall_time_ms": solve.wall_time_ms}

    return instance, results, exact_result


@st.cache_data(show_spinner=False)
def _best_makespan_for_crane_count(n_bays, n_cranes, moves_avg, moves_variability, time_per_move,
                                    travel_time_per_bay, safety_margin, seed):
    instance = generate_instance(
        n_bays, n_cranes, moves_avg, moves_variability, time_per_move, travel_time_per_bay, safety_margin, seed
    )
    tasks = build_schedule(instance, greedy_and_polish(instance, seed=seed))
    return evaluate(instance, tasks, label=f"{n_cranes} Kräne")


st.title("🏗️ Containerbrücken-Einsatzplanung (Quay Crane Scheduling)")
st.markdown(
    """
Welche **Containerbrücke** übernimmt welche **Bay** (Ladeluke) eines Schiffs - und in welcher
Reihenfolge? Ein klassisches Scheduling-Problem aus dem Terminalbetrieb: mehrere Kräne teilen
sich dieselbe Kaischiene, können sich dabei aber **nie überholen** - das begrenzt, wie viel
Parallelität zusätzliche Kräne wirklich bringen (**Kran-Interferenz**). Ziel ist die minimale
**Liegezeit** des Schiffs. Wie das Modell und die vier Verfahren im Detail funktionieren, steht
im Expander "Wie funktioniert diese Demo?" weiter unten, die formale Herleitung im Expander
"📐 Mathematische Formulierung".
"""
)

st.caption("🎯 Schnellstart – ein Beispielszenario laden:")
PRESET_HELP = {
    "Kleines Feederschiff": "Wenige Bays, zwei Kräne - Interferenz spielt kaum eine Rolle.",
    "Mittleres Schiff, Normalbetrieb": "Typische Größe, drei Kräne - guter Ausgangspunkt zum Herumspielen.",
    "Großes Schiff, viele Kräne": "Fünf Kräne auf einem langen Schiff - hier zeigt sich, wie stark "
    "sich zusätzliche Kräne gegenseitig ausbremsen können.",
    "Enge Sicherheitsabstände": "Großer Sicherheitsabstand zwischen Kränen - Interferenz-Wartezeit "
    "wird zum dominanten Effekt.",
}
preset_cols = st.columns(len(C.PRESETS))
for i, name in enumerate(C.PRESETS.keys()):
    with preset_cols[i]:
        st.button(name, use_container_width=True, on_click=apply_preset, args=(name,), help=PRESET_HELP[name])

st.caption(
    "🔗 Die Adresszeile oben spiegelt Ihre aktuelle Konfiguration wider – einfach kopieren, "
    "um ein Szenario zu teilen."
)

load_permalink_settings()
init_session_state_defaults()

with st.sidebar:
    st.header("⚙️ Einstellungen")
    n_bays = st.slider("Anzahl Bays (Schiffslänge)", *bounds("n_bays_slider"), key="n_bays_slider")
    n_cranes = st.slider("Anzahl Containerbrücken", *bounds("n_cranes_slider"), key="n_cranes_slider")
    seed = st.number_input("Zufalls-Seed", *bounds("seed_input"), key="seed_input", step=1)

    st.markdown("**Arbeitslast & Zeiten**")
    moves_avg = st.slider("Ø Container-Moves je Bay", *bounds("moves_avg_slider"), key="moves_avg_slider")
    moves_variability = st.slider(
        "Streuung der Arbeitslast", *bounds("moves_variability_slider"), key="moves_variability_slider"
    )
    time_per_move = st.slider(
        "Zeit je Move (Minuten)", *bounds("time_per_move_slider"), key="time_per_move_slider"
    )
    travel_time_per_bay = st.slider(
        "Kranfahrzeit je Bay (Minuten)", *bounds("travel_time_per_bay_slider"), key="travel_time_per_bay_slider"
    )

    st.markdown("**Physische Randbedingung**")
    safety_margin = st.slider(
        "Sicherheitsabstand zwischen Kränen (Bays)",
        *bounds("safety_margin_slider"),
        key="safety_margin_slider",
        help="Mindestabstand in Bays, den zwei Kräne einhalten müssen, solange beide gleichzeitig "
        "arbeiten - der Grund, warum sich Kräne nie überholen dürfen.",
    )

    st.markdown("**Referenz**")
    run_exact = st.checkbox(
        "Exakte Lösung berechnen (OR-Tools CP-SAT)",
        value=True,
        help="Löst das vollständige Scheduling-Modell exakt - dient als Cross-Check für die "
        f"Heuristiken. Auf {C.EXACT_SOLVE_TIME_LIMIT_SECONDS}s begrenzt (bei vielen Bays/Kränen "
        "manchmal nur die beste gefundene, nicht bewiesen optimale Lösung - wird dann so "
        "gekennzeichnet).",
    )

    st.button(
        "🎲 Neues Zufallsschiff generieren",
        use_container_width=True,
        on_click=randomize_seed,
        help="Würfelt einen neuen Zufalls-Seed für die Bay-Arbeitslasten.",
    )

sync_query_params(
    n_bays, n_cranes, moves_avg, moves_variability, time_per_move, travel_time_per_bay, safety_margin, seed
)

with st.spinner("Berechne Kranplan..."):
    instance, results, exact_result = _compute_all(
        int(n_bays), int(n_cranes), int(moves_avg), moves_variability, time_per_move,
        travel_time_per_bay, int(safety_margin), int(seed), run_exact,
    )

best = min(results, key=lambda r: r["makespan"])
baseline = max(results, key=lambda r: r["makespan"])
time_saved = baseline["makespan"] - best["makespan"]
pct_saved = (time_saved / baseline["makespan"] * 100) if baseline["makespan"] > 0 else 0.0

st.markdown("## 🎯 Ihr kürzester Kranplan")
st.caption(f"Methode: **{best['label']}** - wird bei jedem Lauf neu anhand der Liegezeit bestimmt.")

m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "Liegezeit (Makespan)",
    f"{best['makespan']:.0f} min",
    delta=f"-{time_saved:.0f} min ggü. {baseline['label']}",
    delta_color="inverse",
)
m2.metric("Wartezeit durch Interferenz", f"{best['total_wait_time']:.0f} min")
m3.metric("Fahrzeit gesamt", f"{best['total_travel_time']:.0f} min")
m4.metric("Lastungleichgewicht", f"{best['load_imbalance']:.0f} min")

if time_saved > 1:
    st.success(
        f"⏱️ **{best['label']}** spart hier ca. **{time_saved:.0f} min** ({pct_saved:.1f}%) "
        f"Liegezeit gegenüber '{baseline['label']}'."
    )

if exact_result is not None:
    exact_eval = exact_result["eval"]
    gap = best["makespan"] - exact_eval["makespan"]
    gap_pct = (gap / exact_eval["makespan"] * 100) if exact_eval["makespan"] > 0 else 0.0

    if exact_result["optimal"]:
        if gap < 1:
            st.info(
                f"✅ Exakter Referenzlöser (OR-Tools, optimal gelöst, "
                f"{exact_result['wall_time_ms']:.0f} ms): **{best['label']}** erreicht bereits "
                f"das Optimum ({exact_eval['makespan']:.0f} min)."
            )
        else:
            st.info(
                f"📐 Exakter Referenzlöser (OR-Tools, optimal gelöst, "
                f"{exact_result['wall_time_ms']:.0f} ms): Optimum liegt bei "
                f"{exact_eval['makespan']:.0f} min - Lücke zur besten Heuristik: {gap:.0f} min "
                f"({gap_pct:.1f}%)."
            )
    else:
        if gap <= 1:
            st.warning(
                f"⏱️ Exakter Referenzlöser (OR-Tools, Zeitlimit erreicht, kein Optimalitäts-"
                f"beweis, {exact_result['wall_time_ms']:.0f} ms): **{best['label']}** "
                f"({best['makespan']:.0f} min) erreicht oder unterbietet sogar die beste vom "
                f"Solver gefundene Lösung ({exact_eval['makespan']:.0f} min) - das tatsächliche "
                f"Optimum könnte noch darunter liegen."
            )
        else:
            st.warning(
                f"⏱️ Exakter Referenzlöser (OR-Tools, Zeitlimit erreicht, kein Optimalitäts-"
                f"beweis, {exact_result['wall_time_ms']:.0f} ms): beste bislang gefundene "
                f"Lösung liegt bei {exact_eval['makespan']:.0f} min - {gap:.0f} min ({gap_pct:.1f}%) "
                f"unter der besten Heuristik, aber ohne Optimalitätsgarantie."
            )

fig_best = build_crane_trajectory_chart(instance, best, title=best["label"])
st.plotly_chart(fig_best, use_container_width=True, key="primary_trajectory")

pdf_bytes_best = generate_crane_plan_pdf(best["label"], instance, best)
st.download_button(
    "📄 Kranplan als PDF herunterladen",
    data=pdf_bytes_best,
    file_name="kranplan_optimiert.pdf",
    mime="application/pdf",
    key="primary_pdf_download",
)

st.caption(
    "Ermittelt mit der besten von drei eigenen Optimierungsmethoden für dieses Szenario. "
    "Details zu allen Methoden und dem Vergleich mit Google OR-Tools unten."
)

st.markdown("---")

st.subheader("📐 Lohnt sich ein zusätzlicher Kran?")
st.markdown(
    """
Kernfrage dieser Demo: Kräne teilen sich dieselbe Schiene und dürfen sich nicht überholen
(**Non-Crossing**). Ein zusätzlicher Kran bringt mehr parallele Kapazität, aber auch mehr
Gelegenheit für Interferenz - je enger die Bays und je größer der Sicherheitsabstand, desto
mehr **Wartezeit** frisst ein zusätzlicher Kran wieder auf. Hier live für Ihre aktuelle
Konfiguration geprüft, nicht nur behauptet.
"""
)

can_add = n_cranes < C.N_CRANES_RANGE[1]
alt_cranes = n_cranes + 1 if can_add else n_cranes - 1

if alt_cranes >= 1:
    current_hook = _best_makespan_for_crane_count(
        int(n_bays), int(n_cranes), int(moves_avg), moves_variability, time_per_move,
        travel_time_per_bay, int(safety_margin), int(seed),
    )
    alt_hook = _best_makespan_for_crane_count(
        int(n_bays), int(alt_cranes), int(moves_avg), moves_variability, time_per_move,
        travel_time_per_bay, int(safety_margin), int(seed),
    )
    delta_makespan = alt_hook["makespan"] - current_hook["makespan"]

    core_col1, core_col2, core_col3 = st.columns(3)
    core_col1.metric(f"{n_cranes} Kräne (aktuell)", f"{current_hook['makespan']:.0f} min")
    core_col2.metric(
        f"{alt_cranes} Kräne",
        f"{alt_hook['makespan']:.0f} min",
        delta=f"{delta_makespan:.0f} min ggü. {n_cranes} Kränen",
        delta_color="inverse",
    )
    core_col3.metric(
        f"Wartezeit bei {alt_cranes} Kränen",
        f"{alt_hook['total_wait_time']:.0f} min",
        delta=f"{alt_hook['total_wait_time'] - current_hook['total_wait_time']:.0f} min ggü. {n_cranes} Kränen",
        delta_color="inverse",
    )

    if can_add:
        if delta_makespan < -1:
            st.success(
                f"✅ Ein zusätzlicher Kran ({n_cranes} → {alt_cranes}) lohnt sich hier klar: "
                f"**{-delta_makespan:.0f} min** kürzere Liegezeit."
            )
        elif delta_makespan > -1 and delta_makespan < 1:
            st.warning(
                f"⚠️ Ein zusätzlicher Kran bringt hier kaum noch etwas - die Liegezeit ändert "
                f"sich um weniger als eine Minute. Kran-Interferenz frisst den zusätzlichen "
                f"Durchsatz praktisch komplett auf."
            )
        else:
            st.error(
                f"🚫 Ein zusätzlicher Kran macht es hier sogar **{delta_makespan:.0f} min "
                f"langsamer** - bei diesem Sicherheitsabstand und dieser Schiffslänge steht sich "
                f"der zusätzliche Kran selbst im Weg."
            )
    else:
        if delta_makespan > 1:
            st.info(
                f"ℹ️ Mit {n_cranes - 1} statt {n_cranes} Kränen wäre das Schiff **{delta_makespan:.0f} min** "
                f"langsamer fertig - der letzte Kran lohnt sich hier noch."
            )
        else:
            st.warning(
                f"⚠️ Der letzte (fünfte) Kran bringt kaum noch etwas: mit {n_cranes - 1} Kränen "
                f"wäre die Liegezeit nur {-delta_makespan:.0f} min länger."
            )
else:
    st.info("Bei nur einem Kran gibt es keine Interferenz zu vergleichen - erhöhen Sie die Kranzahl im Regler links.")

st.markdown("---")

with st.expander("🔧 Wie wir das erreichen – vollständiger Methodenvergleich"):
    all_results = list(results)
    if exact_result is not None:
        all_results.append(exact_result["eval"])

    st.dataframe(comparison_table(all_results), use_container_width=True, hide_index=True)
    st.plotly_chart(build_makespan_comparison_chart(all_results), use_container_width=True)

    prefixes = ["naive", "zone", "polish", "exact"]
    tabs = st.tabs([r["label"] for r in all_results])
    for tab, r, prefix in zip(tabs, all_results, prefixes):
        with tab:
            render_crane_panel(prefix, r["label"], instance, r)

with st.expander("Wie funktioniert diese Demo?"):
    st.markdown(
        """
Ein Schiff liegt am Kai und ist in **Bays** unterteilt - Ladeluken entlang der Schiffslänge,
jede mit einer bestimmten Anzahl Container-**Moves** zu erledigen. Mehrere **Containerbrücken**
(Quay Cranes) hängen an derselben Kaischiene und bearbeiten die Bays - jeweils eine Brücke pro
Bay zur Zeit, mit Fahrzeit beim Wechsel zwischen Bays.

Der entscheidende physische Zwang: Containerbrücken sitzen auf **derselben Schiene** und können
sich **nicht überholen**. Kran 1 bleibt für immer der linkeste, Kran *k* für immer der rechteste.
Wenn zwei Kräne gleichzeitig arbeiten, müssen sie einen **Sicherheitsabstand** in Bays einhalten
(**Non-Crossing-Constraint**, Kim & Park 2004) - genau das begrenzt, wie viel zusätzliche
Parallelität weitere Kräne wirklich bringen.

Vier Verfahren stehen zur Auswahl (im Expander "Wie wir das erreichen" alle nebeneinander),
zusätzlich eine **exakte Referenzlösung** (Google OR-Tools CP-SAT):

- **Naive (gleichmäßige Aufteilung)**: jeder Kran bekommt gleich viele Bays, ohne Rücksicht auf
  die tatsächliche Arbeitslast - Referenzpunkt.
- **Greedy (Zonenbalance)**: das Schiff wird per dynamischer Programmierung so in
  zusammenhängende Zonen geschnitten, dass die Arbeitslast je Kran möglichst gleich ist -
  zusammenhängende Zonen vermeiden Interferenz fast vollständig.
- **Greedy + lokale Suche**: startet bei der besseren von mehreren Konstruktionen und verbessert
  iterativ durch Kran-Tausch und Kran-Verlagerung einzelner Bays - nachweislich nie schlechter
  als der Startpunkt.

Die Primäransicht zeigt **dynamisch** die bei den aktuellen Einstellungen tatsächlich schnellste
Methode - keine wird pauschal bevorzugt. Die **Kran-Trajektorien**-Grafik zeigt für jeden Kran
seine Position über die Zeit: waagerechte Abschnitte sind Bearbeitung, schräge Abschnitte
Fahrzeit, rot gepunktete Abschnitte erzwungene Wartezeit durch einen benachbarten Kran - und die
Linien kreuzen sich nie.
        """
    )

with st.expander("📐 Mathematische Formulierung"):
    st.markdown(
        r"""
**Quay Crane Scheduling Problem (QCSP)** mit Non-Crossing-Constraints, NP-schwer (Kim & Park,
*European Journal of Operational Research*, 2004; Bierwirth & Meisel, Übersichtsartikel 2010/2015).

Gegeben Bays $i = 0, \dots, n-1$ (Bay-Index == Position entlang der Schiffsseite) mit fester
Bearbeitungsdauer $d_i$ (= Moves × Zeit/Move), Kräne $c = 0, \dots, k-1$ mit fester
Startposition $p_c$ und physisch fixer Reihenfolge (Kran $c$ ist immer links von Kran $c+1$),
Fahrzeit $\tau$ pro Bay-Abstand und Sicherheitsabstand $s$ (Bays).

Binäre Variable $x_{ic} \in \{0,1\}$: Bay $i$ wird von Kran $c$ bearbeitet, mit
$\sum_c x_{ic} = 1$. Ganzzahlige Startzeit $t_i \ge 0$, Endzeit $t_i + d_i$.

Für jedes Bay-Paar $i, j$ mit $i < j$: sind beide derselben Brücke zugeordnet, dürfen sich ihre
Zeitintervalle nicht überlappen und brauchen zusätzlich die Fahrzeit $\tau \cdot |i-j|$ als
Rüstzeit dazwischen (Reihenfolge frei wählbar - klassisches **Sequencing mit
sequenzabhängigen Rüstzeiten**). Sind sie unterschiedlichen Brücken $p \ne q$ zugeordnet, gilt
bei zeitlicher Überlappung die **Non-Crossing-Bedingung**:

$$
\text{Bay von Kran } p \;+\; s \;\le\; \text{Bay von Kran } q \qquad \text{falls } p < q
$$

Ist die Zuordnung "gekreuzt" (die physisch linkere Brücke soll die rechtere Bay bearbeiten,
während die rechtere Brücke gleichzeitig die linkere Bay bearbeitet), ist jede zeitliche
Überlappung unabhängig vom Sicherheitsabstand unzulässig - eine physische Unmöglichkeit, da sich
Kräne nie überholen können.

Zielfunktion: minimiere primär den **Makespan**, als lexikografisches Tie-Breaking-Ziel
zusätzlich die Summe aller Endzeiten (verhindert, dass der Solver unter mehreren gleich-optimalen
Lösungen willkürlich eine mit unnötigem Leerlauf auf einem unkritischen Kran zurückgibt - siehe
README für den Fund, der das nötig gemacht hat)

$$
\min \; \Big(\max_i \; (t_i + d_i)\Big) \cdot W \;+\; \sum_i (t_i + d_i)
$$

mit einem Gewicht $W$, das groß genug ist, dass eine Verbesserung des Tie-Breaking-Ziels nie
eine Verschlechterung des Makespans aufwiegen kann.

Gelöst mit Google OR-Tools CP-SAT in [quaycrane_cp_solver.py](quaycrane_cp_solver.py), auf
LIMIT_PLACEHOLDERs Rechenzeit begrenzt - für die in dieser Demo möglichen Größen (bis 24 Bays,
5 Kräne) bei moderater Kranzahl fast immer das bewiesene Optimum, bei vielen Bays UND vielen
Kränen gleichzeitig manchmal nur die beste innerhalb des Zeitlimits gefundene Lösung (dann klar
als "Zeitlimit erreicht" gekennzeichnet).

Die **Zonenbalance**-Heuristik löst als Teilschritt exakt das klassische "Zerlege ein Array in
$k$ zusammenhängende Teile, minimiere die größte Teilsumme"-Problem per dynamischer
Programmierung ($O(n^2 k)$) - das liefert bereits eine gute, interferenzfreie Startlösung, die
die lokale Suche danach noch verfeinert.
        """.replace("LIMIT_PLACEHOLDER", str(C.EXACT_SOLVE_TIME_LIMIT_SECONDS))
    )

st.markdown("---")

st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning. Interesse an einer maßgeschneiderten Lösung für "
    "Ihr Unternehmen? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html)"
)

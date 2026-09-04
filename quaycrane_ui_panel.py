"""Wiederverwendbares Panel zur Darstellung einer Methode im Methodenvergleich."""

import streamlit as st

from quaycrane_pdf_export import generate_crane_plan_pdf
from quaycrane_visualization import build_crane_load_chart, build_crane_trajectory_chart


def render_crane_panel(prefix, label, instance, result):
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Liegezeit (Makespan)", f"{result['makespan']:.0f} min")
    m2.metric("Wartezeit (Interferenz)", f"{result['total_wait_time']:.0f} min")
    m3.metric("Fahrzeit gesamt", f"{result['total_travel_time']:.0f} min")
    m4.metric("Lastungleichgewicht", f"{result['load_imbalance']:.0f} min")

    fig = build_crane_trajectory_chart(instance, result, title=label)
    st.plotly_chart(fig, use_container_width=True, key=f"{prefix}_trajectory")
    st.plotly_chart(build_crane_load_chart(instance, result), use_container_width=True, key=f"{prefix}_load")

    pdf_bytes = generate_crane_plan_pdf(label, instance, result)
    st.download_button(
        "📄 Kranplan als PDF herunterladen",
        data=pdf_bytes,
        file_name=f"kranplan_{prefix}.pdf",
        mime="application/pdf",
        key=f"{prefix}_pdf_download",
    )

    return result

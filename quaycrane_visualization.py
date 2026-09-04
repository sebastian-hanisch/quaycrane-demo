"""Plotly-Visualisierungen: Kran-Trajektorien (Kernvisual) und Methodenvergleich."""

import quaycrane_constants as C
from quaycrane_evaluation import crane_position_segments


def build_crane_trajectory_chart(instance, result, title=""):
    import plotly.graph_objects as go

    fig = go.Figure()
    tasks = result["tasks"]

    segments_by_crane = {c: [] for c in range(instance.n_cranes)}
    for seg in crane_position_segments(instance, tasks):
        segments_by_crane[seg[0]].append(seg)

    for c in range(instance.n_cranes):
        segs = sorted(segments_by_crane[c], key=lambda s: s[1])
        xs, ys = [], []
        wait_segments = []
        for crane, t0, p0, t1, p1, kind in segs:
            if not xs:
                xs.append(t0)
                ys.append(p0)
            xs.append(t1)
            ys.append(p1)
            if kind == "wait":
                wait_segments.append((t0, t1, p0))

        color = C.CRANE_COLORS[c % len(C.CRANE_COLORS)]
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines+markers",
                name=f"Kran {c + 1}",
                line=dict(color=color, width=3),
                marker=dict(size=5),
                hovertemplate=f"Kran {c + 1}<br>t=%{{x:.1f}} min<br>Bay %{{y:.1f}}<extra></extra>",
            )
        )
        for x0, x1, y in wait_segments:
            fig.add_trace(
                go.Scatter(
                    x=[x0, x1],
                    y=[y, y],
                    mode="lines",
                    line=dict(color="#d62728", width=7, dash="dot"),
                    showlegend=False,
                    hovertemplate=f"Kran {c + 1}: wartet auf Nachbarkran<br>%{{x:.1f}} min<extra></extra>",
                )
            )

    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="lines",
            line=dict(color="#d62728", width=7, dash="dot"),
            name="Wartezeit durch Kran-Interferenz",
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="Zeit (Minuten)",
        yaxis_title="Bay-Position auf dem Schiff",
        template="plotly_white",
        height=460,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(t=60),
    )
    fig.update_yaxes(dtick=1)
    # fixedrange auf beiden Achsen: verhindert Pinch-Zoom/Drag-Pan im Chart, damit auf
    # Touch-Geräten stattdessen die Seite normal gescrollt wird (Hover-Tooltips bleiben
    # davon unberührt).
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def build_makespan_comparison_chart(results):
    import plotly.graph_objects as go

    labels = [r["label"] for r in results]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=[r["makespan"] for r in results], name="Liegezeit (Makespan)", marker_color="#1f77b4"))
    fig.add_trace(
        go.Bar(x=labels, y=[r["total_wait_time"] for r in results], name="davon Wartezeit (Interferenz)", marker_color="#d62728")
    )
    fig.update_layout(
        barmode="group",
        yaxis_title="Minuten",
        template="plotly_white",
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def build_crane_load_chart(instance, result):
    import plotly.graph_objects as go

    cranes = [f"Kran {c + 1}" for c in range(instance.n_cranes)]
    stats = result["crane_stats"]
    busy = [stats[c]["busy_time"] for c in range(instance.n_cranes)]
    travel = [stats[c]["travel_time"] for c in range(instance.n_cranes)]
    wait = [stats[c]["wait_time"] for c in range(instance.n_cranes)]
    idle = [stats[c]["idle_after"] for c in range(instance.n_cranes)]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=cranes, y=busy, name="Umschlag (Bearbeitung)", marker_color="#2ca02c"))
    fig.add_trace(go.Bar(x=cranes, y=travel, name="Fahrzeit", marker_color="#1f77b4"))
    fig.add_trace(go.Bar(x=cranes, y=wait, name="Wartezeit (Interferenz)", marker_color="#d62728"))
    fig.add_trace(go.Bar(x=cranes, y=idle, name="Leerlauf bis Liegezeitende", marker_color="#bbbbbb"))
    fig.update_layout(
        barmode="stack",
        yaxis_title="Minuten",
        template="plotly_white",
        height=360,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig

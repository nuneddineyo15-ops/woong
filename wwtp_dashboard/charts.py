"""Plotly 차트: 추이 + 규격선 + 근접 구간 + 이상 구간 표시."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from core import KIND, PARAMS, near_margin

LINE_COLOR = "#22d3ee"


def style(fig: go.Figure) -> go.Figure:
    """다크 관제 테마 공통 스타일."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94a3b8"),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,.05)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,.05)", zeroline=False)
    return fig


def _spans(mask: pd.Series) -> list[tuple]:
    out, start = [], None
    idx = mask.index
    for i, f in enumerate(mask.values):
        if f and start is None:
            start = idx[i]
        elif not f and start is not None:
            out.append((start, idx[i - 1]))
            start = None
    if start is not None:
        out.append((start, idx[-1]))
    return out


def sensor_figure(df: pd.DataFrame, param: str, window_min: int, height: int = 230) -> go.Figure:
    p = PARAMS[param]
    lsl, usl, m = p["lsl"], p["usl"], near_margin(p)
    w = df.iloc[-window_min:]

    lo = min(w["value"].min(), lsl if lsl is not None else w["value"].min())
    hi = max(w["value"].max(), usl)
    pad = (hi - lo) * 0.08
    y0, y1 = lo - pad, hi + pad

    fig = go.Figure()

    # 상한 쪽: 근접(주황) + 이탈(빨강) 영역
    fig.add_hrect(y0=usl - m, y1=usl, fillcolor="rgba(249,115,22,.14)", line_width=0, layer="below")
    fig.add_hrect(y0=usl, y1=y1, fillcolor="rgba(239,68,68,.12)", line_width=0, layer="below")
    # 하한 쪽
    if lsl is not None:
        fig.add_hrect(y0=lsl, y1=lsl + m, fillcolor="rgba(249,115,22,.14)", line_width=0, layer="below")
        fig.add_hrect(y0=y0, y1=lsl, fillcolor="rgba(239,68,68,.12)", line_width=0, layer="below")

    # 이상 구간(Hold / σ 초과) 세로 음영
    for kind, col in (("HOLD", "hold"), ("STD", "stdx")):
        rgb = {"HOLD": "59,130,246", "STD": "168,85,247"}[kind]
        for a, b in _spans(w[col]):
            fig.add_vrect(x0=a, x1=b, fillcolor=f"rgba({rgb},.18)", line_width=0, layer="below")

    # 본선
    fig.add_trace(
        go.Scatter(
            x=w.index, y=w["value"], mode="lines", name=param,
            line=dict(color=LINE_COLOR, width=1.8),
            hovertemplate="%{x|%H:%M}  <b>%{y:.2f}</b> " + p["unit"] + "<extra></extra>",
        )
    )
    # 이탈/근접 점
    for kind, col, size in (("NEAR", "near", 5), ("SPEC", "spec", 7)):
        pts = w[w[col]]
        if len(pts):
            fig.add_trace(
                go.Scatter(
                    x=pts.index, y=pts["value"], mode="markers", name=KIND[kind]["label"],
                    marker=dict(color=KIND[kind]["color"], size=size),
                    hovertemplate=f"{KIND[kind]['label']}  %{{y:.2f}}<extra></extra>",
                )
            )

    # 규격선
    fig.add_hline(y=usl, line=dict(color="#ef4444", width=1.3, dash="dash"),
                  annotation_text=f"USL {usl:g}", annotation_position="top left",
                  annotation_font=dict(size=10, color="#ef4444"))
    if lsl is not None:
        fig.add_hline(y=lsl, line=dict(color="#ef4444", width=1.3, dash="dash"),
                      annotation_text=f"LSL {lsl:g}", annotation_position="bottom left",
                      annotation_font=dict(size=10, color="#ef4444"))

    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        showlegend=False,
        hovermode="x unified",
        xaxis=dict(tickformat="%H:%M", showgrid=False),
        yaxis=dict(range=[y0, y1], title=None),
    )
    return style(fig)

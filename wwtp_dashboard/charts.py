"""Plotly 차트: 추이 + 규격선 + 근접/이탈 구간 + 이상 구간 + 동료 비교."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from core import KIND, Plant

LINE_COLOR = "#0e7490"
BAND_KINDS = [k for k in KIND if k not in ("SPEC", "NEAR")]   # 세로 음영으로 보여 줄 경고


def rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def style(fig: go.Figure) -> go.Figure:
    """밝은 현장 모니터 테마 공통 스타일."""
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#475569"),
    )
    fig.update_xaxes(gridcolor="rgba(15,23,42,.07)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(15,23,42,.07)", zeroline=False)
    return fig


def _spans(mask: np.ndarray, x) -> list[tuple]:
    out, start = [], None
    for i, f in enumerate(mask):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((x[start], x[i - 1]))
            start = None
    if start is not None:
        out.append((x[start], x[-1]))
    return out


def sensor_figure(plant: Plant, i: int, window: int, height: int = 230, peers: bool = True) -> go.Figure:
    unit = plant.meta["unit"].iat[i]
    lsl, usl, m = plant.lsl[i], plant.usl[i], plant.margin[i]
    has_l = not np.isnan(lsl)
    x = plant.idx[-window:]
    y = plant.V[i, -window:]

    lo = min(y.min(), lsl if has_l else y.min())
    hi = max(y.max(), usl)
    pad = (hi - lo) * 0.08
    y0, y1 = lo - pad, hi + pad

    fig = go.Figure()

    # 규격 영역: 근접(주황) / 이탈(빨강)
    fig.add_hrect(y0=usl - m, y1=usl, fillcolor="rgba(249,115,22,.14)", line_width=0, layer="below")
    fig.add_hrect(y0=usl, y1=y1, fillcolor="rgba(239,68,68,.12)", line_width=0, layer="below")
    if has_l:
        fig.add_hrect(y0=lsl, y1=lsl + m, fillcolor="rgba(249,115,22,.14)", line_width=0, layer="below")
        fig.add_hrect(y0=y0, y1=lsl, fillcolor="rgba(239,68,68,.12)", line_width=0, layer="below")

    # 이상 구간 세로 음영 (Hold / σ 초과 / 동료 이탈 / 공정 연관 규칙) — 색은 KIND 의 경고 색
    for kind in BAND_KINDS:
        for a, b in _spans(plant.F[kind][i, -window:], x):
            fig.add_vrect(x0=a, x1=b, fillcolor=f"rgba({rgb(KIND[kind]['color'])},.16)", line_width=0, layer="below")

    # 동료(같은 항목 다른 센서) 범위 + 중앙값
    if peers:
        mem = plant.members[plant.G[i]]
        mem = mem[mem != i]
        if len(mem):
            P = plant.V[mem][:, -window:]
            fig.add_trace(go.Scatter(x=x, y=P.min(axis=0), mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=x, y=P.max(axis=0), mode="lines", line=dict(width=0), fill="tonexty",
                                     fillcolor="rgba(100,116,139,.16)", hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=x, y=np.median(P, axis=0), mode="lines", line=dict(color="#64748b", width=1.2, dash="dot"),
                                     hovertemplate="동료 중앙값 %{y:.2f}<extra></extra>", showlegend=False))

    fig.add_trace(
        go.Scatter(x=x, y=y, mode="lines", line=dict(color=LINE_COLOR, width=1.9),
                   hovertemplate="<b>%{y:.2f}</b> " + unit + "<extra></extra>", showlegend=False)
    )
    for kind, size in (("NEAR", 5), ("SPEC", 7)):
        mk = plant.F[kind][i, -window:]
        if mk.any():
            fig.add_trace(go.Scatter(x=x[mk], y=y[mk], mode="markers", marker=dict(color=KIND[kind]["color"], size=size),
                                     hovertemplate=f"{KIND[kind]['label']} %{{y:.2f}}<extra></extra>", showlegend=False))

    fig.add_hline(y=usl, line=dict(color="#ef4444", width=1.3, dash="dash"), annotation_text=f"USL {usl:g}",
                  annotation_position="top left", annotation_font=dict(size=10, color="#ef4444"))
    if has_l:
        fig.add_hline(y=lsl, line=dict(color="#ef4444", width=1.3, dash="dash"), annotation_text=f"LSL {lsl:g}",
                      annotation_position="bottom left", annotation_font=dict(size=10, color="#ef4444"))

    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), showlegend=False, hovermode="x unified",
        xaxis=dict(tickformat="%H:%M" if window <= 288 else "%m/%d %H:%M", showgrid=False),
        yaxis=dict(range=[y0, y1], title=None),
    )
    return style(fig)

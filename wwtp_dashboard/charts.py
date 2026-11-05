"""Plotly 차트: 센서 추이(sensor_figure) · 이상점 트렌드(trend_figure, 전체 현황용)."""
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


SEV_RGB = {"red": "220,38,38", "yellow": "245,158,11"}


def trend_figure(plant: Plant, i: int, window: int, height: int = 260) -> go.Figure:
    """이상점 트렌드: 영역 차트 + 임계치(USL/LSL) 점선 + 이상 구간 음영(조치 필요 = 빨강, 확인 필요 = 노랑)
    + 임계치를 넘은 점은 큰 붉은 마커 + 차트 위쪽 경고 문구."""
    unit, dec = plant.meta["unit"].iat[i], int(plant.meta["dec"].iat[i])
    lsl, usl = plant.lsl[i], plant.usl[i]
    has_l = not np.isnan(lsl)
    x = plant.idx[-window:]
    y = plant.V[i, -window:]
    lo = min(y.min(), lsl if has_l else y.min())
    hi = max(y.max(), usl)
    pad = (hi - lo) * 0.08
    y0, y1 = lo - pad, hi + pad

    fig = go.Figure()
    red = np.zeros(window, bool)
    yel = np.zeros(window, bool)
    for k, v in KIND.items():
        if v["sev"] == "red":
            red |= plant.F[k][i, -window:]
        else:
            yel |= plant.F[k][i, -window:]
    yel &= ~red
    for mask, sev in ((red, "red"), (yel, "yellow")):
        for a, b in _spans(mask, x):
            fig.add_vrect(x0=a, x1=b, fillcolor=f"rgba({SEV_RGB[sev]},.13)", line_width=0, layer="below")

    # 영역 차트: 아래 경계(y0)까지 채움
    fig.add_trace(go.Scatter(x=x, y=np.full(window, y0), mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=LINE_COLOR, width=1.8), fill="tonexty",
                             fillcolor="rgba(14,116,144,.12)", showlegend=False,
                             hovertemplate="%{x|%H:%M}  <b>%{y:." + str(dec) + "f}</b> " + unit + "<extra></extra>"))
    mem = plant.members[plant.G[i]]
    mem = mem[mem != i]
    if len(mem):
        fig.add_trace(go.Scatter(x=x, y=np.median(plant.V[mem][:, -window:], axis=0), mode="lines",
                                 line=dict(color="#94a3b8", width=1, dash="dot"), showlegend=False,
                                 hovertemplate="동료 중앙값 %{y:.2f}<extra></extra>"))

    for val, name in ((usl, "USL"), (lsl if has_l else None, "LSL")):
        if val is not None:
            fig.add_hline(y=val, line=dict(color="#dc2626", width=1.4, dash="dash"), annotation_text=f"{name} {val:g}",
                          annotation_position="top left" if name == "USL" else "bottom left",
                          annotation_font=dict(size=10, color="#dc2626"))

    out = (y > usl) | ((y < lsl) if has_l else np.zeros(window, bool))
    if out.any():
        fig.add_trace(go.Scatter(x=x[out], y=y[out], mode="markers", showlegend=False,
                                 marker=dict(color="#dc2626", size=11, line=dict(color="#ffffff", width=1.5)),
                                 hovertemplate="임계치 초과 %{x|%H:%M}  <b>%{y:." + str(dec) + "f}</b><extra></extra>"))

    # 상단 경고 문구
    text, color = "", "#b45309"
    if out.any():
        dev = np.where(y > usl, y - usl, (lsl - y) if has_l else 0)
        j = int(np.argmax(np.where(out, dev, -np.inf)))
        low = has_l and y[j] < lsl
        text = (f"⚠ {'하한 이탈' if low else '상한 초과'} · {'최저' if low else '최고'} {y[j]:.{dec}f} {unit} ({x[j]:%H:%M})"
                f" · 임계치 밖 {int(out.sum()) * 5}분")
        color = "#dc2626"
    else:
        kinds = plant.active_kinds(i) or plant.window_kinds(i, window)
        if kinds:
            first = int(np.argmax(plant.F[kinds[0]][i, -window:]))
            text = f"⚠ {KIND[kinds[0]]['label'].split('(')[0]} · {x[first]:%H:%M}부터"
            color = "#dc2626" if KIND[kinds[0]]["sev"] == "red" else "#b45309"
    if text:
        fig.add_annotation(xref="paper", yref="paper", x=0, y=1.02, xanchor="left", yanchor="bottom", showarrow=False,
                           text=f"<b>{text}</b>", font=dict(size=12, color=color))

    fig.update_layout(height=height, margin=dict(l=8, r=8, t=28, b=8), showlegend=False, hovermode="x unified",
                      xaxis=dict(tickformat="%H:%M" if window <= 288 else "%m/%d %H:%M", showgrid=False),
                      yaxis=dict(range=[y0, y1], title=None))
    return style(fig)

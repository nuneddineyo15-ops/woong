"""Dash 화면용 그림/판정 함수 (views.py 의 Streamlit 비의존 부분을 옮김).

core(감지)·charts(센서 그래프)는 그대로 쓰고, 여기서는 전체 현황 캔버스·경고 타임라인·한눈에 비교 그림만 만든다.
Dash 쪽 클릭 연동을 위해 각 마크에 customdata(사고 키 / 센서 번호 / 사고 번호)를 심어 둔다.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from charts import BAND_KINDS, LINE_COLOR, _spans, rgb, style
from core import KIND, LINES, NONE_RANK, PROCESSES, kind_by_rank, tanks_of

SEV_COLOR = {"red": "#dc2626", "yellow": "#f59e0b", "green": "#16a34a"}
SEV_TEXT = {"red": "조치 필요", "yellow": "확인 필요", "green": "정상"}
IMPACT_COLOR = {"red": "#dc2626", "yellow": "#f97316", "green": "#94a3b8"}   # 다음 단계로 가는 화살표
OK_COLOR, RESOLVED_COLOR = "#16a34a", "#64748b"


def kind_name(k: str) -> str:
    return KIND[k]["label"].split("(")[0]


def color_of(rank: int) -> str:
    return OK_COLOR if rank >= NONE_RANK else KIND[kind_by_rank(rank)]["color"]


def status_text(rank: int) -> str:
    return "정상" if rank >= NONE_RANK else kind_name(kind_by_rank(rank))


def sev(rank: int) -> str:
    return "green" if rank >= NONE_RANK else KIND[kind_by_rank(rank)]["sev"]


def sev_ids(plant, ids) -> tuple[str, int | None]:
    """센서 묶음의 지금 신호등과 대표 센서: 빨강(조치 필요)이 하나라도 있으면 빨강, 그 외 이상이 있으면 노랑."""
    if not len(ids):
        return "green", None
    red = np.zeros(len(ids), bool)
    for k, v in KIND.items():
        if v["sev"] == "red":
            red |= plant.F[k][ids, -1]
    if red.any():
        return "red", int(ids[np.argmax(red)])
    r = plant.now_rank[ids]
    return ("yellow", int(ids[np.argmin(r)])) if r.min() < NONE_RANK else ("green", None)


def stages(p: str) -> list[str]:
    """공정 흐름 순서의 조 종류 (폭기조1~5, 반응조1~3 은 노드 하나)."""
    return list(dict.fromkeys(stage for _, stage, _ in tanks_of(p)))


def stage_name(stage: str) -> str:
    return stage.replace("유기침전조", "침전조").replace("무기침전조", "침전조")


def ikey(x: dict) -> tuple:
    return (x["bldg"], x["proc"], x["line"], x["stage"])


def now_worst(plant, x: dict) -> tuple[int, int]:
    """사고의 '지금' 가장 심한 경고 (순위, 센서). 이미 풀린 경고는 빼고 판단."""
    best, pick = (True, NONE_RANK), x["sids"][0]
    for i in x["sids"]:
        for k in plant.active_kinds(i):
            cand = (KIND[k]["sev"] != "red", KIND[k]["rank"])
            if cand < best:
                best, pick = cand, i
    return (best[1], pick) if best[1] < NONE_RANK else (x["rank"], x["sids"][0])


def headline(plant, x: dict) -> str:
    """이상점 요약 문장: [STAGE nn] 공정 조 · 위치 항목 현상 (현재값 단위)."""
    rank, i = now_worst(plant, x)
    m = plant.meta.iloc[i]
    k = kind_by_rank(rank)
    v = plant.V[i, -1]
    low = (not np.isnan(plant.lsl[i])) and v < (plant.lsl[i] + plant.usl[i]) / 2
    what = {
        "SPEC": ("농도 급감 · 하한 이탈" if m.param == "DO" else "하한 이탈") if low else "상한 초과",
        "NEAR": "하한 근접" if low else "상한 근접",
        "HOLD": "값 고정 1시간+ (센서·통신 확인)", "STD": "변동 급증", "VALVE": "개도-투입 불일치 (막힘·펌프 의심)",
        "AIR": "DO 하락 · 공기개도 상승 (산기관 의심)", "RATIO": "고분자 부족 (약품 대비)", "PEER": "동료 대비 이탈",
    }[k]
    n = stages(m.proc).index(m.stage) + 1
    return (f"[STAGE {n:02d}] {m.proc} {stage_name(m.stage)} · {m.bldg} {m.line} {m.tank} {m.param} {what} "
            f"({v:.{int(m.dec)}f} {m.unit})")


# ───────────────────────── 전체 현황 ③ 이상점 요약 캔버스 ─────────────────────────
def canvas_figure(plant, inc: list[dict], window: int, sel_key: tuple | None) -> go.Figure:
    """세로 = 공정·조(흐름 순서), 가로 = 시간. 사고마다 지속 막대 + 지금 점. 점을 누르면(clickData) 선택."""
    used = {(it["proc"], it["stage"]) for it in inc}
    lanes = [(p, s) for p in PROCESSES for s in stages(p) if (p, s) in used] or [(PROCESSES[0], stages(PROCESSES[0])[0])]
    ypos = {ls: n for n, ls in enumerate(lanes)}
    x = plant.idx[-window:]
    step = x[1] - x[0]
    slot, count = {}, {}
    for it in inc:                                           # 같은 줄에 사고가 여럿이면 높이를 나눠 겹치지 않게
        ls = (it["proc"], it["stage"])
        slot[ikey(it)] = count.get(ls, 0)
        count[ls] = count.get(ls, 0) + 1
    fig = go.Figure()
    for it in inc:
        sv = sev(now_worst(plant, it)[0] if it["active"] else it["rank"])
        n_in = count[(it["proc"], it["stage"])]
        y = ypos[(it["proc"], it["stage"])] + (slot[ikey(it)] - (n_in - 1) / 2) * min(0.24, 0.8 / n_in)
        key = "|".join(ikey(it))
        color = SEV_COLOR[sv] if it["active"] else "#94a3b8"
        end = "" if it["active"] else f"{it['last']:%H:%M}"
        hover = f"{it['title']}<br>{it['what']}<br>{status_text(it['rank'])} · {it['first']:%H:%M}~{end}"
        fig.add_trace(go.Scatter(x=[it["first"], it["last"] + step], y=[y, y], mode="lines", line=dict(color=color, width=6),
                                 customdata=[key, key], hovertext=[hover, hover], hoverinfo="text", showlegend=False))
        picked = sel_key == ikey(it)
        fig.add_trace(go.Scatter(x=[it["last"] + step], y=[y], mode="markers", customdata=[key], hovertext=[hover],
                                 hoverinfo="text", showlegend=False,
                                 marker=dict(size=14 if picked else (12 if it["active"] else 9),
                                             color=color if it["active"] else "#ffffff",
                                             line=dict(color="#0f172a" if picked else ("#ffffff" if it["active"] else "#94a3b8"),
                                                       width=3 if picked else 2))))
    fig.add_vline(x=x[-1] + step, line=dict(color="#0f172a", width=1, dash="dot"))
    for n in range(1, len(lanes)):
        if lanes[n][0] != lanes[n - 1][0]:
            fig.add_hline(y=n - 0.5, line=dict(color="#94a3b8", width=1))
    fig.update_yaxes(tickvals=list(range(len(lanes))), ticktext=[f"{p} · {stage_name(s)}" for p, s in lanes],
                     range=[len(lanes) - 0.5, -0.5], showgrid=False, tickfont=dict(size=12, color="#0f172a"))
    fig.update_xaxes(range=[x[0], x[-1] + step * 6], tickformat="%H:%M" if window <= 288 else "%m/%d %H:%M")
    fig.update_layout(height=58 * len(lanes) + 50, margin=dict(l=8, r=8, t=8, b=8), hovermode="closest", dragmode=False)
    return style(fig)


# ───────────────────────── 경고 센터 타임라인 ─────────────────────────
def timeline_figure(plant, inc: list[dict], window: int) -> go.Figure:
    """사고마다 한 줄, 경고 종류별 색 막대. 막대를 누르면(customdata = 사고 번호) 아래 해당 사고로 스크롤."""
    x = plant.idx[-window:]
    step = x[1] - x[0]
    labels, seen = [], set()
    for n, it in enumerate(inc):
        what = it["what"] if len(it["what"]) <= 28 else it["what"][:27] + "…"
        lab = f"{it['title']} · {what}"
        labels.append(lab if lab not in seen else f"{lab} ({n})")
        seen.add(labels[-1])
    fig = go.Figure()
    for kind in sorted(KIND, key=lambda k: -KIND[k]["rank"]):
        xs, ys, cd = [], [], []
        for n, (lab, it) in enumerate(zip(labels, inc)):
            mask = plant.F[kind][it["sids"], -window:].any(axis=0)
            for s0, s1 in _spans(mask, x):
                xs += [s0, s1 + step, None]
                ys += [lab, lab, None]
                cd += [n, n, None]
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=KIND[kind]["color"], width=11), customdata=cd,
                                     name=kind_name(kind), hovertemplate=f"{kind_name(kind)}<br>%{{x|%m/%d %H:%M}}<extra></extra>"))
    fig.add_vline(x=x[-1], line=dict(color="#1e293b", width=1, dash="dot"))
    fig.update_yaxes(categoryorder="array", categoryarray=labels, autorange="reversed", showgrid=True,
                     gridcolor="rgba(15,23,42,.06)", tickfont=dict(size=12, color="#0f172a"))
    fig.update_xaxes(tickformat="%H:%M" if window <= 288 else "%m/%d %H:%M", range=[x[0], x[-1] + step])
    fig.update_layout(height=26 * len(inc) + 80, margin=dict(l=8, r=8, t=30, b=8), dragmode=False,
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, font=dict(size=11), traceorder="reversed"))
    return style(fig)


# ───────────────────────── 한눈에 비교 ─────────────────────────
def compare_figure(plant, b: str, p: str, prm: str, window: int, full: bool) -> go.Figure:
    """계열 4 × 조 N 서브플롯. 같은 열은 y축을 맞춤. 선을 누르면(customdata = 센서 번호) 아래에 그 센서 상세."""
    tanks = tanks_of(p)
    cols = [t for t in tanks if prm in t[2]]
    nr, nc = len(LINES), len(cols)
    titles = []
    for l in LINES:
        for tank, _, _ in cols:
            i = plant.find(b, p, l, tank, prm)
            ks = plant.active_kinds(i)
            mark = f" <span style='color:{KIND[ks[0]]['color']}'>■ {kind_name(ks[0])}</span>" if ks else ""
            titles.append(f"<b>{l[0]}</b> · {tank}  {plant.V[i, -1]:.2f}{mark}")
    fig = make_subplots(rows=nr, cols=nc, subplot_titles=titles, shared_xaxes=True, shared_yaxes="columns",
                        vertical_spacing=0.06, horizontal_spacing=0.025)
    x = plant.idx[-window:]
    for r, l in enumerate(LINES, start=1):
        for ci, (tank, _, _) in enumerate(cols, start=1):
            i = plant.find(b, p, l, tank, prm)
            y = plant.V[i, -window:]
            ks = plant.active_kinds(i)
            color = KIND[ks[0]]["color"] if ks else LINE_COLOR
            for kind in BAND_KINDS:
                for s0, s1 in _spans(plant.F[kind][i, -window:], x):
                    fig.add_vrect(x0=s0, x1=s1, fillcolor=f"rgba({rgb(KIND[kind]['color'])},.22)", line_width=0, layer="below", row=r, col=ci)
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=color, width=1.4), showlegend=False,
                                     customdata=[int(i)] * len(x), hovertemplate="%{x|%H:%M}  <b>%{y:.2f}</b><extra></extra>"),
                          row=r, col=ci)
            for kind, size in (("NEAR", 4), ("SPEC", 5)):
                mk = plant.F[kind][i, -window:]
                if mk.any():
                    fig.add_trace(go.Scatter(x=x[mk], y=y[mk], mode="markers", marker=dict(color=KIND[kind]["color"], size=size),
                                             showlegend=False, hoverinfo="skip"), row=r, col=ci)
            if not np.isnan(plant.lsl[i]):
                fig.add_hline(y=plant.lsl[i], line=dict(color="#ef4444", width=1, dash="dot"), row=r, col=ci)
            fig.add_hline(y=plant.usl[i], line=dict(color="#ef4444", width=1, dash="dot"), row=r, col=ci)
    for ci, (tank, _, _) in enumerate(cols, start=1):
        ids = [plant.find(b, p, l, tank, prm) for l in LINES]
        lo = min(plant.V[i, -window:].min() for i in ids)
        hi = max(plant.V[i, -window:].max() for i in ids)
        if full:
            lo = min([lo] + [plant.lsl[i] for i in ids if not np.isnan(plant.lsl[i])])
            hi = max([hi] + [plant.usl[i] for i in ids])
        pad = (hi - lo) * 0.1 or 1
        fig.update_yaxes(range=[lo - pad, hi + pad], col=ci)
    fig.update_annotations(font_size=11)
    fig.update_xaxes(tickformat="%H:%M", showgrid=False)
    fig.update_layout(height=170 * nr + 50, margin=dict(l=8, r=8, t=28, b=8), hovermode="closest")
    return style(fig)

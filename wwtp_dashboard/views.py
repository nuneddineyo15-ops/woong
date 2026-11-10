"""화면 4개: 전체 현황(공정 흐름·이상점 연동) → 공정 상세(계열·조 흐름) → 한눈에 비교 → 경고 센터(사고 묶음)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from charts import BAND_KINDS, LINE_COLOR, _spans, rgb, sensor_figure, style, trend_figure
from core import (
    BUILDINGS, KIND, LINES, NONE_RANK, PROCESSES, STEP_MIN, get_plant, incidents, kind_by_rank, tanks_of,
)

RANGES = {"3시간": 36, "6시간": 72, "12시간": 144, "24시간": 288, "48시간": 576}
OK_COLOR, RESOLVED_COLOR = "#16a34a", "#64748b"


# ───────────────────────── 공통 ─────────────────────────
def _ctx():
    return get_plant(), RANGES[st.session_state.get("range", "24시간")]


def _color(rank: int) -> str:
    return OK_COLOR if rank >= NONE_RANK else KIND[kind_by_rank(rank)]["color"]


def _status_text(rank: int) -> str:
    return "정상" if rank >= NONE_RANK else KIND[kind_by_rank(rank)]["label"].split("(")[0]


def _legend():
    st.caption(
        "배경: 주황 = 상하한 근접 · 빨강 = 이탈  |  세로 음영: 파랑 = Hold · 보라 = σ 초과 · 분홍 = 동료 대비 이탈 · "
        "갈색 = 개도-투입 불일치 · 하늘색 = DO↓ 공기개도↑ · 남색 = 고분자 부족  |  "
        "회색 띠/점선 = 같은 항목 다른 센서의 범위/중앙값"
    )


def _header(title: str, sub: str):
    plant = get_plant()
    st.markdown(f"### {title}")
    st.caption(f"{sub}  |  데이터 기준 {plant.idx[-1]:%Y-%m-%d %H:%M} · {STEP_MIN}분 평균 (데모)")


def _sensor_head(plant, i: int, window: int) -> str:
    """센서 머리글 한 줄: 항목 · 현재값(이상이면 경고 색) · 1시간 변화 · 상태, 아래에 규격·σ·이력."""
    m = plant.meta.iloc[i]
    dec = int(m.dec)
    kinds = plant.active_kinds(i)
    hist = [k for k in plant.window_kinds(i, window) if k not in kinds]
    cur, d = plant.V[i, -1], plant.V[i, -1] - plant.V[i, -13]
    if kinds:
        state = " · ".join(f'<span style="color:{KIND[k]["color"]}">{_kind_name(k)}</span>' for k in kinds)
    elif hist:
        state = f'<span style="color:{RESOLVED_COLOR}">해소됨</span>'
    else:
        state = f'<span style="color:{OK_COLOR}">정상</span>'
    extra = f"규격 {plant.spec_text(i)} · σ {np.nan_to_num(plant.std[i, -1]):.2f}"
    if hist:
        extra += " · 이력: " + ", ".join(_kind_name(k) for k in hist)
    vcol = KIND[kinds[0]]["color"] if kinds else "var(--ink)"
    return (f'<div class="sh"><span class="p">{m.param}</span><span class="v" style="color:{vcol}">{cur:.{dec}f}</span>'
            f'<span class="u">{m.unit}</span><span class="dl">{d:+.{dec}f} /1h</span><span class="s">{state}</span>'
            f'<div class="x">{extra}</div></div>')


def _sensor_card(plant, i: int, window: int, height: int = 240):
    st.markdown(_sensor_head(plant, i, window), unsafe_allow_html=True)
    st.plotly_chart(sensor_figure(plant, i, window, height), width="stretch",
                    key=f"c-{i}-{window}", config={"displayModeBar": False})


def _incident_charts(plant, x: dict, window: int, prefix: str):
    """사고 1건의 센서 그래프 (최대 3개) + 나머지 센서 목록."""
    sids = x["sids"][:3]
    for col, i in zip(st.columns(len(sids)), sids):
        with col:
            m = plant.meta.iloc[i]
            ks = ", ".join(KIND[k]["label"].split("(")[0] for k in plant.window_kinds(i, window))
            st.caption(f"**{m.tank} · {m.param}**  —  {ks}")
            st.plotly_chart(sensor_figure(plant, i, window, 210), width="stretch",
                            key=f"{prefix}-{i}-{window}", config={"displayModeBar": False})
    if len(x["sids"]) > 3:
        st.caption("외 센서: " + ", ".join(f"{plant.meta['tank'].iat[i]} {plant.meta['param'].iat[i]}" for i in x["sids"][3:]))


# ───────────────────────── 1. 전체 현황 ─────────────────────────
# 한 화면 구성 (2026-11-10 재설계). 스크롤 없이 "괜찮은가 → 어디서 → 무엇부터 → 왜" 순서로 읽히게.
#   ⓪ 상황 한 줄      : 조치 필요 / 확인 필요 / 정상 센서 수 + 가장 급한 것 한 문장
#   ① 플랜트 맵       : 공정 흐름(조 종류 노드) 안에 동 3 × 계열 4 점 행렬 → 어느 동·계열인지 바로 보임. 점을 누르면 선택
#   ② 시급한 순 목록  : 위치 · 현상 · 현재값 · 몇 분째. 누르면 선택
#   ③ 선택 상세       : 선택한 곳의 센서 트렌드를 한 줄에  (+ 접어 둔 시간순 타임라인)
# 원칙: 정상은 조용하게(작은 회색 점), 이상만 크게·색으로. 맵·목록·타임라인 어디를 눌러도 같은 '선택'으로 묶임.
SEV_COLOR = {"red": "#dc2626", "yellow": "#f59e0b", "green": "#16a34a"}
SEV_TEXT = {"red": "조치 필요", "yellow": "확인 필요", "green": "정상"}
SEV_INK = {"red": "#dc2626", "yellow": "#b45309", "green": "#64748b"}        # 글자용(노랑은 흰 바탕에서 안 보여 갈색)
IMPACT_COLOR = {"red": "#dc2626", "yellow": "#f97316", "green": "#94a3b8"}   # 다음 단계로 가는 화살표
QUIET = "#dde3ec"                                                             # 정상 점
MAP_LANE_PX = 112


def _kind_name(k: str) -> str:
    return KIND[k]["label"].split("(")[0]


def _sev(rank: int) -> str:
    return "green" if rank >= NONE_RANK else KIND[kind_by_rank(rank)]["sev"]


def _sev_ids(plant, ids) -> tuple[str, int | None]:
    """센서 묶음의 지금 신호등과 대표 센서: 빨강(조치 필요) 경고가 하나라도 있으면 빨강, 그 외 이상이 있으면 노랑."""
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


def _stages(p: str) -> list[str]:
    """공정 흐름 순서의 조 종류 (폭기조1~5, 반응조1~3 은 노드 하나)."""
    return list(dict.fromkeys(stage for _, stage, _ in tanks_of(p)))


def _stage_name(stage: str) -> str:
    return stage.replace("유기침전조", "침전조").replace("무기침전조", "침전조")


def _ikey(x: dict) -> tuple:
    return (x["bldg"], x["proc"], x["line"], x["stage"])


def _now(plant, x: dict) -> tuple[int, int]:
    """사고의 '지금' 가장 심한 경고 (순위, 센서). 이미 풀린 경고(조회 구간 안 과거)는 빼고 판단."""
    best, pick = (True, NONE_RANK), x["sids"][0]
    for i in x["sids"]:
        for k in plant.active_kinds(i):                      # 빨강(조치 필요)을 순위보다 먼저 봄
            cand = (KIND[k]["sev"] != "red", KIND[k]["rank"])
            if cand < best:
                best, pick = cand, i
    return (best[1], pick) if best[1] < NONE_RANK else (x["rank"], x["sids"][0])


def _what(plant, x: dict) -> tuple[str, int]:
    """사고의 현상 한마디와 대표 센서."""
    rank, i = _now(plant, x)
    m = plant.meta.iloc[i]
    v = plant.V[i, -1]
    low = (not np.isnan(plant.lsl[i])) and v < (plant.lsl[i] + plant.usl[i]) / 2
    what = {
        "SPEC": ("농도 급감 · 하한 이탈" if m.param == "DO" else "하한 이탈") if low else "상한 초과",
        "NEAR": "하한 근접" if low else "상한 근접",
        "HOLD": "값 고정 1시간+ (센서·통신 확인)", "STD": "변동 급증", "VALVE": "개도-투입 불일치 (막힘·펌프 의심)",
        "AIR": "DO 하락 · 공기개도 상승 (산기관 의심)", "RATIO": "고분자 부족 (약품 대비)", "PEER": "동료 대비 이탈",
    }[kind_by_rank(rank)]
    return what, i


def _ago(plant, t) -> str:
    mins = int((plant.idx[-1] - t).total_seconds() // 60) + STEP_MIN
    return f"{mins}분째" if mins < 60 else f"{mins // 60}시간 {mins % 60:02d}분째"


def _val(plant, i: int) -> str:
    m = plant.meta.iloc[i]
    return f"{plant.V[i, -1]:.{int(m.dec)}f} {m.unit}"


# ── 선택: 목록 버튼 / 맵의 점 / 타임라인의 점 → st.session_state["ov_sel"] 하나 ──
# 차트는 한 번 누른 점을 계속 '선택됨'으로 들고 있으므로, 다른 곳에서 선택하면 그 차트의 키를 바꿔 선택을 비운다.
def _bump(*charts: str):
    for c in charts:
        st.session_state[f"_gen_{c}"] = st.session_state.get(f"_gen_{c}", 0) + 1


def _chart_key(c: str) -> str:
    return f"ov_{c}_{st.session_state.get(f'_gen_{c}', 0)}"


def _select(kind: str, key: tuple):
    st.session_state["ov_sel"] = (kind, tuple(key))
    _bump("map", "canvas")


def _clicked(c: str) -> tuple | None:
    ev = st.session_state.get(_chart_key(c))
    try:
        pts = ev["selection"]["points"] if ev else []
    except (KeyError, TypeError):
        pts = []
    for pt in pts:
        cd = pt.get("customdata")
        cd = cd[0] if isinstance(cd, (list, tuple)) else cd
        if isinstance(cd, str) and "|" in cd:
            return tuple(cd.split("|"))
    return None


def _resolve_selection(order: list[dict]):
    """맵·타임라인 클릭을 반영하고 지금 선택을 돌려줌. ('inc' | 'cell', (동, 공정, 계열, 조 종류)). 없으면 가장 시급한 사고."""
    keys = {_ikey(x) for x in order}
    for c, other in (("map", "canvas"), ("canvas", "map")):
        cd = _clicked(c)
        if cd and (st.session_state.get("ov_sel") or (None, None))[1] != cd:
            st.session_state["ov_sel"] = ("inc" if cd in keys else "cell", cd)
            _bump(other)
    sel = st.session_state.get("ov_sel")
    if sel and sel[0] == "inc" and tuple(sel[1]) not in keys:
        sel = ("cell", tuple(sel[1]))                          # 조회 구간에서 사라진 사고 → 그 위치만 계속 보여 줌
    if not sel and order:
        sel = ("inc", _ikey(order[0]))
    return sel


def _summary(plant, act: list[dict]):
    """⓪ 상황 한 줄."""
    n_red = sum(_sev(_now(plant, x)[0]) == "red" for x in act)
    n_ok = int((plant.now_rank >= NONE_RANK).sum())
    if act:
        x = act[0]
        what, i = _what(plant, x)
        m = plant.meta.iloc[i]
        lead = (f'가장 급한 것<b>{x["bldg"]} {x["proc"]} {x["line"]} {m.tank} — {m.param} {what} '
                f'<span style="color:{SEV_INK[_sev(_now(plant, x)[0])]}">{_val(plant, i)}</span> · {_ago(plant, x["first"])}</b>')
    else:
        lead = "<b>전 공정 정상 — 진행 중인 이상점 없음</b>"
    st.markdown(
        f'<div class="sum"><div class="k red"><i>{n_red}</i><span>조치 필요</span></div>'
        f'<div class="k yellow"><i>{len(act) - n_red}</i><span>확인 필요</span></div>'
        f'<div class="k ok"><i>{n_ok}</i><span>/ {plant.n} 센서 정상</span></div>'
        f'<div class="lead">{lead}</div>'
        f'<div class="at">데이터 기준<b>{plant.idx[-1]:%m/%d %H:%M}</b>{STEP_MIN}분 평균</div></div>',
        unsafe_allow_html=True,
    )


def _plant_map(plant, sel_cell: tuple | None) -> go.Figure:
    """① 플랜트 맵: 공정마다 한 줄, 조 종류 = 노드. 노드 안 점 행렬 = 세로 동(1~3) × 가로 계열(A~D)."""
    grp = plant.meta.groupby(["proc", "stage", "bldg", "line"], sort=False).indices
    nw, total, dx, dy = 1.0, 5.9, 0.17, 0.165                    # 노드 폭, 한 줄 전체 폭, 점 간격(가로·세로)
    dots = dict(x=[], y=[], c=[], s=[], lw=[], cd=[], hv=[])
    txt = {k: dict(x=[], y=[], t=[], c=[]) for k in ("title", "count", "row", "col", "lane", "imp")}

    def put(k, x, y, t, c="#0f172a"):
        d = txt[k]
        d["x"].append(x); d["y"].append(y); d["t"].append(t); d["c"].append(c)

    fig = go.Figure()
    for pi, p in enumerate(PROCESSES):
        sts = _stages(p)
        gap = (total - len(sts) * nw) / (len(sts) - 1)              # 줄마다 노드 수가 달라도 양 끝을 맞춤
        lane_sev = "green"
        for si, stage in enumerate(sts):
            x0 = si * (nw + gap)
            node_sev, n_bad = "green", 0
            for bi, b in enumerate(BUILDINGS):
                put("row", x0 + 0.27, pi + 0.03 + bi * dy, b, "#94a3b8")
                for li, l in enumerate(LINES):
                    ids = grp[(p, stage, b, l)]
                    sv, j = _sev_ids(plant, ids)
                    bad = int((plant.now_rank[ids] < NONE_RANK).sum())
                    n_bad += bad
                    if sv == "red" or (sv == "yellow" and node_sev == "green"):
                        node_sev = sv
                    picked = sel_cell == (b, p, l, stage)
                    dots["x"].append(x0 + 0.37 + li * dx)
                    dots["y"].append(pi + 0.03 + bi * dy)
                    dots["c"].append(QUIET if sv == "green" else SEV_COLOR[sv])
                    dots["s"].append(18 if picked else (15 if sv != "green" else 8))
                    dots["lw"].append(3 if picked else 0)
                    dots["cd"].append("|".join((b, p, l, stage)))
                    if j is None:
                        dots["hv"].append(f"{b} · {p} · {l} · {_stage_name(stage)}<br>정상 (센서 {len(ids)}개)")
                    else:
                        m = plant.meta.iloc[j]
                        dots["hv"].append(f"<b>{b} · {p} · {l} · {_stage_name(stage)}</b><br>{SEV_TEXT[sv]} · 이상 {bad}/{len(ids)}"
                                          f"<br>{m.tank} {m.param} {_val(plant, j)} — {_status_text(int(plant.now_rank[j]))}")
            for li, l in enumerate(LINES):
                put("col", x0 + 0.37 + li * dx, pi - 0.13, l[0], "#94a3b8")
            if node_sev == "red" or (node_sev == "yellow" and lane_sev == "green"):
                lane_sev = node_sev
            bad_node = node_sev != "green"
            fig.add_shape(type="rect", x0=x0, x1=x0 + nw, y0=pi - 0.46, y1=pi + 0.47, layer="below",
                          fillcolor={"red": "#fef2f2", "yellow": "#fffbeb", "green": "#ffffff"}[node_sev],
                          line=dict(color=SEV_COLOR[node_sev] if bad_node else "#cbd5e1", width=2.5 if bad_node else 1))
            put("title", x0 + 0.05, pi - 0.32, f"<span style='color:#94a3b8'>{si + 1:02d}</span> <b>{_stage_name(stage)}</b>")
            if n_bad:
                put("count", x0 + nw - 0.05, pi - 0.32, f"이상 <b>{n_bad}</b>", SEV_INK[node_sev])
            if si < len(sts) - 1:                                       # 영향 화살표: 앞 단계가 이상이면 주황/빨강
                c = IMPACT_COLOR[node_sev]
                fig.add_annotation(x=x0 + nw + gap - 0.03, y=pi, ax=x0 + nw + 0.03, ay=pi, xref="x", yref="y", axref="x", ayref="y",
                                   showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=3 if bad_node else 2, arrowcolor=c, text="")
                if bad_node:
                    put("imp", x0 + nw + gap / 2, pi - 0.14, "<b>영향</b>", c)
        put("lane", -0.1, pi - 0.1, f"<b>{p}</b>")
        put("lane", -0.1, pi + 0.16, f"<span style='font-size:11px'>● {SEV_TEXT[lane_sev]}</span>", SEV_INK[lane_sev] if lane_sev != "green" else "#16a34a")

    fig.add_trace(go.Scatter(
        x=dots["x"], y=dots["y"], mode="markers", customdata=dots["cd"], hovertext=dots["hv"], hoverinfo="text", showlegend=False,
        marker=dict(symbol="square", size=dots["s"], color=dots["c"], opacity=1, line=dict(color="#0f172a", width=dots["lw"])),
        selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1))))
    for k, pos, size in (("title", "middle right", 12.5), ("count", "middle left", 11.5), ("row", "middle left", 9.5),
                         ("col", "middle center", 9.5), ("lane", "middle left", 16), ("imp", "middle center", 10.5)):
        d = txt[k]
        fig.add_trace(go.Scatter(x=d["x"], y=d["y"], mode="text", text=d["t"], textposition=pos, hoverinfo="skip", showlegend=False,
                                 textfont=dict(size=size, color=d["c"])))
    fig.update_xaxes(range=[-0.62, total + 0.03], visible=False, fixedrange=True)
    fig.update_yaxes(range=[len(PROCESSES) - 0.5, -0.5], visible=False, fixedrange=True)
    fig.update_layout(height=MAP_LANE_PX * len(PROCESSES) + 8, margin=dict(l=0, r=0, t=4, b=4), hovermode="closest",
                      dragmode=False, clickmode="event+select", hoverlabel=dict(bgcolor="#ffffff", font_size=12.5))
    return style(fig)


def _priority(plant, act: list[dict], sel):
    """② 시급한 순 목록: 조치 필요 → 확인 필요. 줄 = 위치 / 현상 · 현재값 · 몇 분째."""
    if not act:
        st.markdown('<div class="ok-bar">전 공정 정상 — 진행 중인 이상점 없음</div>', unsafe_allow_html=True)
        return
    css, last = [], None
    sevs = [_sev(_now(plant, x)[0]) for x in act]
    for n, (x, sv) in enumerate(zip(act, sevs)):
        if sv != last:
            st.markdown(f'<div class="pg {sv}">{SEV_TEXT[sv]} · {sevs.count(sv)}건</div>', unsafe_allow_html=True)
            last = sv
        what, i = _what(plant, x)
        m = plant.meta.iloc[i]
        tanks = x["what"].split(" — ")[0]
        label = (f"**{x['bldg']} · {x['proc']} · {x['line']} · {tanks}**  \n"
                 f"{m.param} {what} — **{_val(plant, i)}** · {_ago(plant, x['first'])}")
        key = f"pl-{n}"
        st.button(label, key=key, on_click=_select, args=("inc", _ikey(x)), width="stretch")
        rule = f".st-key-{key} button{{border-left:7px solid {SEV_COLOR[sv]} !important;"
        if sel == ("inc", _ikey(x)):
            rule += "background:#ecfeff !important;outline:2px solid #0f172a;outline-offset:-2px;"
        css.append(rule + "}")
    st.markdown("<style>" + "".join(css) + "</style>", unsafe_allow_html=True)


def _canvas(plant, inc: list[dict], window: int, sel) -> go.Figure:
    """시간순 타임라인: 세로 = 공정·조(흐름 순서), 가로 = 시간. 사고마다 지속 막대 + 지금 점. 점을 누르면 선택."""
    used = {(it["proc"], it["stage"]) for it in inc}
    lanes = [(p, s) for p in PROCESSES for s in _stages(p) if (p, s) in used] or [(PROCESSES[0], _stages(PROCESSES[0])[0])]
    ypos = {ls: n for n, ls in enumerate(lanes)}
    x = plant.idx[-window:]
    step = x[1] - x[0]
    slot, count = {}, {}
    for it in inc:                                           # 같은 줄에 사고가 여럿이면 높이를 나눠 겹치지 않게
        ls = (it["proc"], it["stage"])
        slot[_ikey(it)] = count.get(ls, 0)
        count[ls] = count.get(ls, 0) + 1
    fig = go.Figure()
    for it in inc:
        sev = _sev(_now(plant, it)[0] if it["active"] else it["rank"])
        n_in = count[(it["proc"], it["stage"])]
        y = ypos[(it["proc"], it["stage"])] + (slot[_ikey(it)] - (n_in - 1) / 2) * min(0.24, 0.8 / n_in)
        key = "|".join(_ikey(it))
        color = SEV_COLOR[sev] if it["active"] else "#94a3b8"
        end = "" if it["active"] else f"{it['last']:%H:%M}"      # 사내 Python 3.11 이하에서도 되게 f-string 중첩 안 함
        hover = f"{it['title']}<br>{it['what']}<br>{_status_text(it['rank'])} · {it['first']:%H:%M}~{end}"
        # 지속 막대는 클릭·호버 대상에서 뺌: 선은 '선택'이 안 되는 종류라, 끝 점과 겹친 자리에서 선이 클릭을 가져가면 빈 선택이 됨
        fig.add_trace(go.Scatter(x=[it["first"], it["last"] + step], y=[y, y], mode="lines", line=dict(color=color, width=6),
                                 hoverinfo="skip", showlegend=False))
        picked = sel is not None and tuple(sel[1]) == _ikey(it)
        fig.add_trace(go.Scatter(x=[it["last"] + step], y=[y], mode="markers", customdata=[key], hovertext=[hover],
                                 hoverinfo="text", showlegend=False,
                                 marker=dict(size=14 if picked else (12 if it["active"] else 9),
                                             color=color if it["active"] else "#ffffff",
                                             line=dict(color="#0f172a" if picked else ("#ffffff" if it["active"] else "#94a3b8"),
                                                       width=3 if picked else 2))))
    fig.add_vline(x=x[-1] + step, line=dict(color="#0f172a", width=1, dash="dot"))
    for n in range(1, len(lanes)):
        if lanes[n][0] != lanes[n - 1][0]:                      # 공정 경계선
            fig.add_hline(y=n - 0.5, line=dict(color="#94a3b8", width=1))
    fig.update_yaxes(tickvals=list(range(len(lanes))), ticktext=[f"{p} · {_stage_name(s)}" for p, s in lanes],
                     range=[len(lanes) - 0.5, -0.5], showgrid=False, tickfont=dict(size=12, color="#0f172a"))
    fig.update_xaxes(range=[x[0], x[-1] + step * 6], tickformat="%H:%M" if window <= 288 else "%m/%d %H:%M")
    fig.update_layout(height=44 * len(lanes) + 50, margin=dict(l=8, r=8, t=8, b=8), hovermode="closest",
                      clickmode="event+select", dragmode=False)
    return style(fig)


def _detail(plant, sel, inc: list[dict], window: int):
    """③ 선택 상세: 선택한 사고(또는 맵에서 누른 위치)의 센서 추이를 한 줄에."""
    if not sel:
        return
    b, p, l, stage = sel[1]
    x = next((it for it in inc if _ikey(it) == tuple(sel[1])), None) if sel[0] == "inc" else None
    if x:
        what, i = _what(plant, x)
        sub = f"{plant.meta['param'].iat[i]} {what} · {_ago(plant, x['first'])} ({x['first']:%H:%M}부터)" if x["active"] else "해소됨"
        sids = x["sids"][:4]
    else:
        ids = plant.sel(bldg=b, proc=p, line=l, stage=stage)
        ids = ids[np.argsort(plant.now_rank[ids], kind="stable")]
        n_bad = int((plant.now_rank[ids] < NONE_RANK).sum())
        sub = f"이상 센서 {n_bad}개" if n_bad else "이상 없음"
        sids = [int(i) for i in ids[:4]]
    st.markdown(f'<div class="sec">선택 상세 — {b} · {p} · {l} · {_stage_name(stage)}<span>{sub} · 다른 곳을 보려면 맵의 점이나 목록을 누르세요</span></div>',
                unsafe_allow_html=True)
    for col, i in zip(st.columns(max(len(sids), 2)), sids):
        with col:
            st.markdown(_sensor_head(plant, i, window), unsafe_allow_html=True)
            st.plotly_chart(trend_figure(plant, i, window, 230), width="stretch", key=f"tr-{i}-{window}",
                            config={"displayModeBar": False})


def overview():
    plant, window = _ctx()
    all_inc = incidents(plant, window)
    # 시급한 순: 조치 필요(red) → 확인 필요, 같은 단계면 경고 순위 → 오래된 순
    act = sorted([x for x in all_inc if x["active"]],
                 key=lambda x: (_sev(_now(plant, x)[0]) != "red", _now(plant, x)[0], x["first"].value))
    sel = _resolve_selection(act + [x for x in all_inc if not x["active"]])

    _summary(plant, act)
    left, right = st.columns([1.75, 1], gap="medium")
    with left:
        st.markdown('<div class="sec" style="margin-top:4px">어디서<span>공정 흐름 → · 노드 안 점 = 세로 동(1~3) × 가로 계열(A~D) · '
                    '큰 색 점 = 이상 · 점을 누르면 아래에 상세</span></div>', unsafe_allow_html=True)
        st.plotly_chart(_plant_map(plant, tuple(sel[1]) if sel else None), width="stretch", key=_chart_key("map"),
                        on_select="rerun", selection_mode="points", config={"displayModeBar": False})
    with right:
        st.markdown(f'<div class="sec" style="margin-top:4px">무엇부터<span>진행 중 {len(act)}건 · 시급한 순</span></div>',
                    unsafe_allow_html=True)
        with st.container(height=MAP_LANE_PX * len(PROCESSES) + 4, border=False, key="plist"):
            _priority(plant, act, sel)

    _detail(plant, sel, all_inc, window)
    # 타임라인은 스위치를 켰을 때만 그림 (안 볼 때는 그리는 비용이 없음)
    if st.toggle(f"시간 순으로 보기 — 이상점 타임라인 ({len(all_inc)}건, 막대 = 지속 시간, 점을 누르면 선택)", key="ov_tl"):
        st.plotly_chart(_canvas(plant, all_inc, window, sel), width="stretch", key=_chart_key("canvas"), on_select="rerun",
                        selection_mode="points", config={"displayModeBar": False})
        _legend()


# ───────────────────────── 2. 공정 상세 ─────────────────────────
# 조 = 누를 수 있는 탱크(버튼), 탱크 사이는 배관(→)으로 이어 공정 흐름을 그대로 보여 줌. 카드·이모지 없음.
def _toggle_node(line: str, tank: str):
    s = set(st.session_state.get("proc_open", set()))
    s ^= {(line, tank)}
    st.session_state["proc_open"] = s


def _set_open(nodes):
    st.session_state["proc_open"] = set(nodes)


def process():
    plant, window = _ctx()
    _header("공정 상세", "계열별 공정 흐름 — 이상 있는 조는 자동으로 펼쳐지고, 탱크를 누르면 그래프가 펼쳐지거나 접혀요")

    jump = st.session_state.pop("_jump", None)
    if jump:
        st.session_state["proc_b"], st.session_state["proc_p"] = jump

    c = st.columns([1, 1, 1.3, 1.3, 2], vertical_alignment="bottom")
    b = c[0].selectbox("건물", BUILDINGS, key="proc_b")
    p = c[1].selectbox("공정", PROCESSES, key="proc_p")
    tanks = tanks_of(p)
    dec = plant.meta["dec"].to_numpy()

    # 조(노드)별 상태 · 현재값
    info = {}
    for l in LINES:
        for tank, stage, params in tanks:
            vals, worst = [], NONE_RANK
            for prm in params:
                i = plant.find(b, p, l, tank, prm)
                worst = min(worst, int(plant.now_rank[i]))
                vals.append((prm, plant.V[i, -1], int(dec[i]), bool(plant.active_kinds(i))))
            info[(l, tank)] = (worst, vals)
    abnormal = [k for k, (w, _) in info.items() if w < NONE_RANK]

    if st.session_state.get("_last_proc") != (b, p):          # 공정을 바꾸면 이상 있는 조를 모두 펼침
        st.session_state["_last_proc"] = (b, p)
        st.session_state["proc_open"] = set(abnormal)
    opened = st.session_state.get("proc_open", set())

    c[2].button("이상 조 모두 펼치기", on_click=_set_open, args=(abnormal,), width="stretch")
    c[3].button("모두 접기", on_click=_set_open, args=([],), width="stretch")

    css = []
    for li, l in enumerate(LINES):
        ws = [info[(l, t[0])][0] for t in tanks]
        n_bad = sum(w < NONE_RANK for w in ws)
        extra = f" · 이상 {n_bad}개 조" if n_bad else ""
        st.markdown(f'<div class="lh"><b>{l}</b><span style="color:{_color(min(ws))}">{_status_text(min(ws))}{extra}</span></div>',
                    unsafe_allow_html=True)
        cols = st.columns(len(tanks), gap="small")
        for ti, (tank, stage, params) in enumerate(tanks):
            w, vals = info[(l, tank)]
            # 탱크 이름은 기울임(*) → CSS 로 굵은 머리글, 이상 항목은 굵게(**) → CSS 로 그 탱크의 경고 색
            label = f"*{tank}*  \n" + "  \n".join(
                f"**{prm} {v:.{d}f}**" if bad else f"{prm} {v:.{d}f}" for prm, v, d, bad in vals
            )
            key = f"nd-{li}-{ti}"
            with cols[ti]:
                st.button(label, key=key, on_click=_toggle_node, args=(l, tank), width="stretch")
            col = _color(w)
            is_open = (l, tank) in opened
            edge = col if w < NONE_RANK else "#475569"                # 정상 탱크는 조용하게 (색 띠 없음)
            rule = (f".st-key-{key} button{{border:2px solid {edge} !important;"
                    f"border-left:{8 if w < NONE_RANK else 2}px solid {edge} !important;"
                    f"{'background:#ecfeff !important;' if is_open else ''}}}"
                    f".st-key-{key} button strong{{color:{col};}}")
            if ti == len(tanks) - 1:                                   # 마지막 탱크 뒤에는 배관 없음
                rule += f".st-key-{key}::before,.st-key-{key}::after{{display:none;}}"
            css.append(rule)

        for tank, stage, params in tanks:                          # 펼친 조의 그래프를 해당 계열 바로 아래에
            if (l, tank) in opened:
                st.markdown(f'<div class="xh">{b} · {p} · {l} · <b>{tank}</b></div>', unsafe_allow_html=True)
                for col_, prm in zip(st.columns(len(params)), params):
                    with col_:
                        _sensor_card(plant, plant.find(b, p, l, tank, prm), window, height=230)
    st.markdown("<style>" + "".join(css) + "</style>", unsafe_allow_html=True)
    _legend()


# ───────────────────────── 3. 한눈에 비교 ─────────────────────────
def compare():
    plant, window = _ctx()
    _header("한눈에 비교", "같은 항목을 계열 × 조로 펼쳐서, 클릭 없이 혼자 튀는 센서를 찾기")

    c = st.columns([1, 1, 2], vertical_alignment="bottom")
    b = c[0].selectbox("건물", BUILDINGS, key="cmp_b")
    p = c[1].selectbox("공정", PROCESSES, key="cmp_p")
    full = c[2].toggle("규격선까지 보이게 스케일 확대 (끄면 데이터에 맞춰 확대)", value=False, key="cmp_full")

    tanks = tanks_of(p)
    params = list(dict.fromkeys(prm for _, _, ps in tanks for prm in ps))
    n_cols = [sum(prm_ in t[2] for t in tanks) for prm_ in params]
    prm = st.radio("항목", params, index=int(np.argmax(n_cols)), horizontal=True, key=f"cmp_prm_{p}")  # 기본: 그래프가 가장 많은 항목
    cols = [t for t in tanks if prm in t[2]]
    nr, nc = len(LINES), len(cols)

    titles = []
    for l in LINES:
        for tank, _, _ in cols:
            i = plant.find(b, p, l, tank, prm)
            ks = plant.active_kinds(i)
            mark = f" <span style='color:{KIND[ks[0]]['color']}'>■ {_kind_name(ks[0])}</span>" if ks else ""
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
                                     hovertemplate="%{x|%H:%M}  <b>%{y:.2f}</b><extra></extra>"), row=r, col=ci)
            for kind, size in (("NEAR", 4), ("SPEC", 5)):
                mk = plant.F[kind][i, -window:]
                if mk.any():
                    fig.add_trace(go.Scatter(x=x[mk], y=y[mk], mode="markers", marker=dict(color=KIND[kind]["color"], size=size),
                                             showlegend=False, hoverinfo="skip"), row=r, col=ci)
            if not np.isnan(plant.lsl[i]):
                fig.add_hline(y=plant.lsl[i], line=dict(color="#ef4444", width=1, dash="dot"), row=r, col=ci)
            fig.add_hline(y=plant.usl[i], line=dict(color="#ef4444", width=1, dash="dot"), row=r, col=ci)

    # 같은 열(같은 종류의 조)은 y축 범위를 맞춤
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
    st.plotly_chart(style(fig), width="stretch", key=f"cmp-{b}-{p}-{prm}-{window}-{full}", config={"displayModeBar": False})
    st.caption(
        "같은 열 = 같은 종류의 조라 y축을 맞췄어요. 한 줄(계열)이 다른 줄들과 다르게 움직이면 이상 후보예요. "
        "선 색 = 현재 상태(청록=정상) · 붉은 점선 = LSL/USL · 세로 음영 = 경고 구간(색은 경고 종류, 위쪽 '기준' 참고)"
    )


# ───────────────────────── 4. 경고 센터 ─────────────────────────
# 카드 목록 대신: 위에 시간축 알람 타임라인(사고마다 언제부터 얼마나), 아래에 선으로 구분한 사고별 그래프 목록.
def _timeline(plant, inc: list[dict], window: int) -> go.Figure:
    x = plant.idx[-window:]
    step = x[1] - x[0]
    labels, seen = [], set()
    for n, it in enumerate(inc):
        what = it["what"] if len(it["what"]) <= 28 else it["what"][:27] + "…"
        lab = f"{it['title']} · {what}"
        labels.append(lab if lab not in seen else f"{lab} ({n})")
        seen.add(labels[-1])
    fig = go.Figure()
    for kind in sorted(KIND, key=lambda k: -KIND[k]["rank"]):        # 덜 심한 것부터 그려서 심한 게 위에 보이게
        xs, ys = [], []
        for lab, it in zip(labels, inc):
            mask = plant.F[kind][it["sids"], -window:].any(axis=0)
            for s0, s1 in _spans(mask, x):
                xs += [s0, s1 + step, None]
                ys += [lab, lab, None]
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=KIND[kind]["color"], width=11),
                                     name=_kind_name(kind), hovertemplate=f"{_kind_name(kind)}<br>%{{x|%m/%d %H:%M}}<extra></extra>"))
    fig.add_vline(x=x[-1], line=dict(color="#1e293b", width=1, dash="dot"))
    fig.update_yaxes(categoryorder="array", categoryarray=labels, autorange="reversed", showgrid=True,
                     gridcolor="rgba(15,23,42,.06)", tickfont=dict(size=12, color="#0f172a"))
    fig.update_xaxes(tickformat="%H:%M" if window <= 288 else "%m/%d %H:%M", range=[x[0], x[-1] + step])
    fig.update_layout(height=26 * len(inc) + 80, margin=dict(l=8, r=8, t=30, b=8),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, font=dict(size=11), traceorder="reversed"))
    return style(fig)


def alerts():
    plant, window = _ctx()
    _header("경고 센터", "사고(같은 계열·같은 조) 단위 — 위 타임라인으로 언제부터인지 보고, 아래로 스크롤하며 그래프 확인")
    inc = incidents(plant, window)
    if not inc:
        st.success(f"최근 {st.session_state.get('range', '24시간')} 동안 경고가 없습니다.")
        return

    f = st.columns([2.6, 1, 1, 1.2], vertical_alignment="bottom")
    kinds = f[0].multiselect("경고 유형", list(KIND), default=list(KIND), format_func=_kind_name)
    bld = f[1].selectbox("건물", ["전체"] + BUILDINGS)
    prc = f[2].selectbox("공정", ["전체"] + PROCESSES)
    only_active = f[3].toggle("진행 중만", value=True)

    def keep(x):
        if bld != "전체" and x["bldg"] != bld:
            return False
        if prc != "전체" and x["proc"] != prc:
            return False
        if only_active and not x["active"]:
            return False
        return bool(set(x["ev"]["kind"]) & set(kinds))

    inc = [x for x in inc if keep(x)]
    if not inc:
        st.info("조건에 맞는 경고가 없습니다.")
        return
    n_act = sum(x["active"] for x in inc)
    st.markdown(f'<div class="sec">알람 타임라인<span>사고 {len(inc)}건 · 진행 중 {n_act} · 해소 {len(inc) - n_act} · 점선 = 지금</span></div>',
                unsafe_allow_html=True)
    st.plotly_chart(_timeline(plant, inc, window), width="stretch", key=f"tl-{window}-{len(inc)}", config={"displayModeBar": False})

    st.markdown('<div class="sec">사고별 그래프<span>아래로 스크롤하며 확인</span></div>', unsafe_allow_html=True)
    _legend()
    shown = st.session_state.setdefault("_alert_n", 8)
    for x in inc[:shown]:
        ks = " · ".join(f'<span style="color:{KIND[k]["color"]}">{_kind_name(k)}</span>'
                        for k in sorted(set(x["ev"]["kind"]), key=lambda k: KIND[k]["rank"]))
        st.markdown(
            f'<div class="ih" style="--c:{_color(x["rank"])}"><span class="t">{x["first"]:%H:%M} → {x["last"]:%H:%M}</span>'
            f'<b>{x["title"]}</b><span class="w">{x["what"]}</span>'
            f'<span class="g">{"진행 중" if x["active"] else "해소됨"}</span><span class="ks">{ks}</span></div>',
            unsafe_allow_html=True,
        )
        _incident_charts(plant, x, window, "a")
    if shown < len(inc):
        if st.button(f"더 보기 ({len(inc) - shown}건 남음)"):
            st.session_state["_alert_n"] = shown + 8
            st.rerun()

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
# 공정 흐름 중심 (사용자 디자인 지시서, 2026-11-04): 3초 안에 어느 공정이 이상인지 보이게.
#   ① 주요 이상점 요약 바(이벤트 스택) → ② 공정 흐름 노드(신호등 + 글로우 + 영향 화살표)
#   → ③ 이상점 요약 캔버스(시간축) → ④ 공정 상세 트렌드.
#   바·노드·캔버스 점 중 어느 것을 눌러도 같은 '선택'으로 묶여 노드 강조와 아래 트렌드가 함께 바뀜.
SEV_COLOR = {"red": "#dc2626", "yellow": "#f59e0b", "green": "#16a34a"}
SEV_TEXT = {"red": "조치 필요", "yellow": "확인 필요", "green": "정상"}
IMPACT_COLOR = {"red": "#dc2626", "yellow": "#f97316", "green": "#94a3b8"}   # 다음 단계로 가는 화살표
BANNER_N = 5


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


def _now(plant, x: dict) -> tuple[int, str]:
    """사고의 '지금' 가장 심한 경고 (순위, 센서). 이미 풀린 경고(조회 구간 안 과거)는 빼고 판단."""
    best, pick = (True, NONE_RANK), x["sids"][0]
    for i in x["sids"]:
        for k in plant.active_kinds(i):                      # 빨강(조치 필요)을 순위보다 먼저 봄
            cand = (KIND[k]["sev"] != "red", KIND[k]["rank"])
            if cand < best:
                best, pick = cand, i
    return (best[1], pick) if best[1] < NONE_RANK else (x["rank"], x["sids"][0])


def _headline(plant, x: dict) -> str:
    """이상점 요약 문장: [STAGE nn] 공정 조 · 위치 항목 현상 (현재값 단위)."""
    rank, i = _now(plant, x)
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
    n = _stages(m.proc).index(m.stage) + 1
    return (f"[STAGE {n:02d}] {m.proc} {_stage_name(m.stage)} · {m.bldg} {m.line} {m.tank} {m.param} {what} "
            f"({v:.{int(m.dec)}f} {m.unit})")


def _select(kind: str, key: tuple):
    st.session_state["ov_sel"] = (kind, key)


def _resolve_selection(inc: list[dict]):
    """캔버스 점 클릭을 반영하고, 지금 선택(사고 또는 노드)을 돌려줌. 없으면 가장 시급한 사고."""
    ev = st.session_state.get("ov_canvas")
    try:
        pts = ev["selection"]["points"] if ev else []
    except (KeyError, TypeError):
        pts = []
    if pts:
        cd = pts[0].get("customdata")
        cd = cd[0] if isinstance(cd, (list, tuple)) else cd
        if cd and cd != st.session_state.get("_ov_canvas_last"):   # 새로 누른 점만 반영 (바·노드 클릭을 덮어쓰지 않게)
            st.session_state["_ov_canvas_last"] = cd
            st.session_state["ov_sel"] = ("inc", tuple(cd.split("|")))
    sel = st.session_state.get("ov_sel")
    if sel and sel[0] == "inc" and not any(_ikey(x) == tuple(sel[1]) for x in inc):
        sel = None
    if not sel and inc:
        sel = ("inc", _ikey(inc[0]))
    return sel


def _banner(plant, act: list[dict], sel):
    """① 주요 이상점 요약 바: 시급한 순(조치 필요 → 확인 필요). 누르면 그 이상점으로 아래 전체가 연동."""
    css = []
    if not act:
        st.markdown('<div class="ok-bar">전 공정 정상 — 진행 중인 이상점 없음</div>', unsafe_allow_html=True)
        return
    for n, x in enumerate(act[:BANNER_N]):
        sev = _sev(_now(plant, x)[0])
        key = f"bn-{n}"
        st.button(("🚨 " if sev == "red" else "⚠ ") + _headline(plant, x) + f" — {SEV_TEXT[sev]}",
                  key=key, on_click=_select, args=("inc", _ikey(x)), width="stretch")
        bg = "#dc2626" if sev == "red" else "#b45309"
        rule = f".st-key-{key} button{{background:{bg} !important;"
        if sev == "red":
            rule += "animation:pulseR 1.8s ease-in-out infinite;"
        if sel == ("inc", _ikey(x)):
            rule += "outline:3px solid #0f172a;outline-offset:2px;"
        css.append(rule + "}")
    if len(act) > BANNER_N:
        st.caption(f"외 {len(act) - BANNER_N}건 진행 중 — 아래 캔버스와 경고 센터에서 모두 볼 수 있어요")
    st.markdown("<style>" + "".join(css) + "</style>", unsafe_allow_html=True)


def _flow(plant, bsel: str | None, sel_node: tuple | None):
    """② 공정 흐름 노드: 공정마다 한 줄, 조 종류 = 노드(신호등), 노드 사이 화살표 = 앞 단계의 영향."""
    css = []
    for pi, p in enumerate(PROCESSES):
        stages = _stages(p)
        widths = [0.75] + sum(([1, 0.3] for _ in stages), [])[:-1]
        cols = st.columns(widths, vertical_alignment="center", gap="small")
        lane = plant.sel(proc=p, **({"bldg": bsel} if bsel else {}))
        lsev = _sev_ids(plant, lane)[0]
        cols[0].markdown(f'<div class="ln2">{p}<small style="color:{SEV_COLOR[lsev]}">● {SEV_TEXT[lsev]}</small></div>',
                         unsafe_allow_html=True)
        for si, stage in enumerate(stages):
            ids = plant.sel(proc=p, stage=stage, **({"bldg": bsel} if bsel else {}))
            sev, j = _sev_ids(plant, ids)
            n_bad = int((plant.now_rank[ids] < NONE_RANK).sum())
            label = f"*STAGE {si + 1:02d} · {_stage_name(stage)}*  \n**● {SEV_TEXT[sev]}**  \n이상 {n_bad} / {len(ids)}"
            if j is not None:
                m = plant.meta.iloc[j]
                label += f"  \n{m.bldg} {m.line[0]} {m.tank} {m.param} {plant.V[j, -1]:.{int(m.dec)}f}"
            key = f"fn-{pi}-{si}"
            cols[1 + 2 * si].button(label, key=key, on_click=_select, args=("node", (p, stage)), width="stretch")
            rule = {
                "red": "border:2px solid #dc2626 !important;background:#fef2f2 !important;animation:glowR 1.8s ease-in-out infinite;",
                "yellow": "border:2px solid #f59e0b !important;background:#fffbeb !important;animation:glowY 2.2s ease-in-out infinite;",
                "green": "border:1px solid #cbd5e1 !important;background:#ffffff !important;",
            }[sev]
            if sel_node == (p, stage):
                rule += "outline:3px solid #0f172a;outline-offset:3px;"
            strong = {"red": "#dc2626", "yellow": "#b45309", "green": "#16a34a"}[sev]
            css.append(f".st-key-{key} button{{{rule}}}.st-key-{key} button strong{{color:{strong};}}")
            if si < len(stages) - 1:                          # 영향 화살표: 앞 단계(이 노드)가 이상이면 주황/빨강
                c = IMPACT_COLOR[sev]
                cols[2 + 2 * si].markdown(f'<div class="fa" style="--c:{c}"><b>{"영향" if sev != "green" else ""}</b><i></i></div>',
                                          unsafe_allow_html=True)
    st.markdown("<style>" + "".join(css) + "</style>", unsafe_allow_html=True)


def _canvas(plant, inc: list[dict], window: int, sel) -> go.Figure:
    """③ 이상점 요약 캔버스: 세로 = 공정·조(흐름 순서), 가로 = 시간. 사고마다 지속 막대 + 지금 점. 점을 누르면 선택."""
    used = {(it["proc"], it["stage"]) for it in inc}
    lanes = [(p, s) for p in PROCESSES for s in _stages(p) if (p, s) in used] or [(PROCESSES[0], _stages(PROCESSES[0])[0])]
    ypos = {ls: n for n, ls in enumerate(lanes)}
    x = plant.idx[-window:]
    step = x[1] - x[0]
    # 같은 줄(공정·조)에 사고가 여럿이면 높이를 하나씩 나눠 줌 → 점이 겹치지 않아 따로 누를 수 있음
    slot, count = {}, {}
    for it in inc:
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
        fig.add_trace(go.Scatter(x=[it["first"], it["last"] + step], y=[y, y], mode="lines", line=dict(color=color, width=6),
                                 customdata=[key, key], hovertext=[hover, hover], hoverinfo="text", showlegend=False))
        picked = sel == ("inc", _ikey(it))                     # 선택된 점은 굵은 검정 테두리 (덮는 원을 따로 그리면 옆 점 클릭을 가로챔)
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
    fig.update_layout(height=58 * len(lanes) + 50, margin=dict(l=8, r=8, t=8, b=8), hovermode="closest",
                      clickmode="event+select", dragmode=False)
    return style(fig)


def _detail(plant, sel, inc: list[dict], window: int, bsel: str | None):
    """④ 공정 상세 트렌드: 선택된 이상점(또는 노드)의 센서 추이."""
    if sel and sel[0] == "inc":
        x = next(it for it in inc if _ikey(it) == tuple(sel[1]))
        title, sub = f"{x['title']} · {x['what']}", f"{_status_text(x['rank'])} · {x['first']:%H:%M}부터"
        sids = x["sids"][:4]
    elif sel and sel[0] == "node":
        p, stage = sel[1]
        ids = plant.sel(proc=p, stage=stage, **({"bldg": bsel} if bsel else {}))
        bad = [int(i) for i in ids[np.argsort(plant.now_rank[ids], kind="stable")] if plant.now_rank[i] < NONE_RANK]
        title = f"{p} · {_stage_name(stage)}" + (f" · {bsel}" if bsel else "")
        sub = f"이상 센서 {len(bad)}개" if bad else "이상 없음 — 첫 계열 센서를 보여 줌"
        sids = bad[:4] or [int(i) for i in ids[:2]]
    else:
        return
    st.markdown(f'<div class="sec">④ 공정 상세 트렌드<span>{title} — {sub}</span></div>', unsafe_allow_html=True)
    for k in range(0, len(sids), 2):
        for col, i in zip(st.columns(2), sids[k:k + 2]):
            with col:
                st.markdown(_sensor_head(plant, i, window), unsafe_allow_html=True)
                st.plotly_chart(trend_figure(plant, i, window), width="stretch", key=f"tr-{i}-{window}",
                                config={"displayModeBar": False})


def overview():
    plant, window = _ctx()
    all_inc = incidents(plant, window)
    # 시급한 순: 조치 필요(red) → 확인 필요, 같은 단계면 경고 순위 → 최근 시작
    act = sorted([x for x in all_inc if x["active"]],
                 key=lambda x: (_sev(_now(plant, x)[0]) != "red", _now(plant, x)[0], -x["first"].value))
    sel = _resolve_selection(act + [x for x in all_inc if not x["active"]])

    st.markdown('<div class="sec" style="margin-top:0">① 주요 이상점<span>시급한 순 · 누르면 아래 노드·캔버스·트렌드가 함께 바뀜</span></div>',
                unsafe_allow_html=True)
    _banner(plant, act, sel)

    head, filt = st.columns([3, 1.4], vertical_alignment="bottom")
    head.markdown('<div class="sec">② 공정 흐름<span>신호등: 초록 정상 · 노랑 확인 필요 · 빨강 조치 필요 · 화살표 색 = 앞 단계 이상의 영향</span></div>',
                  unsafe_allow_html=True)
    b = filt.segmented_control("동", ["전체"] + BUILDINGS, default="전체", key="ov_b", label_visibility="collapsed")
    bsel = None if b in (None, "전체") else b
    sel_node = (sel[1][1], sel[1][3]) if sel and sel[0] == "inc" else (tuple(sel[1]) if sel else None)
    _flow(plant, bsel, sel_node)

    shown = [x for x in all_inc if not bsel or x["bldg"] == bsel]
    st.markdown(f'<div class="sec">③ 이상점 요약 캔버스<span>{len(shown)}건 · 이상이 있었던 공정만 · 막대 = 지속 시간, 큰 점 = 지금 진행 중 · 점을 누르면 아래 트렌드로</span></div>',
                unsafe_allow_html=True)
    st.plotly_chart(_canvas(plant, shown, window, sel), width="stretch", key="ov_canvas", on_select="rerun",
                    selection_mode="points", config={"displayModeBar": False})

    _detail(plant, sel, all_inc, window, bsel)


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

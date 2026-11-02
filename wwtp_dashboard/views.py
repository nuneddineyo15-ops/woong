"""화면 3개: 종합 현황(공정 12개) → 공정 상세(계열·조 흐름) → 경고 센터(사고 묶음)."""
from __future__ import annotations

import numpy as np
import streamlit as st

from charts import sensor_figure
from core import (
    BUILDINGS, KIND, LINES, NONE_RANK, PROCESSES, STEP_MIN, get_plant, incidents, kind_by_rank, tanks_of,
)

RANGES = {"3시간": 36, "6시간": 72, "12시간": 144, "24시간": 288, "48시간": 576}
OK_COLOR, RESOLVED_COLOR, DIM = "#22c55e", "#64748b", "#cbd5e1"


# ───────────────────────── 공통 ─────────────────────────
def _ctx():
    return get_plant(), RANGES[st.session_state.get("range", "24시간")]


def _color(rank: int) -> str:
    return OK_COLOR if rank >= NONE_RANK else KIND[kind_by_rank(rank)]["color"]


def _status_text(rank: int) -> str:
    return "정상" if rank >= NONE_RANK else KIND[kind_by_rank(rank)]["label"].split("(")[0]


def _badges(kinds: list[str]) -> str:
    if not kinds:
        return f'<span style="color:{OK_COLOR};font-weight:700">● 정상</span>'
    return "&nbsp;&nbsp;".join(
        f'<span style="color:{KIND[k]["color"]};font-weight:700">● {KIND[k]["label"].split("(")[0]}</span>' for k in kinds
    )


def _legend():
    st.caption(
        "배경: 주황 = 상하한 근접 · 빨강 = 이탈  |  세로 음영: 파랑 = Hold · 보라 = σ 초과 · 분홍 = 동료 대비 이탈  |  "
        "회색 띠/점선 = 같은 항목 다른 센서의 범위/중앙값"
    )


def _header(title: str, sub: str):
    plant = get_plant()
    st.markdown(f"### {title}")
    st.caption(f"{sub}  |  데이터 기준 {plant.idx[-1]:%Y-%m-%d %H:%M} · {STEP_MIN}분 평균 (데모)")


def _sensor_card(plant, i: int, window: int, height: int = 240, tag: str = "", note: str = ""):
    m = plant.meta.iloc[i]
    kinds = plant.active_kinds(i)
    hist = [k for k in plant.window_kinds(i, window) if k not in kinds]
    cur = plant.V[i, -1]
    prev = plant.V[i, -13]
    with st.container(border=True):
        if tag:
            st.markdown(f"**{tag}**")
        c = st.columns([1.1, 1.5])
        c[0].metric(f"{m.param} ({m.unit})", f"{cur:.2f}", f"{cur - prev:+.2f} /1h", delta_color="off")
        with c[1]:
            st.markdown(
                _badges(kinds) if kinds or not hist else f'<span style="color:{RESOLVED_COLOR};font-weight:700">● 해소됨</span>',
                unsafe_allow_html=True,
            )
            line2 = f"규격 {plant.spec_text(i)}  ·  σ {np.nan_to_num(plant.std[i, -1]):.2f}"
            if hist:
                line2 += "  ·  이력: " + ", ".join(KIND[k]["label"].split("(")[0] for k in hist)
            st.caption(line2)
        if note:
            st.caption(note)
        st.plotly_chart(sensor_figure(plant, i, window, height), width="stretch",
                        key=f"c-{i}-{window}-{tag}", config={"displayModeBar": False})


# ───────────────────────── 1. 종합 현황 ─────────────────────────
def overview():
    plant, window = _ctx()
    _header("종합 현황", "3개 동 · 12개 공정 · 센서 전체를 한눈에")

    now = {k: int(plant.F[k][:, -1].sum()) for k in KIND}
    n_bad = int((plant.now_rank < NONE_RANK).sum())
    cols = st.columns(6)
    cols[0].metric("🟢 정상 / 전체 센서", f"{plant.n - n_bad} / {plant.n}")
    for c, k in zip(cols[1:], KIND):
        c.metric(f"{KIND[k]['icon']} {KIND[k]['label'].split('(')[0]}", f"{now[k]} 개")

    inc = [x for x in incidents(plant, window) if x["active"]]
    st.subheader("지금 확인할 곳")
    if not inc:
        st.success("진행 중인 경고가 없습니다. 전 공정 정상입니다.")
    else:
        st.caption(f"같은 계열·같은 조의 경고는 1건으로 묶었어요. 진행 중 {len(inc)}건")
        rows = "".join(
            f'<div class="ir"><span class="ik" style="color:{_color(x["rank"])}">● {_status_text(x["rank"])}</span>'
            f'<span class="it">{x["title"]}</span><span class="iw">{x["what"]}</span>'
            f'<span class="ic">센서 {len(x["sids"])}개</span><span class="id">{x["first"]:%H:%M}~</span></div>'
            for x in inc[:8]
        )
        st.markdown(f'<div class="ilist">{rows}</div>', unsafe_allow_html=True)
        if len(inc) > 8:
            st.caption(f"외 {len(inc) - 8}건 — 경고 센터에서 모두 볼 수 있어요")
        st.page_link(st.session_state["_pages"]["alerts"], label="경고 센터에서 그래프와 함께 보기", icon="🚨")

    st.subheader("공정 현황")
    st.caption("카드 = 공정 1개(계열 4개). A~D 칩의 색은 그 계열에서 가장 나쁜 센서 상태예요. [상세]를 눌러 내려가 보세요.")
    for b in BUILDINGS:
        st.markdown(f'<div class="bh">{b}</div>', unsafe_allow_html=True)
        cols = st.columns(4)
        for col, p in zip(cols, PROCESSES):
            ids = plant.sel(bldg=b, proc=p)
            r = plant.now_rank[ids]
            worst = int(r.min())
            n_b = int((r < NONE_RANK).sum())
            n_peer = int(plant.F["PEER"][ids, -1].sum())
            chips = ""
            for l in LINES:
                lr = int(plant.now_rank[plant.sel(bldg=b, proc=p, line=l)].min())
                chips += f'<span class="ln" style="background:{_color(lr)}33;border-color:{_color(lr)}">{l[0]}</span>'
            sub = f"이상 센서 <b>{n_b}</b> / {len(ids)}" + (f" · 조기경보 <b>{n_peer}</b>" if n_peer else "")
            with col:
                with st.container(border=True):
                    st.markdown(
                        f'<div class="pt"><b>{p}</b><span style="color:{_color(worst)}">● {_status_text(worst)}</span></div>'
                        f'<div class="pl">{chips}</div><div class="ps">{sub}</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("상세 ›", key=f"go-{b}-{p}", width="stretch"):
                        st.session_state["_jump"] = (b, p)
                        st.switch_page(st.session_state["_pages"]["process"])


# ───────────────────────── 2. 공정 상세 ─────────────────────────
def _node_html(plant, b, p, l, tank, params) -> tuple[str, int]:
    rows, worst = "", NONE_RANK
    for prm in params:
        i = plant.find(b, p, l, tank, prm)
        rk = int(plant.now_rank[i])
        worst = min(worst, rk)
        col = DIM if rk >= NONE_RANK else _color(rk)
        rows += f'<div class="nv" style="color:{col}"><span>{prm}</span><b>{plant.V[i, -1]:.2f}</b></div>'
    c = _color(worst)
    glow = f"box-shadow:0 0 10px {c}66;" if worst < NONE_RANK else ""
    return (
        f'<div class="nd" style="border-color:{c}aa;{glow}"><div class="nh"><span>{tank}</span>'
        f'<i style="background:{c}"></i></div>{rows}</div>'
    ), worst


def process():
    plant, window = _ctx()
    _header("공정 상세", "계열별 흐름도 — 색이 변한 조를 아래에서 선택해 센서 그래프를 확인하세요")

    jump = st.session_state.pop("_jump", None)
    if jump:
        st.session_state["proc_b"], st.session_state["proc_p"] = jump

    c = st.columns([1, 1, 3])
    b = c[0].selectbox("건물", BUILDINGS, key="proc_b")
    p = c[1].selectbox("공정", PROCESSES, key="proc_p")
    tanks = tanks_of(p)
    names = [t[0] for t in tanks]

    worst_of = (NONE_RANK, LINES[0], names[0])
    blocks = []
    for l in LINES:
        nodes, line_worst, n_bad = [], NONE_RANK, 0
        for tank, stage, params in tanks:
            html, w = _node_html(plant, b, p, l, tank, params)
            nodes.append(html)
            line_worst = min(line_worst, w)
            n_bad += w < NONE_RANK
            if w < worst_of[0]:
                worst_of = (w, l, tank)
        extra = f" · 이상 {n_bad}개 조" if n_bad else ""
        head = f'<div class="lh"><b>{l}</b><span style="color:{_color(line_worst)}">● {_status_text(line_worst)}{extra}</span></div>'
        blocks.append(head + f'<div class="fl" style="grid-template-columns:repeat({len(tanks)},1fr)">{"".join(nodes)}</div>')
    st.markdown("".join(blocks), unsafe_allow_html=True)

    if st.session_state.get("_last_proc") != (b, p):          # 공정을 바꾸면 가장 나쁜 조를 자동 선택
        st.session_state["_last_proc"] = (b, p)
        st.session_state["proc_l"], st.session_state["proc_t"] = worst_of[1], worst_of[2]
    st.divider()
    st.subheader("조 상세")
    s = st.columns([1.6, 4])
    l = s[0].radio("계열", LINES, key="proc_l", horizontal=True)
    t = s[1].radio("조", names, key="proc_t", horizontal=True)
    tank, stage, params = next(x for x in tanks if x[0] == t)
    cols = st.columns(len(params))
    for col, prm in zip(cols, params):
        with col:
            _sensor_card(plant, plant.find(b, p, l, tank, prm), window, height=260, tag=f"{b} · {p} · {l} · {tank}")
    _legend()


# ───────────────────────── 3. 경고 센터 ─────────────────────────
def alerts():
    plant, window = _ctx()
    _header("경고 센터", "사고(같은 계열·같은 조) 단위로 묶어서, 그래프와 함께 쭉 훑어보기")
    inc = incidents(plant, window)
    if not inc:
        st.success(f"최근 {st.session_state.get('range', '24시간')} 동안 경고가 없습니다.")
        return

    f = st.columns([2.6, 1, 1, 1.2], vertical_alignment="bottom")
    kinds = f[0].multiselect("경고 유형", list(KIND), default=list(KIND),
                             format_func=lambda k: f"{KIND[k]['icon']} {KIND[k]['label'].split('(')[0]}")
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
    st.caption(f"사고 {len(inc)}건 (진행 중 {n_act} · 해소 {len(inc) - n_act})  —  아래로 스크롤하며 확인하세요")
    _legend()

    shown = st.session_state.setdefault("_alert_n", 8)
    for x in inc[:shown]:
        ev = x["ev"]
        with st.container(border=True):
            top = st.columns([3, 2])
            tag = "진행 중" if x["active"] else "해소됨"
            top[0].markdown(
                f'#### <span style="color:{_color(x["rank"])}">●</span> {x["title"]}'
                f'<br><span style="font-size:13px;color:#94a3b8;font-weight:400">{x["what"]}  |  {tag}  |  '
                f'{x["first"]:%H:%M} → {x["last"]:%H:%M}</span>',
                unsafe_allow_html=True,
            )
            top[1].markdown(
                "<br>" + "&nbsp;&nbsp;".join(
                    f'<span style="color:{KIND[k]["color"]};font-weight:700">● {KIND[k]["label"].split("(")[0]}</span>'
                    for k in sorted(set(ev["kind"]), key=lambda k: KIND[k]["rank"])
                ),
                unsafe_allow_html=True,
            )
            sids = x["sids"][:3]
            for col, i in zip(st.columns(len(sids)), sids):
                with col:
                    m = plant.meta.iloc[i]
                    ks = ", ".join(KIND[k]["label"].split("(")[0] for k in plant.window_kinds(i, window))
                    st.caption(f"**{m.tank} · {m.param}**  —  {ks}")
                    st.plotly_chart(sensor_figure(plant, i, window, 210), width="stretch",
                                    key=f"a-{i}-{window}", config={"displayModeBar": False})
            if len(x["sids"]) > 3:
                st.caption("외 센서: " + ", ".join(
                    f"{plant.meta['tank'].iat[i]} {plant.meta['param'].iat[i]}" for i in x["sids"][3:]))
    if shown < len(inc):
        if st.button(f"더 보기 ({len(inc) - shown}건 남음)"):
            st.session_state["_alert_n"] = shown + 8
            st.rerun()

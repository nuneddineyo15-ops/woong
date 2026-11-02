"""화면 3개: 종합 현황(공정 12개) → 공정 상세(계열·조 흐름) → 경고 센터(사고 묶음)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from charts import _spans, sensor_figure, style
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
        st.caption(f"진행 중 {len(inc)}건 (같은 계열·같은 조의 경고는 1건으로 묶었어요) — 줄을 누르면 그래프가 펼쳐져요")
        all_open = st.toggle("진행 중 사고 모두 펼치기", value=False, key="ov_all_open")
        for n, x in enumerate(inc[:8]):
            label = (
                f"{KIND[kind_by_rank(x['rank'])]['icon']} {_status_text(x['rank'])}  ·  {x['title']}  ·  "
                f"{x['what']}  ·  센서 {len(x['sids'])}개  ·  {x['first']:%H:%M}~"
            )
            with st.expander(label, expanded=(all_open or n == 0)):
                _incident_charts(plant, x, window, f"ov{n}")
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
def _toggle_node(line: str, tank: str):
    s = set(st.session_state.get("proc_open", set()))
    s ^= {(line, tank)}
    st.session_state["proc_open"] = s


def _set_open(nodes):
    st.session_state["proc_open"] = set(nodes)


def process():
    plant, window = _ctx()
    _header("공정 상세", "계열별 흐름도 — 이상 있는 조는 자동으로 펼쳐지고, 박스를 누르면 펼침/접힘이 바뀌어요")

    jump = st.session_state.pop("_jump", None)
    if jump:
        st.session_state["proc_b"], st.session_state["proc_p"] = jump

    c = st.columns([1, 1, 1.3, 1.3, 2], vertical_alignment="bottom")
    b = c[0].selectbox("건물", BUILDINGS, key="proc_b")
    p = c[1].selectbox("공정", PROCESSES, key="proc_p")
    tanks = tanks_of(p)

    # 조(노드)별 상태 · 현재값
    info = {}
    for l in LINES:
        for tank, stage, params in tanks:
            vals, worst = [], NONE_RANK
            for prm in params:
                i = plant.find(b, p, l, tank, prm)
                worst = min(worst, int(plant.now_rank[i]))
                vals.append((prm, plant.V[i, -1]))
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
        st.markdown(
            f'<div class="lh"><b>{l}</b><span style="color:{_color(min(ws))}">● {_status_text(min(ws))}{extra}</span>'
            f'<span style="color:#475569;font-size:11px">흐름: 왼쪽 → 오른쪽</span></div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(len(tanks), gap="small")
        for ti, (tank, stage, params) in enumerate(tanks):
            w, vals = info[(l, tank)]
            icon = "🟢" if w >= NONE_RANK else KIND[kind_by_rank(w)]["icon"]
            label = f"{icon} **{tank}**  \n" + "  \n".join(f"{prm}  {v:.2f}" for prm, v in vals)
            key = f"nd-{li}-{ti}"
            with cols[ti]:
                st.button(label, key=key, on_click=_toggle_node, args=(l, tank), width="stretch")
            is_open = (l, tank) in opened
            glow = f"box-shadow:0 0 10px {_color(w)}66;" if w < NONE_RANK else ""
            border = "2px solid #22d3ee" if is_open else f"1px solid {_color(w)}aa"
            bg = "background:rgba(34,211,238,.10) !important;" if is_open else ""
            css.append(f".st-key-{key} button{{border:{border} !important;{glow}{bg}}}")

        for tank, stage, params in tanks:                          # 펼친 조의 그래프를 해당 계열 바로 아래에
            if (l, tank) in opened:
                st.markdown(f"##### ▼ {b} · {p} · {l} · {tank}")
                for col, prm in zip(st.columns(len(params)), params):
                    with col:
                        _sensor_card(plant, plant.find(b, p, l, tank, prm), window, height=240)
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
            icon = KIND[ks[0]]["icon"] if ks else "🟢"
            titles.append(f"{icon} {l[0]} · {tank}  {plant.V[i, -1]:.2f}")
    fig = make_subplots(rows=nr, cols=nc, subplot_titles=titles, shared_xaxes=True, shared_yaxes="columns",
                        vertical_spacing=0.06, horizontal_spacing=0.025)

    x = plant.idx[-window:]
    for r, l in enumerate(LINES, start=1):
        for ci, (tank, _, _) in enumerate(cols, start=1):
            i = plant.find(b, p, l, tank, prm)
            y = plant.V[i, -window:]
            ks = plant.active_kinds(i)
            color = KIND[ks[0]]["color"] if ks else "#22d3ee"
            for kind, rgb in (("HOLD", "59,130,246"), ("STD", "168,85,247"), ("PEER", "236,72,153")):
                for s0, s1 in _spans(plant.F[kind][i, -window:], x):
                    fig.add_vrect(x0=s0, x1=s1, fillcolor=f"rgba({rgb},.22)", line_width=0, layer="below", row=r, col=ci)
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
        "선 색 = 현재 상태(시안=정상) · 붉은 점선 = LSL/USL · 세로 음영: 파랑 Hold, 보라 σ 초과, 분홍 동료 대비 이탈"
    )


# ───────────────────────── 4. 경고 센터 ─────────────────────────
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
            _incident_charts(plant, x, window, "a")
    if shown < len(inc):
        if st.button(f"더 보기 ({len(inc) - shown}건 남음)"):
            st.session_state["_alert_n"] = shown + 8
            st.rerun()

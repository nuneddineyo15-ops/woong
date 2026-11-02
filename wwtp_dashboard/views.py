"""페이지 4개: 종합 현황 / 경고 센터 / 공정 탐색 / 항목별 비교."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from charts import sensor_figure
from core import (
    KIND, PARAMS, PLANT, active_kinds, alert_events, all_lines, line_label,
    load_data, near_margin, spec_text, window_kinds,
)

RANGES = {"1시간": 60, "3시간": 180, "6시간": 360, "12시간": 720, "24시간": 1440}
BADGE = {"SPEC": ":red", "NEAR": ":orange", "HOLD": ":blue", "STD": ":violet"}


# ───────────────────────── 공통 ─────────────────────────
def _ctx():
    data = load_data()
    window = RANGES[st.session_state.get("range", "6시간")]
    return data, window


def _badges(kinds: list[str]) -> str:
    if not kinds:
        return ":green[**● 정상**]"
    return "  ".join(f"{BADGE[k]}[**● {KIND[k]['label']}**]" for k in kinds)


def _legend():
    st.caption(
        ":red[■ 스펙 이탈]  ·  :orange[■ 상하한 근접]  ·  :blue[■ 1시간 Hold(파란 음영)]  ·  "
        ":violet[■ 표준편차 초과(보라 음영)]  ·  주황/빨강 배경 = 근접/이탈 구간"
    )


def _header(title: str, sub: str):
    st.markdown(f"### {title.split(' ', 1)[-1]}")
    last = load_data()[next(iter(load_data()))].index[-1]
    st.caption(f"{sub}  |  데이터 기준 {last:%Y-%m-%d %H:%M} (데모)")



OVERVIEW_CSS = """<style>
.bh{font-weight:700;color:#cbd5e1;letter-spacing:.05em;margin:14px 0 6px;font-size:13px}
.orow{display:grid;grid-template-columns:140px 1fr;gap:10px;margin-bottom:10px}
.orl{background:rgba(18,26,43,.72);border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:10px 12px;
  display:flex;flex-direction:column;justify-content:center}
.orl b{color:#e2e8f0;font-size:13px}.orl small{color:#64748b;font-size:11px}
.tiles{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.t{background:rgba(18,26,43,.72);border:1px solid;border-radius:10px;padding:9px 12px 8px}
.th{display:flex;justify-content:space-between;font-size:11px;color:#94a3b8}
.tv{font-family:'Orbitron',sans-serif;font-size:21px;color:#e2e8f0;margin:2px 0 8px}
.tv small{font-family:inherit;font-size:10px;color:#64748b;margin-left:5px}
.track{position:relative;height:8px;border-radius:4px;overflow:hidden;background:#1e293b}
.track i{position:absolute;top:0;bottom:0}
.mk{position:absolute;top:-3px;width:4px;height:14px;border-radius:2px;background:#fff;transform:translateX(-50%)}
.mw{position:relative;margin-top:0}
.tr{display:flex;justify-content:space-between;font-size:10px;color:#64748b;margin-top:5px}
</style>"""
_GREEN, _ORANGE, _RED = "rgba(34,197,94,.55)", "rgba(249,115,22,.75)", "rgba(239,68,68,.75)"


def _tile_html(key, df, window: int) -> str:
    """값 + 규격 안에서의 위치 막대 한 칸."""
    param = key[3]
    p = PARAMS[param]
    lsl, usl, m = p["lsl"], p["usl"], near_margin(p)
    val = df["value"].iloc[-1]
    kinds = active_kinds(df)
    hist = window_kinds(df, window)
    if kinds:
        c, text = KIND[kinds[0]]["color"], KIND[kinds[0]]["label"] + (f" 외 {len(kinds) - 1}" if len(kinds) > 1 else "")
    elif hist:
        c, text = "#64748b", "해소됨"
    else:
        c, text = "#22c55e", "정상"

    lo = lsl if lsl is not None else 0.0
    span = usl - lo
    a_lo = lo - 0.2 * span if lsl is not None else 0.0
    a_hi = usl + 0.2 * span

    def pct(x):
        return max(0.0, min(100.0, (x - a_lo) / (a_hi - a_lo) * 100))

    segs = []
    if lsl is not None:
        segs += [(a_lo, lsl, _RED), (lsl, lsl + m, _ORANGE)]
    segs += [(lsl + m if lsl is not None else lo, usl - m, _GREEN), (usl - m, usl, _ORANGE), (usl, a_hi, _RED)]
    bar = "".join(
        f'<i style="left:{pct(x0):.1f}%;width:{pct(x1) - pct(x0):.1f}%;background:{col}"></i>' for x0, x1, col in segs
    )
    left = f"{lsl:g}" if lsl is not None else "0"
    return (
        f'<div class="t" style="border-color:{c}88"><div class="th"><span>{param}</span>'
        f'<span style="color:{c}">● {text}</span></div>'
        f'<div class="tv">{val:.2f}<small>{p["unit"]}</small></div>'
        f'<div class="mw"><div class="track">{bar}</div><span class="mk" style="left:{pct(val):.1f}%"></span></div>'
        f'<div class="tr"><span>{left}</span><span>{usl:g}</span></div></div>'
    )


def _sensor_card(key, df, window: int, height: int = 220, tag: str = "", note: str = ""):
    """작은 카드 1개: 이름 + 현재값 + 상태 + 차트."""
    b, s, l, param = key
    p = PARAMS[param]
    kinds = active_kinds(df)
    hist = [k for k in window_kinds(df, window) if k not in kinds]
    with st.container(border=True):
        if tag:
            st.markdown(f"**{tag}**")
        top = st.columns([1.1, 1.5])
        with top[0]:
            cur = df["value"].iloc[-1]
            prev = df["value"].iloc[-61] if len(df) > 61 else cur
            label = param if p["unit"] == param else f"{param} ({p['unit']})"
            st.metric(label, f"{cur:.2f}", f"{cur - prev:+.2f} /1h", delta_color="off")
        with top[1]:
            st.markdown(_badges(kinds) if kinds or not hist else ":gray[**● 해소됨**]")
            line2 = f"규격 {spec_text(p)}  ·  σ {df['std'].iloc[-1]:.2f}"
            if hist:
                line2 += "  ·  이력: " + ", ".join(KIND[k]["label"] for k in hist)
            st.caption(line2)
        if note:
            st.caption(note)
        st.plotly_chart(
            sensor_figure(df, param, window, height),
            width="stretch", key=f"card-{key}-{window}-{tag}", config={"displayModeBar": False},
        )


# ───────────────────────── 1. 종합 현황 ─────────────────────────
def overview():
    data, window = _ctx()
    _header("🏭 폐수처리 품질 현황", "전 공정 한눈에 보기")

    # KPI
    act = {k: 0 for k in KIND}
    normal = 0
    for df in data.values():
        a = active_kinds(df)
        normal += not a
        for k in a:
            act[k] += 1
    cols = st.columns(5)
    cols[0].metric("🟢 정상 / 전체 센서", f"{normal} / {len(data)}")
    for c, k in zip(cols[1:], ["SPEC", "NEAR", "HOLD", "STD"]):
        c.metric(f"{KIND[k]['icon']} {KIND[k]['label']}", f"{act[k]} 건", delta_color="off")

    # 공정별 현재 상태 타일
    st.subheader("공정별 현재 상태")
    st.caption("막대 = 규격(LSL~USL) 범위, 흰 막대 = 지금 값의 위치. 초록 안쪽이면 정상, 주황에 닿으면 근접, 빨강이면 이탈")
    html = [OVERVIEW_CSS]
    last_b = None
    for (b_, s_, l_) in all_lines():
        if b_ != last_b:
            html.append(f'<div class="bh">{b_}</div>')
            last_b = b_
        tiles = "".join(_tile_html((b_, s_, l_, param), data[(b_, s_, l_, param)], window) for param in PARAMS)
        html.append(f'<div class="orow"><div class="orl"><b>{s_}</b><small>{l_}</small></div><div class="tiles">{tiles}</div></div>')
    st.markdown("".join(html), unsafe_allow_html=True)

    # 진행 중 경고
    st.subheader("지금 진행 중인 경고")
    ev = alert_events(data, window)
    now_ev = ev[ev["active"]] if not ev.empty else ev
    if now_ev.empty:
        st.success("현재 진행 중인 경고가 없습니다.")
    else:
        view = pd.DataFrame(
            {
                "유형": [f"{KIND[k]['icon']} {KIND[k]['label']}" for k in now_ev["kind"]],
                "위치": [line_label(*k[:3]) for k in now_ev["key"]],
                "항목": [k[3] for k in now_ev["key"]],
                "현재값": [f"{v:.2f} {u}" for v, u in zip(now_ev["now"], now_ev["unit"])],
                "규격": now_ev["spec"],
                "지속(분)": now_ev["minutes"],
            }
        )
        st.dataframe(view, hide_index=True, width="stretch")
        st.page_link(st.session_state["_pages"]["alerts"], label="경고 센터에서 자세히 보기 →", icon="🚨")


# ───────────────────────── 2. 경고 센터 ─────────────────────────
def alerts():
    data, window = _ctx()
    _header("🚨 경고 센터", "경고가 걸린 항목을 그래프와 함께 쭉 훑어보기")
    ev = alert_events(data, window)
    if ev.empty:
        st.success(f"최근 {st.session_state.get('range', '6시간')} 동안 경고가 없습니다.")
        return

    f1, f2, f3 = st.columns([2.2, 1.4, 1.4], vertical_alignment="bottom")
    kinds = f1.multiselect("경고 유형", list(KIND), default=list(KIND), format_func=lambda k: f"{KIND[k]['icon']} {KIND[k]['label']}")
    bld = f2.selectbox("건물", ["전체"] + list(PLANT))
    only_active = f3.toggle("진행 중만 보기", value=False)

    ev = ev[ev["kind"].isin(kinds)]
    if bld != "전체":
        ev = ev[[k[0] == bld for k in ev["key"]]]
    if only_active:
        ev = ev[ev["active"]]
    if ev.empty:
        st.info("조건에 맞는 경고가 없습니다.")
        return

    # 센서당 카드 1장: 같은 센서의 여러 경고는 한 카드에 합침 (진행 중 → 심각도 → 최근 순)
    cards = []
    for key, g in ev.groupby("key", sort=False):
        cards.append(
            dict(
                key=key,
                active=bool(g["active"].any()),
                rank=int(g["rank"].min()),
                last=g["last"].max(),
                note="  |  ".join(
                    f"{KIND[r.kind]['icon']} {KIND[r.kind]['label']} {r.first:%H:%M}→{r.last:%H:%M} ({r.minutes}분)"
                    for r in g.sort_values("rank").itertuples()
                ),
            )
        )
    cards.sort(key=lambda c: (not c["active"], c["rank"], -c["last"].value))

    n_act = sum(c["active"] for c in cards)
    st.caption(f"경고 센서 {len(cards)}개 (진행 중 {n_act} · 해소 {len(cards) - n_act})  —  아래로 스크롤하며 확인하세요")
    _legend()

    cols = st.columns(2)
    for i, c in enumerate(cards):
        with cols[i % 2]:
            _sensor_card(
                c["key"], data[c["key"]], window, height=260,
                tag=f"{line_label(*c['key'][:3])}", note=c["note"],
            )


# ───────────────────────── 3. 공정 탐색 ─────────────────────────
def explorer():
    data, window = _ctx()
    _header("🔎 공정 탐색", "건물 › 시스템 › 계열을 고르면 항목별 추이가 나옵니다")

    c = st.columns(3)
    b = c[0].selectbox("건물", list(PLANT))
    s = c[1].selectbox("시스템", list(PLANT[b]))
    l = c[2].selectbox("계열", PLANT[b][s])

    keys = [(b, s, l, p) for p in PARAMS]
    n_alert = sum(bool(active_kinds(data[k])) for k in keys)
    st.markdown(f"#### {line_label(b, s, l)}  " + (f":red[**경고 {n_alert}개 항목**]" if n_alert else ":green[**전 항목 정상**]"))

    cols = st.columns(3)
    for i, k in enumerate(keys):
        with cols[i % 3]:
            _sensor_card(k, data[k], window)
    # 6번째 칸: 이 계열 경고 요약
    with cols[len(keys) % 3]:
        with st.container(border=True):
            st.markdown("**이 계열 경고 요약**")
            any_ = False
            for k in keys:
                a = active_kinds(data[k])
                if a:
                    any_ = True
                    st.markdown(f"- **{k[3]}** {_badges(a)}")
            if not any_:
                st.caption("진행 중인 경고 없음")
            st.caption("카드의 차트는 최근 구간 기준, 배경색은 규격 근접/이탈 영역입니다.")
    _legend()


# ───────────────────────── 4. 항목별 비교 ─────────────────────────
def compare():
    data, window = _ctx()
    _header("📊 항목별 비교", "같은 항목을 모든 계열에서 나란히 비교")

    param = st.radio("항목", list(PARAMS), horizontal=True)
    lines = all_lines()
    cols = st.columns(3)
    for i, (b, s, l) in enumerate(lines):
        with cols[i % 3]:
            k = (b, s, l, param)
            _sensor_card(k, data[k], window, height=200, tag=f"{b.split('(')[0]} {s} {l}")
    _legend()

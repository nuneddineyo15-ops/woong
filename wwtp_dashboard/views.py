"""페이지 4개: 종합 현황 / 경고 센터 / 공정 탐색 / 항목별 비교."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from charts import sensor_figure
from core import (
    FLAG_COL, KIND, PARAMS, PLANT, active_kinds, alert_events, all_lines, line_label,
    load_data, spec_text, window_kinds,
)

RANGES = {"1시간": 60, "3시간": 180, "6시간": 360, "12시간": 720, "24시간": 1440}
BADGE = {"SPEC": ":red", "NEAR": ":orange", "HOLD": ":blue", "STD": ":violet"}

# 종합 맵 색상 (코드 → 색)
MAP_STATES = [
    ("정상", "#16a34a"),
    ("해소(이력)", "#64748b"),
    ("σ 초과", KIND["STD"]["color"]),
    ("Hold", KIND["HOLD"]["color"]),
    ("근접", KIND["NEAR"]["color"]),
    ("스펙 이탈", KIND["SPEC"]["color"]),
]
KIND_TO_CODE = {"STD": 2, "HOLD": 3, "NEAR": 4, "SPEC": 5}


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
    st.title(title)
    last = load_data()[next(iter(load_data()))].index[-1]
    st.caption(f"{sub}  |  데이터 기준 {last:%Y-%m-%d %H:%M} (데모)")


def _sensor_card(key, df, window: int, height: int = 220, tag: str = ""):
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
            st.markdown(_badges(kinds))
            line2 = f"규격 {spec_text(p)}  ·  σ {df['std'].iloc[-1]:.2f}"
            if hist:
                line2 += "  ·  이력: " + ", ".join(KIND[k]["label"] for k in hist)
            st.caption(line2)
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

    # 공정 맵 (행: 건물›시스템›계열, 열: 항목)
    st.subheader("공정 상태 맵")
    st.caption(f"현재 값과 상태 (조회 구간 {st.session_state.get('range', '6시간')} 기준 이력 포함) — 셀 색이 곧 경고 종류")
    lines = all_lines()
    params = list(PARAMS)
    z, txt, hover = [], [], []
    for (b, s, l) in lines:
        zr, tr, hr = [], [], []
        for param in params:
            df = data[(b, s, l, param)]
            a = active_kinds(df)
            h = window_kinds(df, window)
            code = max(KIND_TO_CODE[k] for k in a) if a else (1 if h else 0)
            zr.append(code)
            tr.append(f"{df['value'].iloc[-1]:.1f}")
            state = ", ".join(KIND[k]["label"] for k in a) if a else ("해소: " + ", ".join(KIND[k]["label"] for k in h) if h else "정상")
            hr.append(f"{line_label(b, s, l)}<br>{param}: {df['value'].iloc[-1]:.2f} {PARAMS[param]['unit']}<br>{state}")
        z.append(zr); txt.append(tr); hover.append(hr)

    n = len(MAP_STATES)
    colorscale = []
    for i, (_, c) in enumerate(MAP_STATES):
        colorscale += [[i / n, c], [(i + 1) / n, c]]
    ylabels = [f"{b.split('(')[0]} · {s} · {l}" for (b, s, l) in lines]
    fig = go.Figure(
        go.Heatmap(
            z=z, x=[f"{p} ({PARAMS[p]['unit']})" for p in params], y=ylabels,
            text=txt, texttemplate="%{text}", textfont=dict(color="white", size=15),
            customdata=hover, hovertemplate="%{customdata}<extra></extra>",
            colorscale=colorscale, zmin=-0.5, zmax=n - 0.5, showscale=False,
            xgap=4, ygap=4,
        )
    )
    fig.update_layout(
        height=70 + 62 * len(lines), margin=dict(l=8, r=8, t=8, b=8),
        xaxis=dict(side="top"), yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, width="stretch", key="map", config={"displayModeBar": False})
    st.caption("  ".join(f"<span style='color:{c}'>■</span> {n_}" for n_, c in MAP_STATES), unsafe_allow_html=True)

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
    _header("🚨 경고 센터", "경고가 걸린 항목만 모아보기")
    ev = alert_events(data, window)
    if ev.empty:
        st.success(f"최근 {st.session_state.get('range', '6시간')} 동안 경고가 없습니다.")
        return

    f1, f2, f3 = st.columns([2.2, 1.4, 1.4])
    kinds = f1.multiselect("경고 유형", list(KIND), default=list(KIND), format_func=lambda k: f"{KIND[k]['icon']} {KIND[k]['label']}")
    bld = f2.selectbox("건물", ["전체"] + list(PLANT))
    only_active = f3.toggle("진행 중만 보기", value=False)

    ev = ev[ev["kind"].isin(kinds)]
    if bld != "전체":
        ev = ev[[k[0] == bld for k in ev["key"]]]
    if only_active:
        ev = ev[ev["active"]]
    ev = ev.reset_index(drop=True)
    if ev.empty:
        st.info("조건에 맞는 경고가 없습니다.")
        return

    st.caption(f"{len(ev)}건 — 행을 클릭하면 아래에 상세 추이가 나옵니다.")
    table = pd.DataFrame(
        {
            "상태": ["🔥 진행중" if a else "✔ 해소" for a in ev["active"]],
            "유형": [f"{KIND[k]['icon']} {KIND[k]['label']}" for k in ev["kind"]],
            "위치": [line_label(*k[:3]) for k in ev["key"]],
            "항목": [k[3] for k in ev["key"]],
            "현재값": [f"{v:.2f} {u}" for v, u in zip(ev["now"], ev["unit"])],
            "규격": ev["spec"],
            "최초": ev["first"].dt.strftime("%H:%M"),
            "최근": ev["last"].dt.strftime("%H:%M"),
            "지속(분)": ev["minutes"],
        }
    )
    sel = st.dataframe(
        table, hide_index=True, width="stretch", height=min(38 * len(table) + 40, 330),
        on_select="rerun", selection_mode="single-row", key="alert-table",
    )
    rows = sel.selection.rows
    i = rows[0] if rows and rows[0] < len(ev) else 0
    row = ev.iloc[i]
    key, kind = row["key"], row["kind"]
    df = data[key]
    p = PARAMS[key[3]]

    st.divider()
    st.subheader(f"{KIND[kind]['icon']} {line_label(*key[:3])} · {key[3]}")
    st.caption(f"{KIND[kind]['label']}  |  {'진행 중' if row['active'] else '해소됨'}  |  최초 {row['first']:%H:%M} → 최근 {row['last']:%H:%M}  ({row['minutes']}분)")
    w = df.iloc[-window:]
    m = st.columns(5)
    m[0].metric("현재값", f"{df['value'].iloc[-1]:.2f} {p['unit']}")
    m[1].metric("규격", spec_text(p))
    m[2].metric("구간 평균", f"{w['value'].mean():.2f}")
    m[3].metric("현재 σ(60분)", f"{df['std'].iloc[-1]:.2f}", f"기준 {p['std_limit']:g}", delta_color="off")
    m[4].metric("구간 최대/최소", f"{w['value'].max():.1f} / {w['value'].min():.1f}")
    st.plotly_chart(sensor_figure(df, key[3], window, 380), width="stretch", key=f"alert-detail-{key}-{window}", config={"displayModeBar": False})
    _legend()


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

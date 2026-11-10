"""화면 부품 (Dash 컴포넌트) 모음."""
from __future__ import annotations

from urllib.parse import parse_qs, urlencode

import numpy as np
from dash import ctx as dash_ctx, dcc, html

import store
from core import KIND, STEP_MIN
from figs import OK_COLOR, RESOLVED_COLOR, kind_name

WINDOWS = [36, 72, 144, 288, 576]                    # 조회 구간(샘플 수, 5분 간격) = 3·6·12·24·48시간
WINDOW_LABELS = ["3시간", "6시간", "12시간", "24시간", "48시간"]
GRAPH_CFG = {"displayModeBar": False}


def ctx(range_idx) -> tuple:
    """(Plant, 구간 샘플 수, 데이터 버전)."""
    return store.plant(), WINDOWS[range_idx if range_idx is not None else 3], store.version()


def section(title: str, sub: str = "", sub_id: str | None = None, first: bool = False) -> html.Div:
    kw = {"id": sub_id} if sub_id else {}
    return html.Div([title, html.Span(sub, **kw)], className="sec first" if first else "sec")


def page_header(plant, title: str, sub: str) -> html.Div:
    return html.Div([html.H3(title), html.Div(f"{sub}  |  데이터 기준 {plant.idx[-1]:%Y-%m-%d %H:%M} · {STEP_MIN}분 평균 (데모)", className="cap")])


def legend() -> html.Div:
    return html.Div(
        "배경: 주황 = 상하한 근접 · 빨강 = 이탈  |  세로 음영: 파랑 = Hold · 보라 = σ 초과 · 분홍 = 동료 대비 이탈 · "
        "갈색 = 개도-투입 불일치 · 하늘색 = DO↓ 공기개도↑ · 남색 = 고분자 부족  |  회색 띠/점선 = 같은 항목 다른 센서의 범위/중앙값",
        className="cap")


def sensor_head(plant, i: int, window: int) -> html.Div:
    """센서 머리글 한 줄: 항목 · 현재값(이상이면 경고 색) · 1시간 변화 · 상태, 아래에 규격·σ·이력."""
    m = plant.meta.iloc[i]
    dec = int(m.dec)
    kinds = plant.active_kinds(i)
    hist = [k for k in plant.window_kinds(i, window) if k not in kinds]
    cur, d = plant.V[i, -1], plant.V[i, -1] - plant.V[i, -13]
    if kinds:
        state = []
        for n, k in enumerate(kinds):
            state += ([" · "] if n else []) + [html.Span(kind_name(k), style={"color": KIND[k]["color"]})]
    elif hist:
        state = [html.Span("해소됨", style={"color": RESOLVED_COLOR})]
    else:
        state = [html.Span("정상", style={"color": OK_COLOR})]
    extra = f"규격 {plant.spec_text(i)} · σ {np.nan_to_num(plant.std[i, -1]):.2f}"
    if hist:
        extra += " · 이력: " + ", ".join(kind_name(k) for k in hist)
    return html.Div([
        html.Span(m.param, className="p"),
        html.Span(f"{cur:.{dec}f}", className="v", style={"color": KIND[kinds[0]]["color"] if kinds else "var(--ink)"}),
        html.Span(m.unit, className="u"), html.Span(f"{d:+.{dec}f} /1h", className="dl"),
        html.Span(state, className="s"), html.Div(extra, className="x"),
    ], className="sh")


def trig_value(t):
    """방금 눌린 컴포넌트의 현재 값. 패턴 매칭 입력은 ctx.triggered 의 value 가 None 으로 오는 일이 있어서 inputs_list 에서 직접 찾는다.
    (새로 그려진 버튼은 n_clicks=0 이라 falsy → 호출한 쪽에서 무시)"""
    for grp in dash_ctx.inputs_list:
        for it in (grp if isinstance(grp, list) else [grp]):
            if it["id"] == t:
                return it.get("value")
    return None


def state_hash(ridx, bsel, sel) -> str:
    """화면 상태(구간·동·선택)를 주소의 #해시에 담음. ?검색어는 Dash 페이지 라우터가 바뀌면 화면 전체를 다시 만들기 때문에 쓰지 않음."""
    q = {"w": WINDOWS[ridx if ridx is not None else 3]}
    if bsel and bsel != "전체":
        q["b"] = bsel
    if sel:
        q["sel"] = "|".join([sel["kind"], *sel["key"]])
    return "#" + urlencode(q)


def parse_hash(h: str | None, buildings) -> tuple:
    """#해시 → (구간 번호, 동, 선택). 없는 값은 None."""
    q = parse_qs((h or "").lstrip("#"))
    w = int(q["w"][0]) if q.get("w") and q["w"][0].isdigit() and int(q["w"][0]) in WINDOWS else None
    b = q["b"][0] if q.get("b") and q["b"][0] in buildings else None
    s = q["sel"][0].split("|") if q.get("sel") else None
    sel = {"kind": s[0], "key": s[1:]} if s and s[0] in ("inc", "node") and len(s) > 1 else None
    return (WINDOWS.index(w) if w else None), b, sel


def graph(fig, **kw) -> dcc.Graph:
    return dcc.Graph(figure=fig, config=GRAPH_CFG, **kw)

"""WWTP 품질 관제 — Dash 버전 (데모 데이터, 센서 약 960개).

실행:   python dash_app/main.py          →  http://localhost:8601
운영:   gunicorn "dash_app.main:server"  (여러 프로세스로 띄우기 쉬움)

Streamlit 버전과 같은 core.py(감지) · charts.py(그래프)를 쓰고, 화면만 Dash 로 다시 만든 것.
Dash 에서만 되는 기능:
  - URL 딥링크      : 조회 구간·동 필터·선택한 사고가 주소에 담김 → 링크를 공유하면 같은 화면이 열림, 뒤로가기도 동작
  - 패턴 매칭 콜백  : 흐름 노드·이상점 바·탱크 박스를 콜백 하나로 처리
  - 그래프 직접 클릭: 캔버스 점·비교 그래프의 선·타임라인 막대를 눌러 이동 (clickData)
  - 연동 줌(Patch)  : 트렌드 한 곳에서 시간을 드래그하면 나머지 그래프도 같이 확대 (그림을 다시 만들지 않고 일부만 수정)
  - 일부만 갱신     : dcc.Interval 이 '데이터 버전'만 확인하고, 바뀐 부분만 다시 그림
  - 클라이언트 콜백 : 시계·스크롤 이동은 서버를 거치지 않고 브라우저에서 처리
  - DataTable       : 정렬·필터·CSV 내보내기 기본 제공
"""
import os
import sys
from pathlib import Path

os.environ["WWTP_NO_STREAMLIT"] = "1"                 # core.get_plant 를 Streamlit 없이 캐시
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]          # core, charts, figs, ui, store 를 어디서든 import

import dash                                            # noqa: E402
from dash import Input, Output, State, callback, clientside_callback, ctx, dcc, html, no_update  # noqa: E402

import store                                           # noqa: E402
from core import BUILDINGS                             # noqa: E402
from ui import WINDOW_LABELS, WINDOWS, ctx as get_ctx, parse_hash, state_hash  # noqa: E402

REFRESH_SEC = int(os.environ.get("WWTP_REFRESH_SEC", "300"))   # 5분 평균이 5분마다 쌓이므로 기본 300초

app = dash.Dash(__name__, use_pages=True, pages_folder=str(HERE / "pages"), assets_folder=str(HERE / "assets"),
                suppress_callback_exceptions=True, title="WWTP 품질 관제")
server = app.server                                    # gunicorn 용 Flask 서버

RULES = [
    ("스펙 이탈", "LSL/USL 벗어남"), ("근접", "규격폭 10% 이내"), ("Hold", "1시간(12샘플) 연속 같은 값"),
    ("σ 초과", "1시간 이동 표준편차 > 항목별 기준"),
    ("동료 대비 이탈", "같은 공정·같은 항목 센서들의 중앙값과 5σ 이상 벌어져 30분 지속 (규격 안이어도 감지)"),
    ("개도-투입 불일치", "개도에 비해 투입량·농도가 평소(앞 7일) 관계에서 5σ 이상 벗어나 30분 지속 (막힘·펌프 정지·누설)"),
    ("DO↓ 공기개도↑", "2시간 동안 DO 는 떨어지고 공기 밸브는 열리는 게 평소보다 뚜렷하게 30분 지속 (산기관 막힘·부하 급증)"),
    ("고분자 부족", "같은 계열 약품(CaOH2·AFR·FR) 투입 대비 Polymer 비율이 평소보다 5σ 낮게 30분 지속"),
]

app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    dcc.Interval(id="tick", interval=REFRESH_SEC * 1000),         # 데이터 버전 확인용 (그림은 다시 안 그림)
    dcc.Interval(id="clock-tick", interval=1000),                  # 시계 (클라이언트 콜백)
    dcc.Store(id="sel"), dcc.Store(id="data-ver"), dcc.Store(id="pr-open", data=[]), dcc.Store(id="al-n", data=8),
    html.Div(id="nav", className="topnav"),
    html.Div([
        html.Div("WWTP", className="wwtp-mark"),
        html.Div([html.Div(["WWTP QUALITY CONTROL", html.Span("LIVE · DEMO · DASH", className="wwtp-live")], className="wwtp-title"),
                  html.Div(id="hdr-sub", className="wwtp-sub")]),
        html.Div(id="clock", className="clock"),
        html.Div(id="pill", className="wwtp-pill ok"),
    ], className="wwtp-bar"),
    html.Div([
        html.Div([html.Label("조회 구간"), html.Div(dcc.Slider(id="range", min=0, max=4, step=None, value=3,
                  marks={i: s for i, s in enumerate(WINDOW_LABELS)}, tooltip=None), className="slider")], className="ctl wide"),
        html.Div([html.Label("동"), dcc.RadioItems(id="bsel", options=[{"label": x, "value": x} for x in ["전체"] + BUILDINGS],
                  value="전체", inline=True, className="seg")], className="ctl"),
        html.Details([html.Summary("경고 기준"), html.Ul([html.Li([html.B(a + " "), b]) for a, b in RULES])], className="rules"),
    ], className="ctlbar"),
    dash.page_container,
])


# ───────────── 상단 탭 (현재 상태 #해시를 그대로 붙여 이동 → 선택·구간이 유지됨) ─────────────
@callback(Output("nav", "children"), Input("url", "pathname"), Input("url", "hash"))
def render_nav(path, hash_):
    return [dcc.Link(pg["name"], href=pg["path"] + (hash_ or ""), className="tnav" + (" on" if pg["path"] == (path or "/") else ""))
            for pg in sorted(dash.page_registry.values(), key=lambda p: p["order"])]


# ───────────── URL ↔ 화면 상태 (딥링크) ─────────────
# 읽기는 '페이지 이동/처음 열기' 때만(pathname), 쓰기는 값이 바뀔 때마다 → 서로를 다시 부르지 않음
@callback(Output("range", "value"), Output("bsel", "value"), Output("sel", "data"),
          Input("url", "pathname"), State("url", "hash"))
def read_url(_, hash_):
    ridx, b, sel = parse_hash(hash_, BUILDINGS)
    return (no_update if ridx is None else ridx), (b or no_update), (sel or no_update)


@callback(Output("url", "hash"), Input("range", "value"), Input("bsel", "value"), Input("sel", "data"),
          prevent_initial_call=True)
def write_url(ridx, b, sel):
    return state_hash(ridx, b, sel)


# ───────────── 데이터 버전 확인 → 바뀐 부분만 갱신 ─────────────
@callback(Output("data-ver", "data"), Input("tick", "n_intervals"), State("data-ver", "data"))
def check_version(_, old):
    v = store.version()
    return no_update if v == old else v


@callback(Output("pill", "children"), Output("pill", "className"), Output("hdr-sub", "children"),
          Input("data-ver", "data"), Input("range", "value"))
def header(_, ridx):
    plant, window, ver = get_ctx(ridx)
    n = sum(x["active"] for x in store.incs(ver, window))
    sub = f"폐수처리 공정 수질 · 센서 {plant.n}개 이상 감지 관제 · 마지막 갱신 {plant.idx[-1]:%H:%M}"
    text, cls = (f"진행 중 사고 {n}", "wwtp-pill bad") if n else ("전 센서 정상", "wwtp-pill ok")
    return text, cls, sub


clientside_callback(                                   # 시계: 서버 호출 없이 브라우저에서
    "function(n){return new Date().toLocaleTimeString('ko-KR',{hour12:false});}",
    Output("clock", "children"), Input("clock-tick", "n_intervals"))

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", "8601")))

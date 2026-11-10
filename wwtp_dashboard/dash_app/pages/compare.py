"""한눈에 비교: 같은 항목을 계열 × 조로 펼쳐서 혼자 튀는 센서 찾기. 선을 누르면 아래에 그 센서 상세(그래프 직접 클릭)."""
from __future__ import annotations

import dash
import numpy as np
from dash import Input, Output, State, callback, dcc, html
from dash.exceptions import PreventUpdate

from charts import sensor_figure
from core import BUILDINGS, PROCESSES, tanks_of
from figs import compare_figure
from ui import GRAPH_CFG, ctx as get_ctx, legend, page_header, sensor_head

dash.register_page(__name__, path="/compare", name="한눈에 비교", order=2)


def _params(p):
    ps = list(dict.fromkeys(prm for _, _, x in tanks_of(p) for prm in x))
    n = [sum(prm in t[2] for t in tanks_of(p)) for prm in ps]
    return ps, ps[int(np.argmax(n))]                              # 기본 항목: 그래프가 가장 많은 항목


def layout(**_):
    ps, default = _params("유기")
    return html.Div([
        html.Div(id="cmp-head"),
        html.Div([
            html.Div([html.Label("건물"), dcc.Dropdown(id="cmp-b", options=BUILDINGS, value="1동", clearable=False)]),
            html.Div([html.Label("공정"), dcc.Dropdown(id="cmp-p", options=PROCESSES, value="유기", clearable=False)]),
            dcc.Checklist(id="cmp-full", options=[{"label": " 규격선까지 보이게 스케일 확대 (끄면 데이터에 맞춰 확대)", "value": "full"}], value=[]),
        ], className="filters", style={"gridTemplateColumns": "1fr 1fr 2fr"}),
        html.Div([html.Label("항목"), dcc.RadioItems(id="cmp-prm", options=ps, value=default, inline=True, className="seg")]),
        dcc.Loading(dcc.Graph(id="cmp-graph", config=GRAPH_CFG), type="dot", color="#0e7490"),
        html.Div("같은 열 = 같은 종류의 조라 y축을 맞췄어요. 한 줄(계열)이 다른 줄들과 다르게 움직이면 이상 후보예요. "
                 "선 색 = 현재 상태(청록=정상) · 붉은 점선 = LSL/USL · 그래프의 선을 누르면 아래에 그 센서 상세가 나와요.", className="cap"),
        html.Div(id="cmp-detail"),
        legend(),
    ], className="page")


@callback(Output("cmp-head", "children"), Input("data-ver", "data"), State("range", "value"))
def head(_, ridx):
    return page_header(get_ctx(ridx)[0], "한눈에 비교", "같은 항목을 계열 × 조로 펼쳐서, 클릭 없이 혼자 튀는 센서를 찾기")


@callback(Output("cmp-prm", "options"), Output("cmp-prm", "value"), Input("cmp-p", "value"))
def prm_options(p):
    ps, default = _params(p)
    return ps, default


@callback(Output("cmp-graph", "figure"), Output("cmp-graph", "clickData"),
          Input("cmp-b", "value"), Input("cmp-p", "value"), Input("cmp-prm", "value"), Input("cmp-full", "value"),
          Input("range", "value"), Input("data-ver", "data"))
def figure(b, p, prm, full, ridx, _):
    if prm not in _params(p)[0]:                                  # 공정을 막 바꿔서 항목이 아직 이전 것 → 곧 prm_options 가 맞춰 줌
        raise PreventUpdate
    plant, window, _v = get_ctx(ridx)
    return compare_figure(plant, b, p, prm, window, bool(full)), None     # 그림이 바뀌면 이전 클릭 선택은 지움


@callback(Output("cmp-detail", "children"), Input("cmp-graph", "clickData"), Input("range", "value"))
def detail(click, ridx):
    if not click:
        return html.Div("그래프의 선을 누르면 그 센서의 상세 그래프가 여기에 나와요.", className="msg")
    cd = click["points"][0].get("customdata")
    i = int(cd[0] if isinstance(cd, (list, tuple)) else cd)
    plant, window, _v = get_ctx(ridx)
    m = plant.meta.iloc[i]
    return [html.Div([f"{m.bldg} · {m.proc} · {m.line} · ", html.B(f"{m.tank} {m.param}")], className="xh"),
            sensor_head(plant, i, window), dcc.Graph(figure=sensor_figure(plant, i, window, 280), config=GRAPH_CFG)]

"""공정 상세: 계열별 공정 흐름(탱크 → 배관 → 탱크). 이상 있는 조는 자동 펼침, 탱크를 누르면 그 계열 바로 아래에 그래프 펼침/접힘."""
from __future__ import annotations

import dash
from dash import ALL, Input, Output, State, callback, ctx, dcc, html
from dash.exceptions import PreventUpdate

from charts import sensor_figure
from core import BUILDINGS, KIND, LINES, NONE_RANK, PROCESSES, tanks_of
from figs import color_of, status_text
from ui import GRAPH_CFG, ctx as get_ctx, legend, page_header, sensor_head, trig_value
import store

dash.register_page(__name__, path="/process", name="공정 상세", order=1)


def layout(pb=None, pp=None, **_):
    """주소의 ?pb=동&pp=공정 으로 바로 열림 (전체 현황의 '흐름도 열기' 링크가 사용 — Dash 페이지는 검색어를 layout 인자로 받음)."""
    return html.Div([
        html.Div(id="pr-head"),
        html.Div([
            html.Div([html.Label("건물"), dcc.Dropdown(id="pr-b", options=BUILDINGS, value=pb if pb in BUILDINGS else "1동", clearable=False)]),
            html.Div([html.Label("공정"), dcc.Dropdown(id="pr-p", options=PROCESSES, value=pp if pp in PROCESSES else "유기", clearable=False)]),
            html.Div([html.Button("이상 조 모두 펼치기", id="pr-expand", className="btn"),
                      html.Button("모두 접기", id="pr-collapse", className="btn")], className="btnrow"),
        ], className="filters", style={"gridTemplateColumns": "1fr 1fr 2fr"}),
        html.Div(id="pr-body"),
        legend(),
    ], className="page")


def _abnormal(plant, b, p):
    return [f"{l}|{tank}" for l in LINES for tank, _, params in tanks_of(p)
            if any(plant.now_rank[plant.find(b, p, l, tank, prm)] < NONE_RANK for prm in params)]


@callback(Output("pr-open", "data"),
          Input({"type": "tk", "l": ALL, "t": ALL}, "n_clicks"), Input("pr-expand", "n_clicks"), Input("pr-collapse", "n_clicks"),
          Input("pr-b", "value"), Input("pr-p", "value"), State("pr-open", "data"), State("range", "value"))
def open_state(_tk, _e, _c, b, p, cur, ridx):
    t = ctx.triggered_id
    plant = get_ctx(ridx)[0]
    if t is None or t in ("pr-b", "pr-p", "pr-expand"):          # 처음 열기 / 공정을 바꾸면 이상 있는 조를 모두 펼침
        return _abnormal(plant, b, p)
    if t == "pr-collapse":
        return []
    if not trig_value(t):                                          # 새로 그려진 버튼(n_clicks=0)은 무시
        raise PreventUpdate
    s = set(cur or [])
    s ^= {f"{t['l']}|{t['t']}"}
    return sorted(s)


@callback(Output("pr-head", "children"), Input("data-ver", "data"), State("range", "value"))
def head(_, ridx):
    return page_header(get_ctx(ridx)[0], "공정 상세", "계열별 공정 흐름 — 이상 있는 조는 자동으로 펼쳐지고, 탱크를 누르면 그래프가 펼쳐지거나 접혀요")


@callback(Output("pr-body", "children"),
          Input("pr-open", "data"), Input("pr-b", "value"), Input("pr-p", "value"), Input("range", "value"), Input("data-ver", "data"))
def body(open_, b, p, ridx, _):
    plant, window, _v = get_ctx(ridx)
    open_ = set(open_ or [])
    tanks, dec = tanks_of(p), plant.meta["dec"].to_numpy()
    out = []
    for l in LINES:
        info, row = {}, []
        for tank, stage, params in tanks:
            vals, worst = [], NONE_RANK
            for prm in params:
                i = plant.find(b, p, l, tank, prm)
                worst = min(worst, int(plant.now_rank[i]))
                vals.append((prm, plant.V[i, -1], int(dec[i]), bool(plant.active_kinds(i))))
            info[tank] = (worst, vals)
        ws = [w for w, _ in info.values()]
        n_bad = sum(w < NONE_RANK for w in ws)
        out.append(html.Div([html.B(l), html.Span(status_text(min(ws)) + (f" · 이상 {n_bad}개 조" if n_bad else ""),
                                                  style={"color": color_of(min(ws))})], className="lh"))
        for ti, (tank, stage, params) in enumerate(tanks):
            w, vals = info[tank]
            col = color_of(w)
            edge = col if w < NONE_RANK else "#475569"
            row.append(html.Button(
                [html.Span(tank, className="n")] + [
                    html.Div(f"{prm} {v:.{d}f}", className="bad" if bad else "", style={"color": col} if bad else {})
                    for prm, v, d, bad in vals],
                id={"type": "tk", "l": l, "t": tank}, n_clicks=0,
                className="tk" + (" warn" if w < NONE_RANK else "") + (" open" if f"{l}|{tank}" in open_ else ""),
                style={"borderColor": edge}))
            if ti < len(tanks) - 1:
                row.append(html.Div(className="pipe"))
        out.append(html.Div(row, className="tanks"))
        for tank, stage, params in tanks:                           # 펼친 조의 그래프를 해당 계열 바로 아래에
            if f"{l}|{tank}" in open_:
                out.append(html.Div([f"{b} · {p} · {l} · ", html.B(tank)], className="xh"))
                out.append(html.Div(
                    [html.Div([sensor_head(plant, plant.find(b, p, l, tank, prm), window),
                               dcc.Graph(figure=sensor_figure(plant, plant.find(b, p, l, tank, prm), window, 230), config=GRAPH_CFG)])
                     for prm in params],
                    style={"display": "grid", "gridTemplateColumns": f"repeat({len(params)},1fr)", "gap": "6px 24px"}))
    return out

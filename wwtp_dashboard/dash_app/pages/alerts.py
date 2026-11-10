"""경고 센터: 알람 타임라인(막대를 누르면 해당 사고로 스크롤) + 표(정렬·필터·CSV) + 사고별 그래프 쭉 나열."""
from __future__ import annotations

import dash
from dash import Input, Output, State, callback, clientside_callback, ctx, dash_table, dcc, html

import store
from charts import sensor_figure
from core import BUILDINGS, KIND, PROCESSES, STEP_MIN
from figs import color_of, kind_name, timeline_figure
from ui import GRAPH_CFG, ctx as get_ctx, legend, page_header, section

dash.register_page(__name__, path="/alerts", name="경고 센터", order=3)


def layout(**_):
    return html.Div([
        html.Div(id="al-head"),
        html.Div([
            html.Div([html.Label("경고 유형"), dcc.Dropdown(id="al-kinds", options=[{"label": kind_name(k), "value": k} for k in KIND],
                                                           value=list(KIND), multi=True, clearable=False)]),
            html.Div([html.Label("공정"), dcc.Dropdown(id="al-p", options=["전체"] + PROCESSES, value="전체", clearable=False)]),
            dcc.Checklist(id="al-act", options=[{"label": " 진행 중만", "value": "on"}], value=["on"]),
        ], className="filters"),
        html.Div(id="al-body"),
        html.Button("더 보기", id="al-more", className="btn", style={"marginTop": "10px"}),
        dcc.Store(id="al-dummy"),
    ], className="page")


@callback(Output("al-head", "children"), Input("data-ver", "data"), State("range", "value"))
def head(_, ridx):
    return page_header(get_ctx(ridx)[0], "경고 센터", "사고(같은 계열·같은 조) 단위 — 위 타임라인으로 언제부터인지 보고, 아래로 스크롤하며 그래프 확인")


@callback(Output("al-n", "data"), Input("al-more", "n_clicks"), Input("al-kinds", "value"), Input("al-p", "value"),
          Input("al-act", "value"), State("al-n", "data"))      # 입력은 이 페이지 것만 (출력이 전역 Store 라서 다른 페이지 컴포넌트를 섞으면 에러)
def paging(_, *args):
    return (args[-1] or 8) + 8 if ctx.triggered_id == "al-more" else 8     # 필터가 바뀌면 처음 8건부터


@callback(Output("al-body", "children"),
          Input("al-kinds", "value"), Input("al-p", "value"), Input("al-act", "value"), Input("bsel", "value"),
          Input("range", "value"), Input("data-ver", "data"), Input("al-n", "data"))
def body(kinds, prc, act, bsel, ridx, _, shown):
    plant, window, ver = get_ctx(ridx)
    bld = None if bsel in (None, "전체") else bsel
    kinds = set(kinds or [])
    inc = [x for x in store.incs(ver, window)
           if (not bld or x["bldg"] == bld) and (prc in (None, "전체") or x["proc"] == prc)
           and (not act or x["active"]) and (set(x["ev"]["kind"]) & kinds)]
    if not inc:
        return html.Div("조건에 맞는 경고가 없습니다.", className="msg")
    n_act = sum(x["active"] for x in inc)
    out = [section("알람 타임라인", f"사고 {len(inc)}건 · 진행 중 {n_act} · 해소 {len(inc) - n_act} · 점선 = 지금 · 막대를 누르면 아래 해당 사고로 이동"),
           dcc.Graph(id="al-tl", figure=timeline_figure(plant, inc, window), config=GRAPH_CFG)]

    rows = [{"시작": f"{x['first']:%m/%d %H:%M}", "위치": x["title"], "조 / 항목": x["what"],
             "경고 종류": " · ".join(kind_name(k) for k in sorted(set(x["ev"]["kind"]), key=lambda k: KIND[k]["rank"])),
             "상태": "진행 중" if x["active"] else "해소", "센서 수": len(x["sids"]),
             "지속(분)": int((x["last"] - x["first"]).total_seconds() // 60) + STEP_MIN} for x in inc]
    out.append(html.Details([html.Summary("표로 보기 · 열 이름을 눌러 정렬, 위 칸에 글자를 쳐서 필터, CSV 내보내기"),
        dash_table.DataTable(data=rows, columns=[{"name": c, "id": c} for c in rows[0]], page_size=10, sort_action="native",
                             filter_action="native", export_format="csv", style_as_list_view=True,
                             style_header={"fontWeight": "800", "backgroundColor": "#f1f5f9", "border": "0"},
                             style_cell={"textAlign": "left", "padding": "5px 10px", "fontSize": "12.5px", "fontFamily": "inherit"},
                             style_data_conditional=[{"if": {"filter_query": '{상태} = "진행 중"', "column_id": "상태"},
                                                      "color": "#dc2626", "fontWeight": "800"}])],
        style={"background": "#fff", "padding": "6px 10px", "border": "1px solid #cbd5e1", "margin": "8px 0"}))

    out.append(section("사고별 그래프", "아래로 스크롤하며 확인"))
    out.append(legend())
    for n, x in enumerate(inc[:shown or 8]):
        ks = [html.Span(kind_name(k), style={"color": KIND[k]["color"]}) for k in sorted(set(x["ev"]["kind"]), key=lambda k: KIND[k]["rank"])]
        ks = [e for k in ks for e in (k, " · ")][:-1]
        cells = []
        for i in x["sids"][:3]:
            m = plant.meta.iloc[i]
            names = ", ".join(kind_name(k) for k in plant.window_kinds(i, window))
            cells.append(html.Div([html.Div(f"{m.tank} · {m.param} — {names}", className="cap"),
                                   dcc.Graph(figure=sensor_figure(plant, i, window, 210), config=GRAPH_CFG)]))
        out.append(html.Div([
            html.Div([html.Span(f"{x['first']:%H:%M} → {x['last']:%H:%M}", className="t"), html.B(x["title"]), html.Span(x["what"], className="w"),
                      html.Span("진행 중" if x["active"] else "해소됨", className="g"), html.Span(ks, className="ks")],
                     className="ih", style={"--c": color_of(x["rank"])}, id=f"inc-{n}"),
            html.Div(cells, className="grid3"),
            html.Div("외 센서: " + ", ".join(f"{plant.meta['tank'].iat[i]} {plant.meta['param'].iat[i]}" for i in x["sids"][3:]), className="cap")
            if len(x["sids"]) > 3 else None]))
    return out


clientside_callback(                                   # 타임라인 막대 클릭 → 서버 거치지 않고 해당 사고로 부드럽게 스크롤
    """function(cd){
        if(!cd){return window.dash_clientside.no_update;}
        var el=document.getElementById('inc-'+cd.points[0].customdata);
        if(el){el.scrollIntoView({behavior:'smooth',block:'start'});}
        return window.dash_clientside.no_update;}""",
    Output("al-dummy", "data"), Input("al-tl", "clickData"), prevent_initial_call=True)

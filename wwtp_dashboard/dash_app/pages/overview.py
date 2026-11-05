"""전체 현황: ① 주요 이상점 → ② 공정 흐름 노드 → ③ 이상점 캔버스 → ④ 공정 상세 트렌드. 셋 중 무엇을 눌러도 같은 '선택'(sel)으로 연동."""
from __future__ import annotations

import dash
import numpy as np
from dash import ALL, Input, Output, Patch, callback, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

import store
from charts import trend_figure
from core import NONE_RANK, PROCESSES
from figs import (IMPACT_COLOR, SEV_COLOR, SEV_TEXT, canvas_figure, headline, ikey, now_worst, sev, sev_ids, stage_name, stages,
                  status_text)
from ui import GRAPH_CFG, ctx as get_ctx, legend, section, sensor_head, state_hash, trig_value

dash.register_page(__name__, path="/", name="전체 현황", order=0)

BANNER_N = 5
STRONG = {"red": "#dc2626", "yellow": "#b45309", "green": "#16a34a"}


def layout(**_):
    return html.Div([
        section("① 주요 이상점", "시급한 순 · 누르면 아래 노드·캔버스·트렌드가 함께 바뀜 (주소에도 담겨 링크로 공유 가능)", first=True),
        html.Div(id="ov-banner"),
        section("② 공정 흐름", "신호등: 초록 정상 · 노랑 확인 필요 · 빨강 조치 필요 · 화살표 색 = 앞 단계 이상의 영향"),
        html.Div(id="ov-flow"),
        section("③ 이상점 요약 캔버스", "", sub_id="ov-canvas-sub"),
        dcc.Loading(dcc.Graph(id="ov-canvas", config=GRAPH_CFG), type="dot", color="#0e7490"),
        html.Div(id="ov-detail"),
    ], className="page")


def _state(ridx, bsel, sel):
    plant, window, ver = get_ctx(ridx)
    all_inc = store.incs(ver, window)
    act = sorted([x for x in all_inc if x["active"]],
                 key=lambda x: (sev(now_worst(plant, x)[0]) != "red", now_worst(plant, x)[0], -x["first"].value))
    order = act + [x for x in all_inc if not x["active"]]
    if sel and sel.get("kind") == "inc" and not any(ikey(x) == tuple(sel["key"]) for x in order):
        sel = None
    if not sel and order:
        sel = {"kind": "inc", "key": list(ikey(order[0]))}
    return plant, window, all_inc, act, sel, (None if bsel in (None, "전체") else bsel)


def _sel_node(sel):
    if not sel:
        return None
    return (sel["key"][1], sel["key"][3]) if sel["kind"] == "inc" else tuple(sel["key"])


# ───────────── 선택: 이상점 바 · 흐름 노드 · 캔버스 점 → 콜백 하나 (패턴 매칭) ─────────────
@callback(Output("sel", "data", allow_duplicate=True),
          Input({"type": "bn", "k": ALL}, "n_clicks"), Input({"type": "fn", "p": ALL, "s": ALL}, "n_clicks"),
          Input("ov-canvas", "clickData"), prevent_initial_call=True)
def select(_bn, _fn, click):
    t = ctx.triggered_id
    if t is None or not (ctx.triggered[0]["value"] if t == "ov-canvas" else trig_value(t)):   # 새로 그려진 버튼(n_clicks=0)은 무시
        raise PreventUpdate
    if t == "ov-canvas":
        cd = click["points"][0].get("customdata")
        cd = cd[0] if isinstance(cd, (list, tuple)) else cd
        return {"kind": "inc", "key": cd.split("|")}
    if t["type"] == "bn":
        return {"kind": "inc", "key": t["k"].split("|")}
    return {"kind": "node", "key": [t["p"], t["s"]]}


# ───────────── ① 바 + ② 흐름 ─────────────
@callback(Output("ov-banner", "children"), Output("ov-flow", "children"),
          Input("data-ver", "data"), Input("range", "value"), Input("bsel", "value"), Input("sel", "data"))
def render_top(_, ridx, bsel, sel):
    plant, window, all_inc, act, sel, b = _state(ridx, bsel, sel)
    sel_inc = tuple(sel["key"]) if sel and sel["kind"] == "inc" else None
    if not act:
        banner = [html.Div("전 공정 정상 — 진행 중인 이상점 없음", className="ok-bar")]
    else:
        banner = []
        for n, x in enumerate(act[:BANNER_N]):
            sv = sev(now_worst(plant, x)[0])
            cls = f"bn {sv}" + (" first" if n == 0 else "") + (" pulse" if sv == "red" else "") + (" sel" if sel_inc == ikey(x) else "")
            banner.append(html.Button(("🚨 " if sv == "red" else "⚠ ") + headline(plant, x) + f" — {SEV_TEXT[sv]}",
                                      id={"type": "bn", "k": "|".join(ikey(x))}, className=cls, n_clicks=0))
        if len(act) > BANNER_N:
            banner.append(html.Div(f"외 {len(act) - BANNER_N}건 진행 중 — 아래 캔버스와 경고 센터에서 모두 볼 수 있어요", className="cap"))

    node_sel, flow = _sel_node(sel), []
    for p in PROCESSES:
        sts = stages(p)
        kw = {"bldg": b} if b else {}
        lsev = sev_ids(plant, plant.sel(proc=p, **kw))[0]
        kids = [html.Div([p, html.Small(f"● {SEV_TEXT[lsev]}", style={"color": SEV_COLOR[lsev]})], className="lane-h")]
        for si, stage in enumerate(sts):
            ids = plant.sel(proc=p, stage=stage, **kw)
            sv, j = sev_ids(plant, ids)
            n_bad = int((plant.now_rank[ids] < NONE_RANK).sum())
            body = [html.Div(f"STAGE {si + 1:02d} · {stage_name(stage)}", className="h"),
                    html.Div(f"● {SEV_TEXT[sv]}", className="st", style={"color": STRONG[sv]}),
                    html.Div(f"이상 {n_bad} / {len(ids)}")]
            if j is not None:
                m = plant.meta.iloc[j]
                body.append(html.Div(f"{m.bldg} {m.line[0]} {m.tank} {m.param} {plant.V[j, -1]:.{int(m.dec)}f}"))
            kids.append(html.Button(body, id={"type": "fn", "p": p, "s": stage},
                                    className=f"fn {sv}" + (" sel" if node_sel == (p, stage) else ""), n_clicks=0))
            if si < len(sts) - 1:                                 # 영향 화살표: 앞 단계가 이상이면 주황/빨강
                kids.append(html.Div([html.B("영향" if sv != "green" else ""), html.I()], className="fa", style={"--c": IMPACT_COLOR[sv]}))
        flow.append(html.Div(kids, className="lane"))
    return banner, flow


# ───────────── ③ 캔버스 ─────────────
@callback(Output("ov-canvas", "figure"), Output("ov-canvas-sub", "children"),
          Input("data-ver", "data"), Input("range", "value"), Input("bsel", "value"), Input("sel", "data"))
def render_canvas(_, ridx, bsel, sel):
    plant, window, all_inc, act, sel, b = _state(ridx, bsel, sel)
    shown = [x for x in all_inc if not b or x["bldg"] == b]
    sel_key = tuple(sel["key"]) if sel and sel["kind"] == "inc" else None
    return (canvas_figure(plant, shown, window, sel_key),
            f"{len(shown)}건 · 이상이 있었던 공정만 · 막대 = 지속 시간, 큰 점 = 지금 진행 중 · 점을 누르면 아래 트렌드로")


# ───────────── ④ 트렌드 ─────────────
@callback(Output("ov-detail", "children"),
          Input("data-ver", "data"), Input("range", "value"), Input("bsel", "value"), Input("sel", "data"))
def render_detail(_, ridx, bsel, sel):
    plant, window, all_inc, act, sel, b = _state(ridx, bsel, sel)
    if not sel:
        return []
    if sel["kind"] == "inc":
        x = next(it for it in all_inc if ikey(it) == tuple(sel["key"]))
        title, sub, sids = f"{x['title']} · {x['what']}", f"{status_text(x['rank'])} · {x['first']:%H:%M}부터", x["sids"][:4]
        proc, bld = x["proc"], x["bldg"]
    else:
        p, stage = sel["key"]
        ids = plant.sel(proc=p, stage=stage, **({"bldg": b} if b else {}))
        bad = [int(i) for i in ids[np.argsort(plant.now_rank[ids], kind="stable")] if plant.now_rank[i] < NONE_RANK]
        title = f"{p} · {stage_name(stage)}" + (f" · {b}" if b else "")
        sub = f"이상 센서 {len(bad)}개" if bad else "이상 없음 — 첫 계열 센서를 보여 줌"
        sids = bad[:4] or [int(i) for i in ids[:2]]
        proc, bld = p, (b or "1동")
    cells = []
    for i in sids:
        fig = trend_figure(plant, i, window)
        fig.update_yaxes(fixedrange=True)                           # 드래그 = 시간 구간 확대만 (연동 줌)
        cells.append(html.Div([sensor_head(plant, i, window),
                               dcc.Graph(id={"type": "trend", "i": int(i)}, figure=fig, config=GRAPH_CFG)]))
    link = dcc.Link("이 공정의 계열·조 흐름도 열기 →", href=f"/process?pb={bld}&pp={proc}{state_hash(ridx, bsel, sel)}", className="tnav")
    return [section("④ 공정 상세 트렌드", f"{title} — {sub}"), html.Div(cells, className="grid2"),
            html.Div(["그래프에서 시간 구간을 드래그하면 나머지 그래프도 같이 확대돼요 (더블클릭 = 되돌리기)  ·  ", link], className="cap"), legend()]


# ───────────── 연동 줌: 한 그래프에서 확대하면 나머지 그래프의 x축만 Patch 로 바꿈 (그림을 다시 만들지 않음) ─────────────
@callback(Output({"type": "trend", "i": ALL}, "figure"),
          Input({"type": "trend", "i": ALL}, "relayoutData"), prevent_initial_call=True)
def link_zoom(rds):
    t = ctx.triggered_id
    rd = trig_value(t) if t is not None else None
    if not rd:
        raise PreventUpdate
    if "xaxis.range[0]" in rd:                                    # 사용자가 드래그로 확대
        rng, auto = [rd["xaxis.range[0]"], rd["xaxis.range[1]"]], False
    elif "xaxis.range" in rd:                                     # 코드로 확대
        rng, auto = list(rd["xaxis.range"]), False
    elif rd.get("xaxis.autorange"):
        rng, auto = None, True
    else:
        raise PreventUpdate
    out = []
    for comp in ctx.outputs_list:
        if comp["id"] == t:
            out.append(no_update)
            continue
        p = Patch()
        p["layout"]["xaxis"]["autorange"] = auto
        if not auto:
            p["layout"]["xaxis"]["range"] = rng
        out.append(p)
    return out

"""폐수처리 공정 품질 현황 대시보드 (데모 데이터, 센서 약 960개).

실행:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="WWTP 품질 관제", page_icon="💧", layout="wide", initial_sidebar_state="collapsed")

import views  # noqa: E402  (set_page_config 이후 import)
from core import KIND, get_plant, incidents  # noqa: E402
from views import RANGES  # noqa: E402

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&display=swap');

/* 사이드바 제거 → 상단 내비 + 헤더 바. 현장 모니터(와이드)에 맞춰 폭을 넓게 */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }
.block-container { padding-top: 4.5rem; max-width: 1920px; }

/* 헤더 바 */
.wwtp-bar { display:flex; align-items:center; gap:14px; padding:10px 16px; margin-bottom:6px;
  background:#ffffff; border:1px solid #cbd5e1; border-left:6px solid #0e7490; border-radius:10px;
  box-shadow:0 1px 3px rgba(15,23,42,.08); }
.wwtp-logo { width:38px; height:38px; border-radius:9px; display:flex; align-items:center; justify-content:center;
  background:#ecfeff; border:1px solid #67e8f9; font-size:20px; }
.wwtp-title { font-weight:800; letter-spacing:.04em; color:#0f172a; font-size:15px; line-height:1.2; }
.wwtp-sub { color:#64748b; font-size:11px; }
.wwtp-live { font-family:'Orbitron',sans-serif; font-size:10px; padding:2px 8px; border-radius:5px;
  color:#0e7490; background:#ecfeff; border:1px solid #67e8f9; margin-left:8px; }
.wwtp-pill { margin-left:auto; padding:6px 14px; border-radius:8px; font-size:13px; font-weight:800; }
.wwtp-pill.bad { color:#ffffff; background:#dc2626; border:1px solid #b91c1c; animation: glow 1.6s infinite; }
.wwtp-pill.ok { color:#ffffff; background:#16a34a; border:1px solid #15803d; }
@keyframes glow { 0%,100% { box-shadow:0 0 0 0 rgba(220,38,38,.55);} 50% { box-shadow:0 0 0 6px rgba(220,38,38,0);} }

/* 카드(테두리 컨테이너) */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background:#ffffff; border:1px solid #d5dde7 !important; border-radius:10px; box-shadow:0 1px 2px rgba(15,23,42,.05);
}
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlockBorderWrapper"] { box-shadow:none; }

/* 숫자는 계기판 폰트 */
[data-testid="stMetricValue"] { font-family:'Orbitron',sans-serif; color:#0e7490; font-weight:700; }
[data-testid="stMetricLabel"] { color:#475569; }
h3 { letter-spacing:.02em; }

/* 전체 현황: KPI 타일 */
.kp { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:10px; margin:4px 0 10px; }
.kt { background:#ffffff; border:1px solid #d5dde7; border-left:8px solid #cbd5e1; border-radius:10px; padding:10px 14px; }
.kt .kl { font-size:13px; color:#475569; font-weight:700; }
.kt .kv { font-family:'Orbitron',sans-serif; font-size:30px; font-weight:700; color:#94a3b8; line-height:1.25; }
.kt .kv small { font-size:15px; color:#64748b; }
.kt.ok .kv { color:#16a34a; }
.kt.hot { color:#ffffff; }
.kt.hot .kl, .kt.hot .kv, .kt.hot .kv small { color:#ffffff; }
.kt.pulse { animation: glow 1.6s infinite; }

/* 전체 현황: 진행 중 경고 띠 */
.tk { display:flex; flex-wrap:wrap; gap:8px; margin:2px 0 12px; }
.tc { padding:7px 12px; border-radius:8px; color:#ffffff; font-size:14px; font-weight:700; }
.tc span { font-weight:500; opacity:.92; }
.tk-ok { padding:10px 14px; border-radius:8px; background:#16a34a; color:#fff; font-weight:800; font-size:15px; margin-bottom:12px; }

/* 전체 현황: 운전 보드 */
.bt { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 12px; font-size:14px; color:#475569; }
.bt > * { white-space:nowrap; }
.bt b { font-size:20px; color:#0f172a; }
.bt .st { font-weight:800; }
.bd-wrap { overflow-x:auto; }
table.bd { border-collapse:collapse; width:100%; font-size:14px; }
table.bd.nr { font-size:13px; }
table.bd.nr td, table.bd.nr th { padding:4px 1px; }
.bd th { background:#334155; color:#ffffff; font-weight:700; font-size:12px; padding:4px 2px; text-align:center;
  border:1px solid #475569; white-space:nowrap; }
.bd tr.h2 th { background:#e2e8f0; color:#1e293b; border-color:#cbd5e1; }
.bd th small { display:block; font-weight:400; color:#64748b; font-size:10px; }
.bd td { background:#ffffff; color:#0f172a; border:1px solid #e2e8f0; text-align:center; padding:5px 2px;
  font-weight:600; font-variant-numeric:tabular-nums; white-space:nowrap; cursor:default; }
.bd td.rb { background:#f1f5f9; color:#0f172a; font-weight:800; font-size:13px; }
.bd td.rl { background:#f8fafc; color:#334155; font-weight:700; font-size:13px; }
.bd tr.bs td { border-top:3px solid #64748b; }
.bd td.k { color:#ffffff; font-weight:800; }
.bd td.res { background:#e2e8f0; color:#64748b; }
.bd td.k-SPEC { animation: blink 1.1s steps(2, start) infinite; }
.bd .ar { font-size:10px; margin-left:2px; opacity:.75; }
@keyframes blink { 50% { background:#7f1d1d; } }
.lg { display:flex; flex-wrap:wrap; gap:6px 14px; font-size:12px; color:#475569; margin:2px 0 8px; align-items:center; }
.lg i { display:inline-block; width:14px; height:14px; border-radius:3px; vertical-align:-2px; margin-right:4px; border:1px solid #cbd5e1; }

/* 공정 상세: 흐름도(조 = 버튼) */
.lh { display:flex; gap:14px; align-items:baseline; margin:14px 0 6px; font-size:13px; } .lh b { color:#0f172a; font-size:14px; }
[class*="st-key-nd-"] button { height:auto; min-height:0; padding:7px 10px; justify-content:flex-start; background:#ffffff; }
[class*="st-key-nd-"] button:hover { background:#ecfeff; }
[class*="st-key-nd-"] button p { font-size:12px; line-height:1.55; text-align:left; margin:0; }
</style>
"""
# 경고 종류별 칸 색 (색 의미는 core.KIND 하나로 고정)
CSS += "<style>" + "".join(f".bd td.k-{k}, .lg i.k-{k} {{ background:{v['color']}; }}" for k, v in KIND.items()) + "</style>"

pages = {
    "overview": st.Page(views.overview, title="전체 현황", icon="🏭", default=True),
    "process": st.Page(views.process, title="공정 상세", icon="🔎", url_path="process"),
    "compare": st.Page(views.compare, title="한눈에 비교", icon="📊", url_path="compare"),
    "alerts": st.Page(views.alerts, title="경고 센터", icon="🚨", url_path="alerts"),
}
st.session_state["_pages"] = pages
nav = st.navigation(list(pages.values()), position="top")

st.markdown(CSS, unsafe_allow_html=True)

plant = get_plant()
n_inc = sum(x["active"] for x in incidents(plant, RANGES[st.session_state.get("range", "24시간")]))
pill = (
    f'<span class="wwtp-pill bad">⚠ 진행 중 사고 {n_inc}건</span>'
    if n_inc
    else '<span class="wwtp-pill ok">● 전 센서 정상</span>'
)
bar, ctl = st.columns([3.2, 1.4], vertical_alignment="center")
bar.markdown(
    f"""<div class="wwtp-bar"><div class="wwtp-logo">💧</div>
    <div><div class="wwtp-title">WWTP QUALITY CONTROL<span class="wwtp-live">LIVE · DEMO</span></div>
    <div class="wwtp-sub">폐수처리 공정 수질 · 센서 {plant.n}개 이상 감지 관제</div></div>{pill}</div>""",
    unsafe_allow_html=True,
)
with ctl:
    c1, c2 = st.columns([3, 1.3], vertical_alignment="bottom")
    c1.select_slider("조회 구간", options=list(RANGES), value="24시간", key="range", help="차트 표시 구간이자 경고 이력 조회 구간")
    with c2.popover("기준", help="경고 기준"):
        st.markdown(
            "- **스펙 이탈** LSL/USL 벗어남\n- **근접** 규격폭 10% 이내\n"
            "- **Hold** 1시간(12샘플) 연속 같은 값\n- **σ 초과** 1시간 이동 표준편차 > 항목별 기준\n"
            "- **동료 대비 이탈** 같은 공정·같은 항목 센서들의 중앙값과 5σ 이상 벌어져 30분 지속 (규격 안이어도 감지)\n"
            "- **개도-투입 불일치** 개도에 비해 투입량·농도가 평소(앞 7일) 관계에서 5σ 이상 벗어나 30분 지속 (막힘·펌프 정지·누설)\n"
            "- **DO↓ 공기개도↑** 2시간 동안 DO 는 떨어지고 공기 밸브는 열리는 게 평소보다 뚜렷하게 30분 지속 (산기관 막힘·부하 급증)\n"
            "- **고분자 부족** 같은 계열 약품(CaOH2·AFR·FR) 투입 대비 Polymer 비율이 평소보다 5σ 낮게 30분 지속"
        )
        if st.button("데모 데이터 새로 만들기", width="stretch"):
            st.cache_resource.clear()
            st.rerun()

nav.run()

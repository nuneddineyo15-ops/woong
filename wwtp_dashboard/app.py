"""폐수처리 공정 품질 현황 대시보드 (데모 데이터, 센서 약 650개).

실행:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="WWTP 품질 관제", page_icon="💧", layout="wide", initial_sidebar_state="collapsed")

import views  # noqa: E402  (set_page_config 이후 import)
from core import get_plant, incidents  # noqa: E402
from views import RANGES  # noqa: E402

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&display=swap');

/* 사이드바 제거 → 상단 내비 + 헤더 바 */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }
.block-container { padding-top: 4.5rem; max-width: 1600px; }

/* 헤더 바 */
.wwtp-bar { display:flex; align-items:center; gap:14px; padding:10px 16px; margin-bottom:6px;
  background: linear-gradient(90deg, rgba(34,211,238,.10), rgba(18,26,43,.0) 70%);
  border:1px solid rgba(34,211,238,.25); border-radius:12px; }
.wwtp-logo { width:38px; height:38px; border-radius:9px; display:flex; align-items:center; justify-content:center;
  background: rgba(34,211,238,.12); border:1px solid rgba(34,211,238,.4); font-size:20px; }
.wwtp-title { font-weight:700; letter-spacing:.04em; color:#f1f5f9; font-size:15px; line-height:1.2; }
.wwtp-sub { color:#64748b; font-size:11px; }
.wwtp-live { font-family:'Orbitron',sans-serif; font-size:10px; padding:2px 8px; border-radius:5px;
  color:#22d3ee; background:rgba(34,211,238,.12); border:1px solid rgba(34,211,238,.4); margin-left:8px; }
.wwtp-pill { margin-left:auto; padding:5px 12px; border-radius:8px; font-size:12px; font-weight:700; }
.wwtp-pill.bad { color:#fca5a5; background:rgba(239,68,68,.15); border:1px solid rgba(239,68,68,.5);
  animation: glow 1.6s infinite; }
.wwtp-pill.ok { color:#86efac; background:rgba(34,197,94,.12); border:1px solid rgba(34,197,94,.4); }
@keyframes glow { 0%,100% { box-shadow:0 0 10px rgba(239,68,68,.6);} 50% { box-shadow:0 0 1px rgba(239,68,68,.2);} }

/* 카드(테두리 컨테이너) */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: rgba(18,26,43,.72); border:1px solid rgba(255,255,255,.07) !important; border-radius:12px;
}
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlockBorderWrapper"] { background: transparent; }

/* 숫자는 계기판 폰트 */
[data-testid="stMetricValue"] { font-family:'Orbitron',sans-serif; color:#22d3ee; font-weight:700; }
[data-testid="stMetricLabel"] { color:#94a3b8; }
h3 { letter-spacing:.02em; }

/* 종합: 지금 확인할 곳 */
.ilist { border:1px solid rgba(255,255,255,.07); border-radius:12px; background:rgba(18,26,43,.72); overflow:hidden; }
.ir { display:grid; grid-template-columns:130px 190px 1fr 90px 70px; gap:10px; padding:9px 14px; font-size:13px;
  border-bottom:1px solid rgba(255,255,255,.05); align-items:center; }
.ir:last-child { border-bottom:none; }
.ik { font-weight:700; } .it { color:#e2e8f0; } .iw { color:#94a3b8; } .ic, .id { color:#64748b; text-align:right; font-size:12px; }

/* 종합: 공정 카드 */
.bh { font-weight:700; color:#cbd5e1; letter-spacing:.05em; margin:14px 0 6px; font-size:13px; }
.pt { display:flex; justify-content:space-between; font-size:14px; margin-bottom:8px; }
.pt b { color:#f1f5f9; font-size:16px; }
.pl { display:flex; gap:6px; margin-bottom:8px; }
.ln { width:30px; text-align:center; padding:2px 0; border:1px solid; border-radius:6px; font-size:12px; font-weight:700; color:#f1f5f9; }
.ps { color:#94a3b8; font-size:12px; margin-bottom:4px; } .ps b { color:#e2e8f0; }

/* 공정 상세: 흐름도(조 = 버튼) */
.lh { display:flex; gap:14px; align-items:baseline; margin:14px 0 6px; font-size:13px; } .lh b { color:#e2e8f0; font-size:14px; }
[class*="st-key-nd-"] button { height:auto; min-height:0; padding:7px 10px; justify-content:flex-start;
  background:rgba(18,26,43,.72); }
[class*="st-key-nd-"] button:hover { background:rgba(34,211,238,.08); }
[class*="st-key-nd-"] button p { font-size:12px; line-height:1.55; text-align:left; margin:0; }
</style>
"""

pages = {
    "overview": st.Page(views.overview, title="종합 현황", icon="🏭", default=True),
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
            "- **동료 대비 이탈** 같은 공정·같은 항목 센서들의 중앙값과 5σ 이상 벌어져 30분 지속 (규격 안이어도 감지)"
        )
        if st.button("데모 데이터 새로 만들기", width="stretch"):
            st.cache_resource.clear()
            st.rerun()

nav.run()

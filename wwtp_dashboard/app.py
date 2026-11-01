"""폐수처리 공정 품질 현황 대시보드 (데모 데이터).

실행:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="WWTP 품질 관제", page_icon="💧", layout="wide", initial_sidebar_state="collapsed")

import views  # noqa: E402  (set_page_config 이후 import)
from core import active_kinds, load_data  # noqa: E402
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
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] [data-testid="stMetric"]),
div[class*="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
  background: rgba(18,26,43,.72); border:1px solid rgba(255,255,255,.07) !important; border-radius:12px;
}

/* 숫자는 계기판 폰트 */
[data-testid="stMetricValue"] { font-family:'Orbitron',sans-serif; color:#22d3ee; font-weight:700; }
[data-testid="stMetricLabel"] { color:#94a3b8; }
h3 { letter-spacing:.02em; }
</style>
"""

pages = {
    "overview": st.Page(views.overview, title="종합 현황", icon="🏭", default=True),
    "alerts": st.Page(views.alerts, title="경고 센터", icon="🚨", url_path="alerts"),
    "explorer": st.Page(views.explorer, title="공정 탐색", icon="🔎", url_path="explorer"),
    "compare": st.Page(views.compare, title="항목별 비교", icon="📊", url_path="compare"),
}
st.session_state["_pages"] = pages
nav = st.navigation(list(pages.values()), position="top")

st.markdown(CSS, unsafe_allow_html=True)

data = load_data()
n_bad = sum(bool(active_kinds(df)) for df in data.values())
pill = (
    f'<span class="wwtp-pill bad">⚠ 진행 중 경고 {n_bad}건</span>'
    if n_bad
    else '<span class="wwtp-pill ok">● 전 센서 정상</span>'
)
bar, ctl = st.columns([3.2, 1.4], vertical_alignment="center")
bar.markdown(
    f"""<div class="wwtp-bar"><div class="wwtp-logo">💧</div>
    <div><div class="wwtp-title">WWTP QUALITY CONTROL<span class="wwtp-live">LIVE · DEMO</span></div>
    <div class="wwtp-sub">폐수처리 공정 수질 · 센서 이상 관제</div></div>{pill}</div>""",
    unsafe_allow_html=True,
)
with ctl:
    c1, c2 = st.columns([3, 1.3], vertical_alignment="bottom")
    c1.select_slider("조회 구간", options=list(RANGES), value="6시간", key="range", help="차트 표시 구간이자 경고 이력 조회 구간")
    with c2.popover("기준", help="경고 기준"):
        st.markdown(
            "- **스펙 이탈** LSL/USL 벗어남\n- **근접** 규격폭 10% 이내\n"
            "- **Hold** 60분 이상 같은 값\n- **σ 초과** 60분 이동 표준편차 > 항목별 기준"
        )
        if st.button("데모 데이터 새로 만들기", width="stretch"):
            st.cache_data.clear()
            st.rerun()

nav.run()

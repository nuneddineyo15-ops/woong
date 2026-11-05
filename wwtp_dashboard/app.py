"""폐수처리 공정 품질 현황 대시보드 (데모 데이터, 센서 약 960개).

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

/* 템플릿 금지: 둥근 카드·그림자·타일 대신 현장 HMI 패널처럼 선과 글자 크기로 구분 */
:root { --mono: 'D2Coding', 'Consolas', 'Menlo', monospace; --ink:#0f172a; --rule:#1e293b; --mute:#64748b; }

/* 사이드바 제거 → 상단 내비 + 헤더 바. 현장 모니터(와이드)에 맞춰 폭을 넓게 */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }
.block-container { padding-top: 4.5rem; max-width: 1920px; }

/* 헤더: 상자 없이 굵은 밑줄 하나 */
.wwtp-bar { display:flex; align-items:center; gap:14px; padding:2px 0 8px; margin-bottom:4px; border-bottom:3px solid var(--rule); }
.wwtp-mark { font-family:var(--mono); font-weight:800; font-size:13px; letter-spacing:.1em; color:#fff; background:var(--rule); padding:7px 9px; }
.wwtp-title { font-weight:800; letter-spacing:.06em; color:var(--ink); font-size:15px; line-height:1.2; }
.wwtp-sub { color:var(--mute); font-size:11px; }
.wwtp-live { font-family:var(--mono); font-size:10px; padding:1px 6px; color:#0e7490; border:1px solid #0e7490; margin-left:8px; }
.wwtp-pill { margin-left:auto; padding:6px 14px; font-size:13px; font-weight:800; font-family:var(--mono); letter-spacing:.04em; }
.wwtp-pill.bad { color:#fff; background:#dc2626; animation: glow 1.6s infinite; }
.wwtp-pill.ok { color:#fff; background:#16a34a; }
@keyframes glow { 0%,100% { box-shadow:0 0 0 0 rgba(220,38,38,.55);} 50% { box-shadow:0 0 0 5px rgba(220,38,38,0);} }

/* 테두리 컨테이너·펼침 상자: 직각, 그림자 없음 */
div[data-testid="stVerticalBlockBorderWrapper"] { background:#ffffff; border:1px solid #cbd5e1 !important; border-radius:0 !important; box-shadow:none; }
[data-testid="stExpander"] details { border-radius:0 !important; border-color:#cbd5e1 !important; background:#ffffff; }

/* 숫자는 계기판 폰트 */
[data-testid="stMetricValue"] { font-family:'Orbitron',sans-serif; color:#0e7490; font-weight:700; }
[data-testid="stMetricLabel"] { color:#475569; }
h3 { letter-spacing:.02em; }
.sec { font-weight:800; font-size:13px; letter-spacing:.08em; color:var(--ink); border-bottom:2px solid var(--rule);
  margin:18px 0 6px; padding-bottom:3px; display:flex; justify-content:space-between; align-items:baseline; }
.sec span { font-weight:400; letter-spacing:0; color:var(--mute); font-size:12px; }

/* 전체 현황 ① 주요 이상점 요약 바 (색·깜빡임은 views._banner 가 바마다 넣음) */
[class*="st-key-bn-"] button { justify-content:flex-start; border:0 !important; border-radius:0 !important; padding:8px 14px !important;
  min-height:0; height:auto; }
[class*="st-key-bn-"] button div { width:100%; justify-content:flex-start; text-align:left; }
[class*="st-key-bn-"] button p { font-size:14px; font-weight:700; text-align:left; color:#ffffff; margin:0; }
[class*="st-key-bn-"] button:hover { filter:brightness(1.08); }
.st-key-bn-0 button { padding:13px 16px !important; }
.st-key-bn-0 button p { font-size:17px; font-weight:800; }
.ok-bar { background:#16a34a; color:#fff; font-weight:800; padding:12px 16px; }
@keyframes pulseR { 0%,100% { box-shadow:0 0 0 0 rgba(220,38,38,0); } 50% { box-shadow:0 0 16px 2px rgba(220,38,38,.55); } }

/* 전체 현황 ② 공정 흐름 노드(신호등 + 글로우) + 영향 화살표 */
[class*="st-key-fn-"] button { height:auto; min-height:0; padding:8px 10px; justify-content:flex-start; border-radius:6px !important; }
[class*="st-key-fn-"] button p { font-size:12px; line-height:1.45; text-align:left; margin:0; color:#475569; }
[class*="st-key-fn-"] button em { font-style:normal; font-weight:800; font-size:13px; color:var(--ink); }
[class*="st-key-fn-"] button strong { font-weight:800; }
@keyframes glowR { 0%,100% { box-shadow:0 0 4px 0 rgba(220,38,38,.25); } 50% { box-shadow:0 0 18px 4px rgba(220,38,38,.5); } }
@keyframes glowY { 0%,100% { box-shadow:0 0 3px 0 rgba(245,158,11,.25); } 50% { box-shadow:0 0 16px 3px rgba(245,158,11,.5); } }
.ln2 { font-weight:800; font-size:16px; color:var(--ink); line-height:1.2; }
.ln2 small { display:block; font-size:11.5px; font-weight:700; margin-top:2px; }
.fa { position:relative; height:40px; }
.fa i { position:absolute; left:0; right:11px; top:24px; height:4px; background:var(--c); }
.fa i::after { content:""; position:absolute; right:-11px; top:-6px; border-left:12px solid var(--c);
  border-top:8px solid transparent; border-bottom:8px solid transparent; }
.fa b { position:absolute; left:0; right:0; top:4px; text-align:center; font-size:10.5px; color:var(--c); }

/* 공정 상세: 계열 머리 + 탱크(버튼) + 탱크 사이 배관 */
.lh { display:flex; gap:12px; align-items:center; margin:16px 0 6px; font-size:13px; font-weight:700;
  border-bottom:1px solid #94a3b8; padding-bottom:4px; }
.lh b { background:var(--rule); color:#fff; font-family:var(--mono); padding:2px 9px; font-size:13px; }
[class*="st-key-nd-"] { position:relative; }
[class*="st-key-nd-"]::after { content:""; position:absolute; top:50%; right:-1rem; width:1rem; height:3px;
  background:#475569; transform:translateY(-50%); }
[class*="st-key-nd-"]::before { content:""; position:absolute; top:50%; right:-1rem; transform:translateY(-50%);
  border-left:8px solid #475569; border-top:6px solid transparent; border-bottom:6px solid transparent; z-index:1; }
[class*="st-key-nd-"] button { height:auto; min-height:0; padding:6px 10px; justify-content:flex-start; background:#ffffff;
  border-radius:0 !important; box-shadow:none !important; }
[class*="st-key-nd-"] button:hover { background:#f1f5f9; }
[class*="st-key-nd-"] button p { font-size:12px; line-height:1.5; text-align:left; margin:0; font-family:var(--mono); color:var(--mute); }
[class*="st-key-nd-"] button em { font-style:normal; font-family:'Malgun Gothic',sans-serif; font-weight:800; font-size:13px; color:var(--ink); }
[class*="st-key-nd-"] button strong { font-weight:800; }
.xh { margin:8px 0 2px; font-size:13px; color:var(--mute); border-left:4px solid #0e7490; padding-left:8px; }
.xh b { color:var(--ink); }

/* 센서 머리글 (카드·metric 위젯 대신 선 하나) */
.sh { border-top:2px solid var(--rule); padding:4px 0 0; display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 10px; }
.sh .p { font-weight:800; font-size:13px; color:var(--ink); }
.sh .v { font-family:var(--mono); font-size:24px; font-weight:700; line-height:1.1; }
.sh .u { color:var(--mute); font-size:12px; margin-left:-6px; }
.sh .dl { font-family:var(--mono); color:var(--mute); font-size:12px; }
.sh .s { margin-left:auto; font-size:12.5px; font-weight:800; }
.sh .x { flex-basis:100%; font-size:11.5px; color:var(--mute); }

/* 경고 센터: 사고 머리 (카드 대신 왼쪽 색 막대 + 굵은 윗선) */
.ih { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 14px; margin:18px 0 6px; padding:6px 10px;
  border-top:2px solid var(--rule); border-left:6px solid var(--c); background:#ffffff; font-size:13px; }
.ih .t { font-family:var(--mono); font-weight:700; color:var(--ink); }
.ih b { font-size:15px; color:var(--ink); }
.ih .w { color:#475569; }
.ih .g { font-family:var(--mono); font-size:11px; padding:1px 6px; border:1px solid currentColor; color:var(--c); }
.ih .ks { margin-left:auto; font-weight:800; }
</style>
"""

pages = {
    "overview": st.Page(views.overview, title="전체 현황", icon=":material/monitor_heart:", default=True),
    "process": st.Page(views.process, title="공정 상세", icon=":material/account_tree:", url_path="process"),
    "compare": st.Page(views.compare, title="한눈에 비교", icon=":material/grid_view:", url_path="compare"),
    "alerts": st.Page(views.alerts, title="경고 센터", icon=":material/notifications:", url_path="alerts"),
}
st.session_state["_pages"] = pages
nav = st.navigation(list(pages.values()), position="top")

st.markdown(CSS, unsafe_allow_html=True)

plant = get_plant()
n_inc = sum(x["active"] for x in incidents(plant, RANGES[st.session_state.get("range", "24시간")]))
pill = (
    f'<span class="wwtp-pill bad">진행 중 사고 {n_inc}</span>'
    if n_inc
    else '<span class="wwtp-pill ok">전 센서 정상</span>'
)
bar, ctl = st.columns([3.2, 1.4], vertical_alignment="center")
bar.markdown(
    f"""<div class="wwtp-bar"><div class="wwtp-mark">WWTP</div>
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

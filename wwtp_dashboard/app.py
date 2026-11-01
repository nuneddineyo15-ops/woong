"""폐수처리 공정 품질 현황 대시보드 (데모 데이터).

실행:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="폐수처리 품질 대시보드", page_icon="💧", layout="wide")

import views  # noqa: E402  (set_page_config 이후 import)
from views import RANGES  # noqa: E402

pages = {
    "overview": st.Page(views.overview, title="종합 현황", icon="🏭", default=True),
    "alerts": st.Page(views.alerts, title="경고 센터", icon="🚨", url_path="alerts"),
    "explorer": st.Page(views.explorer, title="공정 탐색", icon="🔎", url_path="explorer"),
    "compare": st.Page(views.compare, title="항목별 비교", icon="📊", url_path="compare"),
}
st.session_state["_pages"] = pages
nav = st.navigation(list(pages.values()))

with st.sidebar:
    st.divider()
    st.select_slider("조회 구간", options=list(RANGES), value="6시간", key="range",
                     help="차트 표시 구간이자 경고 이력 조회 구간")
    if st.button("데모 데이터 새로 만들기", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.caption(
        "경고 기준\n\n"
        "- 스펙 이탈: LSL/USL 벗어남\n"
        "- 근접: 규격폭 10% 이내\n"
        "- Hold: 60분 이상 같은 값\n"
        "- σ 초과: 60분 이동 표준편차 > 항목별 기준"
    )

nav.run()

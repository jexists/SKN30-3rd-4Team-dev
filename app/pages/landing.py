"""
pages/landing.py — 메인(랜딩) 페이지

로고 + 히어로 + 좌(계약 전·예방) / 우(계약 후·분쟁) 카드.
"바로가기" 클릭 시 해당 채팅 페이지로 이동한다.
"""

import streamlit as st

from ui import inject_css, render_logo

inject_css()

# ── 로고
col_l, col_c, col_r = st.columns([1, 2, 1])
with col_c:
    render_logo(width=180)

# ── 히어로 헤드라인
st.markdown(
    """
    <div class="hero-title">전·월세 계약,<br><b>계약 전부터 계약 후까지</b> 한눈에 도와줄게!</div>
    <div class="hero-sub">표준 임대차 계약서·등기부·특약 분석부터 수리·보증금 분쟁까지, 팩트체커가 함께합니다.</div>
    """,
    unsafe_allow_html=True,
)

# ── 좌/우 카드 (카드 전체가 하나의 클릭 가능한 버튼)
c_left, c_right = st.columns(2)

with c_left:
    if st.button(
        "1단계 · 계약 전\n\n예방\n\n등기부·특약을 분석해 전세사기 위험을 미리 진단해요.",
        key="go_pre", use_container_width=True,
    ):
        st.switch_page("pages/pre.py")

with c_right:
    if st.button(
        "2단계 · 계약 후\n\n분쟁\n\n수리비·보증금 반환 등 거주 중 갈등 대응을 도와드려요.",
        key="go_post", use_container_width=True,
    ):
        st.switch_page("pages/post.py")

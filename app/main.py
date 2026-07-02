"""
main.py — 멀티페이지 앱 엔트리 (사이드바 내비게이션)

실행:  uv run streamlit run app/main.py

사이드바에서 [메인 / 계약 전 (예방) / 계약 후 (분쟁)] 페이지를 선택한다.
각 페이지는 pages/ 아래 별도 파일이며, 백엔드(backend.py)·UI(ui.py)를 공유한다.
"""

import os
import sys

# 페이지 파일(pages/*.py)에서 `from backend import ...`, `from ui import ...` 가
# 항상 해결되도록 app 디렉터리를 sys.path 에 보장 추가.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import streamlit as st

from ui import render_logo, render_sidebar_footer

st.set_page_config(
    page_title="전·월세 분쟁 팩트체커",
    page_icon="⚖️",
    layout="centered",
    initial_sidebar_state="expanded",
)

# 페이지 등록 (자동 내비게이션 위젯은 숨기고, 아래에서 로고 → 메뉴 → 푸터 순서로 직접 배치)
pages = [
    st.Page("pages/landing.py", title="메인", icon="🏠", default=True),
    st.Page("pages/pre.py", title="계약 전 (예방)", icon="🔍"),
    st.Page("pages/post.py", title="계약 후 (분쟁)", icon="⚖️"),
]
pg = st.navigation(pages, position="hidden")

# 사이드바: 로고 → 메뉴 3개 → (여백) → 하단 법률고지 푸터
with st.sidebar:
    render_logo(width=240)
    st.markdown(
        """
        <style>
        [data-testid="stSidebarUserContent"] [data-testid="stCaptionContainer"] p {
            margin-bottom: 0;
        }
        /* 사이드바 메뉴(페이지 링크) 글자 스타일 */
        [data-testid="stSidebarUserContent"] [data-testid="stPageLink-NavLink"] p {
            font-size: 20px !important;
            font-weight: bold !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.divider()
    for page in pages:
        st.page_link(page)
    # margin-top:auto 로 사이드바 맨 아래에 고정 (CSS 는 각 페이지 inject_css 에 정의)
    render_sidebar_footer()

pg.run()

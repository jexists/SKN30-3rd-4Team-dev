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

from ui import render_logo

st.set_page_config(
    page_title="전·월세 분쟁 팩트체커",
    page_icon="⚖️",
    layout="centered",
    initial_sidebar_state="expanded",
)

# 사이드바 상단 로고
with st.sidebar:
    render_logo(width=140)
    st.markdown("### 전·월세 팩트체커")
    st.caption("계약 전 예방 · 계약 후 분쟁")
    st.divider()

# 페이지 등록 → 사이드바에 목록 자동 표시
pages = [
    st.Page("pages/landing.py", title="메인", icon="🏠", default=True),
    st.Page("pages/pre.py", title="계약 전 (예방)", icon="🔍"),
    st.Page("pages/post.py", title="계약 후 (분쟁)", icon="⚖️"),
]

pg = st.navigation(pages)
pg.run()

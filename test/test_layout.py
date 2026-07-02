import streamlit as st

st.set_page_config(
    page_title="전·월세 분쟁 팩트체커",
    page_icon="🏠",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------
# 전역 스타일
# ---------------------------------------------------------
st.markdown(
    """
    <style>
    /* 상단 잘림 현상 해결을 위해 padding-top을 4.5rem으로 확대 조절했습니다 */
    .block-container {max-width: 760px; padding-top: 4.5rem; padding-bottom: 1rem;}
    #MainMenu, footer {visibility: hidden;}

    .topbar {display:flex; align-items:center; justify-content:space-between; margin-bottom:20px;}
    .topbar-left {display:flex; align-items:center; gap:8px; font-size:18px; font-weight:700; color:#1a1a1a;}
    .topbar-nav {display:flex; align-items:center; gap:18px; font-size:13px; color:#6b7280;}

    .greeting-card {
        background:#eaf0ff; border-radius:16px; padding:22px 24px;
        display:flex; gap:14px; align-items:flex-start; margin-bottom:24px;
    }
    .greeting-avatar {
        width:40px; height:40px; min-width:40px; border-radius:50%;
        background:#2f5fe0; display:flex; align-items:center; justify-content:center;
        font-size:18px; color:white;
    }
    .greeting-title {font-size:15px; font-weight:700; color:#1a1a1a; margin:0 0 4px 0;}
    .greeting-desc {font-size:13px; color:#4b5563; margin:0; line-height:1.6;}

    .section-label {font-size:13px; font-weight:600; color:#6b7280; margin:4px 0 10px 2px;}

    .notice-box {
        background:#f3f4f6; border-radius:12px; padding:14px 18px;
        font-size:12px; color:#6b7280; line-height:1.7; margin: 18px 0 24px 0;
    }
    .notice-title {font-weight:700; color:#374151; margin-bottom:4px;}

    .footer-row {
        display:flex; justify-content:space-between; align-items:center;
        font-size:11px; color:#9ca3af; margin-top:28px; padding-top:14px; border-top:1px solid #eee;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# 세션 상태 초기화
# ---------------------------------------------------------
if "step" not in st.session_state:
    st.session_state.step = "before"      # before | after
if "chat_before" not in st.session_state:
    st.session_state.chat_before = []
if "chat_after" not in st.session_state:
    st.session_state.chat_after = []

FAQ_BEFORE = [
    ("📄", "등기부등본에서 확인해야 할 사항은?", "소유자, 근저당권, 가압류 등 등기 확인"),
    ("📋", "전세보증보험은 꼭 가입해야 하나요?", "보증보험의 필요성과 가입 조건 확인"),
    ("📝", "특약에 어떤 내용을 넣어야 할까요?", "보증금 보호를 위한 특약 작성 가이드"),
    ("⚠️", "전세사기 유형과 예방법은?", "최근 사기 사례와 예방 체크포인트"),
]

FAQ_AFTER = [
    ("🔧", "보일러 고장, 수리비는 누가 내나요?", "임대인·임차인 수선 의무 범위 확인"),
    ("💰", "보증금을 돌려받지 못하고 있어요.", "임차권등기명령과 대응 절차 안내"),
    ("🧹", "원상복구 범위는 어디까지인가요?", "통상 마모와 훼손의 법적 구분"),
    ("✉️", "내용증명은 어떻게 작성하나요?", "분쟁 대응을 위한 내용증명 작성법"),
]

# ---------------------------------------------------------
# 상단 바
# ---------------------------------------------------------
st.markdown(
    """
    <div class="topbar">
        <div class="topbar-left">🏠 전·월세 분쟁 팩트체커</div>
        <div class="topbar-nav">이용안내&nbsp;&nbsp;사례보기&nbsp;&nbsp;법률정보&nbsp;&nbsp;자주묻는질문</div>
    </div>
    """,
    unsafe_allow_html=True,
)

top_l, top_r = st.columns([5, 1])
with top_r:
    if st.button("＋ 새 대화", use_container_width=True):
        st.session_state.chat_before = []
        st.session_state.chat_after = []
        st.rerun()

# ---------------------------------------------------------
# 단계 탭: 계약 전 / 계약 후
# ---------------------------------------------------------
tab_col1, tab_col2 = st.columns(2)
with tab_col1:
    if st.button(
        "1단계  계약 전 (예방)",
        use_container_width=True,
        type="primary" if st.session_state.step == "before" else "secondary",
    ):
        st.session_state.step = "before"
        st.rerun()
with tab_col2:
    if st.button(
        "2단계  계약 후 (분쟁)",
        use_container_width=True,
        type="primary" if st.session_state.step == "after" else "secondary",
    ):
        st.session_state.step = "after"
        st.rerun()

st.write("")

is_before = st.session_state.step == "before"
chat_log = st.session_state.chat_before if is_before else st.session_state.chat_after
faq_list = FAQ_BEFORE if is_before else FAQ_AFTER

# ---------------------------------------------------------
# 인사 카드
# ---------------------------------------------------------
if is_before:
    greet_title = "안녕하세요! 계약 전 단계예요."
    greet_desc = "등기부·특약이 걱정되면 서류를 올리거나, 전세사기·보증금 관련해 궁금한 점을 물어보세요."
else:
    greet_title = "안녕하세요! 계약 후 단계예요."
    greet_desc = "보일러 고장, 수리비 부담, 보증금 미반환 등 거주 중 발생한 갈등 상황을 편하게 적어주세요."

st.markdown(
    f"""
    <div class="greeting-card">
        <div class="greeting-avatar">🤖</div>
        <div>
            <p class="greeting-title">{greet_title}</p>
            <p class="greeting-desc">{greet_desc}</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# 자주 묻는 질문 카드
# ---------------------------------------------------------
st.markdown('<div class="section-label">많이 물어보는 질문</div>', unsafe_allow_html=True)

faq_cols = st.columns(2)
for idx, (icon, title, desc) in enumerate(faq_list):
    with faq_cols[idx % 2]:
        with st.container(border=True):
            st.markdown(f"**{icon}  {title}**")
            st.caption(desc)
            if st.button("자세히 보기 →", key=f"faq_{st.session_state.step}_{idx}", use_container_width=True):
                chat_log.append({"role": "user", "content": title})
                chat_log.append(
                    {"role": "assistant", "content": f"'{title}'에 대한 RAG 검색 결과를 바탕으로 답변을 생성합니다. (예시 응답)"}
                )
                st.rerun()

# ---------------------------------------------------------
# 안내사항
# ---------------------------------------------------------
st.markdown(
    """
    <div class="notice-box">
        <div class="notice-title">ⓘ 안내사항</div>
        입력하신 내용은 AI 분석에 활용되며, 저장되지 않습니다.<br>
        법률적 파트너는 아니며, 최종 판단은 전문가와 상담하세요.
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# 대화 내역
# ---------------------------------------------------------
for msg in chat_log:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ---------------------------------------------------------
# 메시지 입력창 (하단 고정)
# ---------------------------------------------------------
placeholder = "등기부·특약 관련 궁금한 점을 입력하세요." if is_before else "집주인과의 갈등 상황을 입력하세요."
user_input = st.chat_input(placeholder, key=f"chat_input_{st.session_state.step}")
if user_input:
    chat_log.append({"role": "user", "content": user_input})
    chat_log.append(
        {"role": "assistant", "content": "주택임대차보호법 및 판례를 기반으로 답변을 생성합니다. (예시 응답)"}
    )
    st.rerun()

# ---------------------------------------------------------
# 푸터
# ---------------------------------------------------------
st.markdown(
    """
    <div class="footer-row">
        <div>개인정보처리방침&nbsp;&nbsp;이용약관&nbsp;&nbsp;저작권정책&nbsp;&nbsp;문의하기</div>
        <div>© 2026 전·월세 분쟁 팩트체커</div>
    </div>
    """,
    unsafe_allow_html=True,
)
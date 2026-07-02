"""
ui.py — 공유 UI 헬퍼

- inject_css():  전역 스타일 (test_layout.py 디자인 + 랜딩 카드 + chat_input 스타일)
- render_sidebar_footer():  사이드바 하단 고정 법률 고지 푸터
- render_chat(stage):  채팅 화면 공통 렌더 (계약 전/후 페이지가 호출)
- LOGO_PATH:  로고 이미지 경로 (없으면 이모지 폴백)
- FAQ_BEFORE / FAQ_AFTER:  단계별 자주 묻는 질문
"""

import os
import uuid
import base64
import tempfile

import streamlit as st

from backend import setup_graph, answer_of

# 로고 경로 (app/assets/logo.png). CWD 와 무관하게 __file__ 기준 절대경로.
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")

# 법률 고지 문구 (푸터 공통)
LEGAL_NOTICE = (
    "※ 본 답변은 법률 정보 제공이며 변호사의 법률 자문이 아닙니다. "
    "구체적 사안은 대한법률구조공단(132) 또는 변호사 상담을 권장합니다."
)

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
# 전역 스타일
# ---------------------------------------------------------
def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {max-width: 820px; padding-top: 3.5rem; padding-bottom: 1rem;}
        #MainMenu, footer {visibility: hidden;}

        .topbar {display:flex; align-items:center; justify-content:space-between; margin-bottom:18px;}
        .topbar-left {display:flex; align-items:center; gap:8px; font-size:19px; font-weight:700; color:#1a1a1a;}

        /* 인사 카드 */
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
            font-size:12px; color:#6b7280; line-height:1.7; margin: 18px 0 12px 0;
        }
        .notice-title {font-weight:700; color:#374151; margin-bottom:4px;}

        /* ── 사이드바 하단 고정 푸터 (법률고지 + 저작권) */
        /* 사이드바 본문을 세로 flex 로 만들어 마지막 요소를 바닥으로 밀어낸다 */
        [data-testid="stSidebarUserContent"] {
            display:flex; flex-direction:column; min-height:calc(100vh - 5rem);
        }
        .sidebar-footer {
            margin-top:100px; padding-top:16px; border-top:1px solid #e6e8ec;
        }
        .sidebar-footer .footer-legal {
            font-size:11px; color:#8a6d1f; line-height:1.6;
            padding-left:10px; border-left:2px solid #e7cf8a; margin-bottom:12px;
        }
        .sidebar-footer .footer-copy {font-size:10.5px; color:#b3b8bf; letter-spacing:.01em;}

        /* 랜딩 히어로 */
        .hero-title {text-align:center; font-size:30px; font-weight:800; color:#1a1a1a;
                     line-height:1.4; margin:8px 0 6px 0;}
        .hero-sub {text-align:center; font-size:14px; color:#6b7280; margin-bottom:26px;}

        /* 랜딩 카드 = 하나의 클릭 가능한 버튼 */
        .st-key-go_pre button, .st-key-go_post button {
            min-height:210px; border-radius:18px; border:none !important; color:#fff !important;
            padding:26px 22px; box-shadow:0 6px 16px rgba(0,0,0,.12); transition:transform .12s ease;
        }
        /* 랜딩 카드 행 아래 여백 */
        .stHorizontalBlock:has(.st-key-go_pre) {margin-bottom:80px;}
        .st-key-go_pre button:hover, .st-key-go_post button:hover {transform:translateY(-3px);}
        .st-key-go_pre button {background:linear-gradient(160deg,#3b82f6,#2563eb) !important;}
        .st-key-go_post button {background:linear-gradient(160deg,#8b5cf6,#6d28d9) !important;}
        /* 버튼 라벨(마크다운) 줄별 타이포 */
        .st-key-go_pre [data-testid="stMarkdownContainer"] p,
        .st-key-go_post [data-testid="stMarkdownContainer"] p {color:#fff !important; margin:0;}
        .st-key-go_pre [data-testid="stMarkdownContainer"] p:nth-child(1),
        .st-key-go_post [data-testid="stMarkdownContainer"] p:nth-child(1) {font-size:13px; opacity:.9;}
        .st-key-go_pre [data-testid="stMarkdownContainer"] p:nth-child(2),
        .st-key-go_post [data-testid="stMarkdownContainer"] p:nth-child(2) {font-size:26px; font-weight:800; margin:10px 0;}
        .st-key-go_pre [data-testid="stMarkdownContainer"] p:nth-child(3),
        .st-key-go_post [data-testid="stMarkdownContainer"] p:nth-child(3) {font-size:13px; opacity:.92; line-height:1.6;}

        /* 하단 고정 입력창 컨테이너 패딩 균일하게 (기본 16px 16px 56px → 16px) */
        [data-testid="stBottomBlockContainer"] {padding:16px !important;}

        /* chat_input 전송 버튼만 노랑 (첨부 📎 버튼은 기본색 유지) */
        [data-testid="stChatInputSubmitButton"] {background:#f5df4e !important; border:none !important;}
        [data-testid="stChatInputSubmitButton"] svg {color:#3b3200 !important; fill:#3b3200 !important;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_logo(width: int = 160) -> None:
    """로고 이미지 표시 (없으면 이모지+텍스트 폴백).

    st.image 는 컬럼 안에서 좌측 정렬되는 이슈가 있어, base64 인라인 이미지를
    text-align:center div 로 감싸 버전·DOM 구조와 무관하게 가운데 정렬한다.
    """
    if os.path.isfile(LOGO_PATH):
        b64 = base64.b64encode(open(LOGO_PATH, "rb").read()).decode()
        st.markdown(
            f"<div style='text-align:center;'>"
            f"<img src='data:image/png;base64,{b64}' width='{width}' "
            f"style='mix-blend-mode:multiply;'/></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div style='font-size:40px; text-align:center;'>🔍⚖️<br>"
            "<span style='font-size:20px; font-weight:800;'>팩트체커</span></div>",
            unsafe_allow_html=True,
        )


def render_sidebar_footer() -> None:
    """사이드바 하단 고정 푸터 — 법률 고지 + 저작권. (with st.sidebar 안에서 호출)"""
    legal = LEGAL_NOTICE.lstrip("※ ").strip()
    st.markdown(
        f"""
        <div class="sidebar-footer">
            <div class="footer-legal">{legal}</div>
            <div class="footer-copy">© 2026 전·월세 분쟁 팩트체커</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------
# 채팅 화면 (계약 전/후 공통)
# ---------------------------------------------------------
_STAGE_META = {
    "pre": {
        "title": "🔍 계약 전 (예방)",
        "greet_title": "안녕하세요! 계약 전 단계예요.",
        "greet_desc": "표준 임대차 계약서·등기부·특약이 걱정되면 서류를 올리거나, 전세사기·보증금 관련해 궁금한 점을 물어보세요.",
        "placeholder": "등기부·특약 관련 궁금한 점을 입력하세요.",
        "faq": FAQ_BEFORE,
    },
    "post": {
        "title": "⚖️ 계약 후 (분쟁)",
        "greet_title": "안녕하세요! 계약 후 단계예요.",
        "greet_desc": "보일러 고장, 수리비 부담, 보증금 미반환 등 거주 중 발생한 갈등 상황을 편하게 적어주세요.",
        "placeholder": "집주인과의 갈등 상황을 입력하세요.",
        "faq": FAQ_AFTER,
    },
}


def _ensure_state(stage: str) -> None:
    tkey, mkey = f"thread_{stage}", f"messages_{stage}"
    if tkey not in st.session_state:
        st.session_state[tkey] = str(uuid.uuid4())
    if mkey not in st.session_state:
        st.session_state[mkey] = []


def render_chat(stage: str) -> None:
    """test_layout.py 디자인 + app.py 백엔드 기능. stage: 'pre' | 'post'."""
    inject_css()
    _ensure_state(stage)
    meta = _STAGE_META[stage]
    tkey, mkey = f"thread_{stage}", f"messages_{stage}"
    chat_log = st.session_state[mkey]

    gs = setup_graph()

    # ── 상단바 + 새 대화
    top_l, top_r = st.columns([5, 1])
    with top_l:
        st.markdown(
            f'<div class="topbar"><div class="topbar-left">{meta["title"]}</div></div>',
            unsafe_allow_html=True,
        )
    with top_r:
        if st.button("＋ 새 대화", use_container_width=True, key=f"new_{stage}"):
            st.session_state[tkey] = str(uuid.uuid4())
            st.session_state[mkey] = []
            st.rerun()

    # # ── 매매 시세 입력 (계약 전 · 전세가율 계산용)
    # market_price = None
    # if stage == "pre":
    #     man = st.number_input(
    #         "매매 시세 (만원) · 전세가율 계산용 · 선택",
    #         min_value=0, step=1000, value=0,
    #         help="등기부·계약서를 첨부하면 보증금은 자동 추출되고, 이 시세로 전세가율을 계산합니다.",
    #     )
    #     market_price = int(man) * 10_000 if man else None   # 만원 → 원

    # ── 백엔드 상태 배너
    if gs["error"]:
        st.warning(gs["error"])
    if not gs["ready"]:
        st.info("백엔드 미연결 — UI 미리보기 모드입니다. (.env 설정 후 새로고침)")

    # 처리 대기(pending) 상태 — FAQ 버튼/입력창이 공통으로 사용.
    #   { "query": 백엔드에 보낼 질문, "docs": 첨부 경로 리스트 or None }
    pkey = f"pending_{stage}"
    if pkey not in st.session_state:
        st.session_state[pkey] = None

    # 대화 시작 전에만 인사 카드 + FAQ 노출. 시작되면(메시지 존재) 숨겨 채팅 화면처럼.
    started = bool(chat_log) or st.session_state[pkey] is not None

    # 인사+FAQ 는 st.empty() 자리에 렌더 → 대화 시작 시 이 자리를 즉시 비워
    #   (답변을 기다리지 않고) 버튼이 곧바로 사라지게 한다.
    intro_ph = st.empty()
    if started:
        intro_ph.empty()
    else:
        with intro_ph.container():
            # ── 인사 카드
            st.markdown(
                f"""
                <div class="greeting-card">
                    <div class="greeting-avatar">🤖</div>
                    <div>
                        <p class="greeting-title">{meta["greet_title"]}</p>
                        <p class="greeting-desc">{meta["greet_desc"]}</p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # ── 자주 묻는 질문 카드 → 클릭 시 입력창 전송과 동일하게 동작
            st.markdown('<div class="section-label">많이 물어보는 질문</div>', unsafe_allow_html=True)
            faq_cols = st.columns(2)
            for idx, (icon, title, desc) in enumerate(meta["faq"]):
                with faq_cols[idx % 2]:
                    with st.container(border=True):
                        st.markdown(f"**{icon}  {title}**")
                        st.caption(desc)
                        if st.button("자세히 보기 →", key=f"faq_{stage}_{idx}", use_container_width=True):
                            chat_log.append({"role": "user", "content": title})
                            st.session_state[pkey] = {"query": title, "docs": None}
                            st.rerun()

    # ── 대화 내역
    for msg in chat_log:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # ── 처리 대기 시, 어시스턴트 로딩 말풍선 '자리'만 미리 확보 (입력창 위).
    #   실제 로딩/답변 처리는 입력창·푸터를 렌더한 뒤 맨 마지막에 수행 →
    #   느린 답변 대기 중에도 입력창과 푸터가 계속 보인다.
    pending = st.session_state[pkey]
    resp_ph = st.empty() if pending else None

    # ── 입력창 (파일 다중 첨부 + 전송). 구버전이면 텍스트 전용 폴백.
    # 본문 최상위에서 직접 호출 → Streamlit 이 화면 하단에 고정(fixed) 시킨다.
    #   (컨테이너로 감싸면 인라인 배치가 되어 고정이 풀린다.)
    try:
        submitted = st.chat_input(
            meta["placeholder"],
            accept_file="multiple",
            file_type=["png", "jpg", "jpeg", "pdf"],
            key=f"chat_input_{stage}",
        )
        _attach_ok = True
    except TypeError:
        submitted = st.chat_input(meta["placeholder"], key=f"chat_input_{stage}")
        _attach_ok = False

    if submitted:
        # 반환형 정규화: 첨부 지원 시 객체(text/files), 아니면 문자열
        if _attach_ok:
            text = (submitted.text or "").strip()
            files = submitted.files or []
        else:
            text, files = str(submitted).strip(), []

        # 첨부 파일 전부 저장 → document_paths 리스트
        doc_paths = []
        for up in files:
            p = os.path.join(tempfile.gettempdir(), up.name)
            with open(p, "wb") as fp:
                fp.write(up.getbuffer())
            doc_paths.append(p)

        # 사용자 말풍선(첨부 파일명 표시)
        shown = text or "(파일 첨부)"
        if files:
            shown += "　📎 " + ", ".join(f.name for f in files)
        chat_log.append({"role": "user", "content": shown})

        # FAQ 버튼과 동일하게 pending 으로 넘기고 즉시 리런 → 사용자 말풍선 먼저 표시
        st.session_state[pkey] = {
            "query": text or "업로드한 서류를 분석해줘",
            "docs": doc_paths or None,
        }
        st.rerun()

    # ── 처리 대기 답변 (맨 마지막): 위에서 확보한 resp_ph 자리를 로딩→답변으로 채운다.
    #   입력창이 이미 렌더된 뒤라, 느린 답변을 기다리는 동안에도 계속 보인다.
    if pending:
        with resp_ph.container():
            with st.chat_message("assistant"):
                with st.spinner("근거를 찾는 중…"):
                    reply = answer_of(
                        gs, st.session_state[tkey],
                        pending["query"],
                        # stage, pending["docs"], market_price,   # market_price 입력란 주석 처리로 비활성화
                        stage, pending["docs"], None,
                    )
        chat_log.append({"role": "assistant", "content": reply})
        st.session_state[pkey] = None
        st.rerun()

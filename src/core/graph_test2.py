"""
graph2.py
전·월세 분쟁 팩트체커 — LangGraph 상태 그래프 (터미널 실시간 대화 버전)

구조:
  parent: START → (entry_router) → pre_contract | post_contract → 공통 응답 파이프라인 → END
  pre subgraph : 문서 여부 라우팅 → OCR·서류분석·전세가율·위험판정 | 계약 질의 분석 → 컨텍스트
  post subgraph: 쟁점 분류 → 컨텍스트
  공통 파이프라인: retrieve → grade(→쿼리 재작성 루프) → generate → verify(→재생성 루프) → 법적 고지

검색은 vs_method.search_similar(kb_chunks / pgvector) 사용.
멀티턴은 그래프 내부 루프가 아니라 MemorySaver + thread_id 로 상태를 유지하고 매 턴 재호출한다.
"""

from __future__ import annotations

import json
from typing import Optional

from typing_extensions import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
from dotenv import load_dotenv
import os

load_dotenv()

import vs_method  # search_similar / get_conn (kb_chunks)

# ──────────────────────────────────────────────
# LLM / 검색 연결
# ──────────────────────────────────────────────
llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0)

MAX_RETRIEVAL_ATTEMPTS = 2
MAX_VERIFY_ATTEMPTS = 2

_conn = None
def conn():
    global _conn
    if _conn is None:
        _conn = vs_method.get_conn()
    return _conn


def _llm_json(prompt: str) -> dict:
    """LLM 응답을 JSON 으로 강제 파싱. 실패 시 빈 dict."""
    raw = llm.invoke(prompt + "\n\nJSON 객체만 출력. 설명·마크다운 금지.").content
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# ──────────────────────────────────────────────
# 공유 State
# ──────────────────────────────────────────────
class FactCheckState(TypedDict, total=False):
    # 입력 / 세션
    stage: str                       # 'pre' | 'post'
    question: str
    has_document: bool
    document_path: Optional[str]
    messages: Annotated[list, add_messages]
    # 계약 전 산출물
    document_text: Optional[str]
    findings: Optional[dict]          # 근저당·선순위·보증금 등
    risk_result: Optional[dict]       # {level, ratio, reasons}
    # 검색 / 생성 공통
    query: str
    issues: list
    retrieved: list
    retrieval_attempts: int
    answer: str
    verify_attempts: int


# ══════════════════════════════════════════════
# 외부 파이프라인 스텁 (남진님 기존 모듈에 연결)
# ══════════════════════════════════════════════
def run_ocr(document_path: str) -> str:
    # TODO: pdf2image + pytesseract 한글 OCR 파이프라인 연결
    raise NotImplementedError("OCR 파이프라인 연결 필요")


def fetch_market_price(address: str) -> int:
    # TODO: 실시간 시세 API 연결 → 매매 시세(원) 반환
    raise NotImplementedError("실시간 시세 API 연결 필요")


# ══════════════════════════════════════════════
# 계약 전 서브그래프
# ══════════════════════════════════════════════
def pre_entry_router(state: FactCheckState) -> str:
    return "doc" if state.get("has_document") else "question"


def ocr_extract(state: FactCheckState) -> dict:
    return {"document_text": run_ocr(state["document_path"])}


def analyze_document(state: FactCheckState) -> dict:
    """등기부·계약서 텍스트에서 근저당·선순위·보증금·특약 추출 (LLM)."""
    data = _llm_json(
        "당신은 부동산 등기부등본 및 임대차계약서 분석 전문가입니다. 제공된 텍스트에서 '오직 명시된 사실'만을 기반으로 위험 요소를 추출하세요. 절대 추측하거나 없는 값을 임의로 채워 넣어서는 안 됩니다.\n\n"
        "지정된 Key별 데이터 추출 규칙:\n"
        "- deposit: 임대차 보증금 총액 (반드시 정수 숫자로만 추출, 파악 불가 시 0)\n"
        "- senior_debt: 근저당권 채권최고액, 선순위 확정일자 보증금 등 선순위 채권 총액 합계 (정수 숫자, 없으면 0)\n"
        "- address: 목적물 소재지 주소 (상세 주소를 포함한 문자열, 미기재 시 빈 문자열)\n"
        "- special_terms: 계약서 특약사항란에 기재된 문장들의 리스트 (리스트 형식)\n"
        "- flags: 독소조항, 임차인 권리 제한 조항, 임대인의 담보제공 금지 위반 등 위험 요소가 감지된 특약 요약 (리스트 형식)\n\n"
        f"[문서 텍스트 스니펫]:\n{state['document_text'][:4000]}"
    )
    return {"findings": data}


def calc_jeonse_ratio(state: FactCheckState) -> dict:
    """결정론적 계산: (보증금 + 선순위채권) / 매매시세.  LLM 아님."""
    f = state.get("findings") or {}
    deposit = int(f.get("deposit") or 0)
    senior = int(f.get("senior_debt") or 0)
    price = fetch_market_price(f.get("address", "")) or 1
    ratio = round((deposit + senior) / price, 3)
    return {"findings": {**f, "jeonse_ratio": ratio, "market_price": price}}


def assess_risk(state: FactCheckState) -> dict:
    """결정론적 임계값 판정."""
    f = state.get("findings") or {}
    ratio = f.get("jeonse_ratio", 0)
    reasons, level = [], "low"
    if ratio >= 0.8:
        level, r = "high", f"전세가율 {ratio:.0%} (깡통전세 위험 구간)"
        reasons.append(r)
    elif ratio >= 0.7:
        level = "medium"
        reasons.append(f"전세가율 {ratio:.0%} (경계 구간)")
    if f.get("senior_debt"):
        reasons.append("선순위 근저당 존재 → 우선변제 순위 확인 필요")
    return {"risk_result": {"level": level, "ratio": ratio, "reasons": reasons}}


def analyze_pre_query(state: FactCheckState) -> dict:
    """질문에서 검색 쿼리·쟁점 태그 추출 (LLM)."""
    data = _llm_json(
        "당신은 부동산 계약 전(안전성 진단, 가계약, 특약 설계) 단계의 임차인 질의 분석 전문가입니다. 질문자의 의도를 파악하여 법률 지식 데이터베이스(Vector DB) 검색에 가장 최적화된 쿼리와 관련 쟁점 태그를 추출하세요.\n\n"
        "지정된 Key별 추출 규칙:\n"
        "- query: 검색 모델이 법령, 판례, 유권해석을 정확히 찾을 수 있도록 명확하고 정제된 형태의 핵심 검색 문장 (질문자의 감정이나 군더더기 단어 제외)\n"
        "- issues: 다음 태그 리스트 중 질문과 밀접하게 연관된 핵심 쟁점 태그들만 엄선하여 리스트로 반환 (해당 항목이 없으면 빈 리스트)\n"
        "  [허용 태그: 'deposit'(보증금 반환/보증보험), 'opposing_power'(대항력/확정일자), 'priority_repayment'(최우선변제금), 'fraud'(전세사기/위험판정), 'special_terms'(가계약 및 특약사항)]\n\n"
        f"질문: {state.get('question','')}"
    )
    return {"query": data.get("query", state.get("question", "")),
            "issues": data.get("issues", [])}


def build_pre_context(state: FactCheckState) -> dict:
    """위험 판정 결과가 있으면 검색 쿼리·쟁점에 병합. stage 고정."""
    out = {"stage": "pre", "retrieval_attempts": 0, "verify_attempts": 0}
    risk = state.get("risk_result")
    if risk and risk["reasons"]:
        out["query"] = state.get("query", "") + " / " + "; ".join(risk["reasons"])
        out["issues"] = list({*state.get("issues", []), "fraud", "priority_repayment"})
    return out


def build_pre_graph():
    g = StateGraph(FactCheckState)
    g.add_node("ocr_extract", ocr_extract)
    g.add_node("analyze_document", analyze_document)
    g.add_node("calc_jeonse_ratio", calc_jeonse_ratio)
    g.add_node("assess_risk", assess_risk)
    g.add_node("analyze_pre_query", analyze_pre_query)
    g.add_node("build_pre_context", build_pre_context)

    g.add_conditional_edges(START, pre_entry_router,
                            {"doc": "ocr_extract", "question": "analyze_pre_query"})
    g.add_edge("ocr_extract", "analyze_document")
    g.add_edge("analyze_document", "calc_jeonse_ratio")
    g.add_edge("calc_jeonse_ratio", "assess_risk")
    g.add_edge("assess_risk", "analyze_pre_query")   # 문서 경로도 질의 분석으로 합류
    g.add_edge("analyze_pre_query", "build_pre_context")
    g.add_edge("build_pre_context", END)
    return g.compile()


# ══════════════════════════════════════════════
# 계약 후 서브그래프
# ══════════════════════════════════════════════
def classify_issue(state: FactCheckState) -> dict:
    """수리·분쟁 질문에서 쟁점 분류 + 검색 쿼리 (LLM)."""
    data = _llm_json(
        "당신은 임대차 계약 체결 이후 발생한 분쟁(유지보수, 계약갱신, 퇴거, 보증금 미반환) 단계의 임차인 질의 분석 전문가입니다. 법률 지식 데이터베이스 검색에 최적화된 검색 문장과 관련 쟁점 태그를 정확히 분류하세요.\n\n"
        "지정된 Key별 추출 규칙:\n"
        "- query: 판례나 주택임대차분쟁조정위원회 사례집에서 유사 사례를 찾을 수 있도록 정제된 핵심 법적 검색 문장\n"
        "- issues: 다음 태그 리스트 중 해당 분쟁과 직접 연관된 쟁점 태그들만 리스트로 반환 (해당 항목이 없으면 빈 리스트)\n"
        "  [허용 태그: 'deposit'(보증금 미반환/임차권등기명령), 'repair'(수선의무/결로·누수 분쟁), 'contract_renewal'(계약갱신요구권/상속/양도), 'eviction'(명도/퇴거 의무/해지 통지), 'maintenance_duty'(원상복구 의무/관리비·공과금)]\n\n"
        f"질문: {state.get('question','')}"
    )
    return {"stage": "post",
            "query": data.get("query", state.get("question", "")),
            "issues": data.get("issues", []),
            "retrieval_attempts": 0, "verify_attempts": 0}


def build_post_graph():
    g = StateGraph(FactCheckState)
    g.add_node("classify_issue", classify_issue)
    g.add_edge(START, "classify_issue")
    g.add_edge("classify_issue", END)
    return g.compile()


# ══════════════════════════════════════════════
# 공통 응답 파이프라인
# ══════════════════════════════════════════════
def retrieve(state: FactCheckState) -> dict:
    """pgvector 하이브리드 검색 (stage + issue 필터). binding·persuasive 함께 가져와 뒤에서 층 분리."""
    hits = vs_method.search_similar(
        conn(),
        query=state["query"],
        stage=state["stage"],
        issues=state.get("issues") or None,
        k=8,
        min_score=0.30,
    )
    return {"retrieved": hits}


def grade_documents(state: FactCheckState) -> dict:
    """검색 결과가 질문을 커버하는지 판정 (관련성 평가)."""
    ctx = "\n".join(f"- ({h['authority']}) [{h.get('law_name') or h.get('doc_title', '알 수 없음')}] {h['content'][:120]}" for h in state["retrieved"])
    v = _llm_json(
        "당신은 검색된 임대차 법률 조항 및 판례 조각들이 사용자 질문에 왜곡이나 추측 없이 '논리적으로 완벽한 답변'을 제공하기에 충분한지 심사하는 엄격한 법률 감사관입니다.\n\n"
        "판정 기준 및 Key 설명:\n"
        "- sufficient: 검색된 근거만으로 질문에 명확한 답변을 내릴 수 있다면 true, 만약 핵심 법령이나 직접적인 판례 근거가 누락되어 추측성 답변을 해야만 하는 상황이라면 무조건 false로 판단하십시오. (boolean)\n"
        "- gap: sufficient가 false인 경우, 사용자의 질문을 명확히 해결하기 위해 추가로 검색해야 하거나 보완이 필요한 구체적인 법적 키워드나 누락된 쟁점을 기술하는 한 문장 (sufficient가 true인 경우 빈 문자열)\n\n"
        f"진단할 검색 쿼리: {state['query']}\n"
        f"검색된 법률/판례 근거 목록:\n{ctx or '(검색 결과 없음)'}"
    )
    return {"_grade": v}  # 임시 채널 (라우터에서 읽고 버림)


def grade_router(state: FactCheckState) -> str:
    v = state.get("_grade", {})
    if v.get("sufficient"):
        return "generate"
    if state.get("retrieval_attempts", 0) < MAX_RETRIEVAL_ATTEMPTS:
        return "rewrite"
    return "generate"  # 상한 초과 → 있는 근거로 진행(부족 고지)


def rewrite_query(state: FactCheckState) -> dict:
    """부족한 부분을 반영해 쿼리 재작성 후 재검색 루프."""
    gap = state.get("_grade", {}).get("gap", "")
    new_q = llm.invoke(
        f"원 검색 쿼리: {state['query']}\n"
        f"현재 검색 데이터의 부족한 점(누락 항목): {gap}\n\n"
        "위 부족한 점을 보완하여 법률 규정 및 판례 문서가 정확히 검색될 수 있도록 고도화된 정밀 검색어(키워드 중심의 명확한 한 문장)를 재작성하세요. 다른 설명 없이 문장만 출력하십시오."
    ).content.strip()
    return {"query": new_q, "retrieval_attempts": state.get("retrieval_attempts", 0) + 1}


def generate(state: FactCheckState) -> dict:
    """근거 기반 답변 생성. 결론은 binding, 사례는 persuasive 로 층 분리."""
    binding = [h for h in state["retrieved"] if h["authority"] == "binding"]
    persuasive = [h for h in state["retrieved"] if h["authority"] == "persuasive"]
    ref = [h for h in state["retrieved"] if h["authority"] == "reference"]

    def fmt(hs):
        return "\n".join(
            f"- ID: {h.get('id') or 'N/A'} | 출처: [{h.get('law_name') or h.get('doc_title', '미명시')}] {h.get('article') or ''}\n  내용: {h['content'][:300]}"
            for h in hs) or "(제공된 근거 없음)"

    risk = state.get("risk_result")
    risk_txt = f"\n[서류 기반 위험 진단 결과] 위험 수준: {risk['level']} / 진단 사유: {'; '.join(risk['reasons'])}" if risk else ""

    # 할루시네이션 완벽 방지 및 출처 표기 의무화 프롬프트 구축
    answer = llm.invoke(
        "당신은 주택임대차보호법 및 부동산 분쟁 조정 사례에 정통한 공인 전문 법률 정보 도우미입니다. 오직 아래 제공된 법령, 판례, 사례 데이터만을 사용하여 답변을 작성하십시오.\n\n"
        "★ [엄격한 할루시네이션 방지 및 출처 표기 규칙] ★\n"
        "1. 제공된 근거 자료에 기재되어 있지 않은 사실을 자의적으로 유추하거나, '그럴 것이다' 형태의 추측성 단정, 외부 지식을 활용한 법적 판단은 절대로 금지합니다. 철저히 제공된 데이터 안에서만 답변하십시오.\n"
        "2. 특정 문장이나 항목을 작성할 때는 해당 문장 끝에 반드시 그 근거가 된 데이터의 출처(예: [출처: 주택임대차보호법 제O조] 또는 [출처: OO지방법원 판례])를 괄호 형태로 명확히 기재하십시오.\n"
        "3. 만약 제공된 데이터만으로 사용자의 질문에 대한 명확한 결론을 도출하기 어렵거나 근거가 매칭되지 않는다면, 억지로 답변을 꾸며내지 말고 '제공된 법령 및 판례 근거 내에서는 관련 내용을 명확히 확인할 수 없습니다.'라고 솔직하게 답변에 명시하십시오.\n\n"
        "■ 답변의 논리 구조 구성 방식:\n"
        "- [해결 결론 및 법적 근거]: [강제력 있는 법령·판례(binding)] 항목의 데이터를 기반으로 질문에 대한 명확한 법적 결론과 권리 관계를 명시하고 출처 조항을 연계하세요.\n"
        "- [유사 사례 참고]: [하급심/조정 사례(persuasive)] 항목의 데이터를 활용하여 실제 기관에서 어떻게 판단했었는지 참고용 사례로 서술하세요.\n"
        "- [임차인 대응 가이드]: [실무 참고(reference)] 및 위험 진단 내용을 기반으로 임차인이 당장 취해야 할 실무적 조치나 주의사항을 안내하세요.\n\n"
        f"{risk_txt}\n\n"
        f"[제공된 강제력 있는 법령·판례 (binding)]\n{fmt(binding)}\n\n"
        f"[제공된 하급심/조정 사례 (persuasive)]\n{fmt(persuasive)}\n\n"
        f"[제공된 실무 참고 (reference)]\n{fmt(ref)}\n\n"
        f"사용자 질문: {state.get('question','')}"
    ).content.strip()
    return {"answer": answer}


def verify(state: FactCheckState) -> dict:
    """답변이 검색 근거에 충실한지(환각 여부) 검증."""
    ctx = "\n".join(f"- 출처: [{h.get('law_name') or h.get('doc_title', '미명시')}] {h.get('article') or ''} | 내용: {h['content'][:150]}" for h in state["retrieved"])
    v = _llm_json(
        "당신은 작성된 법률 답변서가 제공된 날것의 검색 근거 문서들과 완벽하게 일치하는지 심사하는 최종 준법감시인(Compliance Officer)입니다.\n\n"
        "판정 기준 및 Key 설명:\n"
        "- faithful: 답변에 명시된 모든 법적 단정, 권리 관계, 수치, 사실관계가 아래 제공된 '근거 문서 목록'에 있는 내용과 100% 일치하고, 근거가 없거나 유추해낸 할루시네이션 내용이 전혀 없다면 true, 단 하나라도 근거가 없거나 왜곡된 문장, 출처 누락이 있다면 false를 반환하십시오. (boolean)\n"
        "- problem: faithful이 false인 경우, 제공된 근거 범위를 이탈하여 과장되거나 왜곡된 부분, 또는 근거 문서에 존재하지 않는데 임의로 단정한 문장을 찾아내어 구체적으로 지적하는 한 문장 (faithful이 true인 경우 빈 문자열)\n\n"
        f"[제공된 실제 근거 문서 목록]:\n{ctx}\n\n"
        f"[생성된 법률 답변]:\n{state['answer']}"
    )
    return {"_verify": v}


def verify_router(state: FactCheckState) -> str:
    v = state.get("_verify", {})
    if v.get("faithful"):
        return "notice"
    if state.get("verify_attempts", 0) < MAX_VERIFY_ATTEMPTS:
        return "regenerate"
    return "notice"  # 상한 초과 → 고지에 한계 명시


def bump_verify(state: FactCheckState) -> dict:
    return {"verify_attempts": state.get("verify_attempts", 0) + 1}


DISCLAIMER = ("\n\n---\n※ 본 답변은 제공된 법률 데이터 및 서류 정보를 기반으로 한 사실 확인 참고용 정보 제공이며, 변호사의 공식적인 법률 자문이 아닙니다. "
              "구체적인 분쟁 해결 및 사안의 조율을 위해서는 대한법률구조공단(국번없이 132) 또는 변호사 전문 상담을 이용하시기 바랍니다.")


def legal_notice(state: FactCheckState) -> dict:
    """법적 고지 부착 후 최종 답변 확정 + 세션 기록."""
    final = state["answer"] + DISCLAIMER
    return {"answer": final, "messages": [AIMessage(content=final)]}


# ══════════════════════════════════════════════
# 부모 그래프
# ══════════════════════════════════════════════
def entry_router(state: FactCheckState) -> str:
    return "pre_contract" if state.get("stage") == "pre" else "post_contract"


def build_app():
    g = StateGraph(FactCheckState)

    # 서브그래프를 노드로 장착 (State 공유)
    g.add_node("pre_contract", build_pre_graph())
    g.add_node("post_contract", build_post_graph())

    # 공통 파이프라인
    g.add_node("retrieve", retrieve)
    g.add_node("grade", grade_documents)
    g.add_node("rewrite_query", rewrite_query)
    g.add_node("generate", generate)
    g.add_node("verify", verify)
    g.add_node("bump_verify", bump_verify)
    g.add_node("legal_notice", legal_notice)

    # 진입 라우팅
    g.add_conditional_edges(START, entry_router,
                            {"pre_contract": "pre_contract", "post_contract": "post_contract"})
    g.add_edge("pre_contract", "retrieve")
    g.add_edge("post_contract", "retrieve")

    # 검색 → 관련성 평가 (→ 쿼리 재작성 루프)
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", grade_router,
                            {"generate": "generate", "rewrite": "rewrite_query"})
    g.add_edge("rewrite_query", "retrieve")

    # 생성 → 충실성 검증 (→ 재생성 루프)
    g.add_edge("generate", "verify")
    g.add_conditional_edges("verify", verify_router,
                            {"notice": "legal_notice", "regenerate": "bump_verify"})
    g.add_edge("bump_verify", "generate")
    g.add_edge("legal_notice", END)

    return g.compile(checkpointer=MemorySaver())


app = build_app()


# ──────────────────────────────────────────────
# 한 턴 실행 헬퍼 (멀티턴 = 같은 thread_id 로 재호출)
# ──────────────────────────────────────────────
def run_turn(thread_id: str, question: str, *, stage: str,
             has_document: bool = False, document_path: str | None = None) -> str:
    cfg = {"configurable": {"thread_id": thread_id}}
    out = app.invoke(
        {"question": question, "stage": stage,
         "has_document": has_document, "document_path": document_path},
        config=cfg,
    )
    return out["answer"]


# ══════════════════════════════════════════════
# 🛠️ 실시간 터미널 대화용 실행 블록 (수정된 파트)
# ══════════════════════════════════════════════
if __name__ == "__main__":
    import uuid
    
    # 1. 세션 구분을 위한 고유 thread_id 발급
    thread_id = str(uuid.uuid4())[:8]
    print(f"\n==================================================")
    print(f"🏠 전·월세 분쟁 팩트체커 실행 (세션 ID: {thread_id})")
    print(f"==================================================")
    print("※ 종료하려면 '종료' 또는 'exit'를 입력하세요.\n")
    
    # 2. 계약 단계 최초 1회 선택
    while True:
        stage_input = input("현재 어떤 단계의 질의인가요?\n(1: 계약 전/안전성 진단, 2: 계약 후/분쟁 발생) ➡️ 번호 입력: ").strip()
        if stage_input in ["1", "2"]:
            stage = "pre" if stage_input == "1" else "post"
            break
        print("❌ 잘못된 입력입니다. 1 또는 2를 입력해 주세요.\n")
        
    print(f"\n➡️ [{'계약 전' if stage=='pre' else '계약 후'}] 모드로 실시간 대화를 시작합니다.")
    
    # 3. 사용자 입력 대화 루프 시작
    while True:
        question = input("\n👤 임차인 질문 입력: ").strip()
        
        # 종료 조건
        if question.lower() in ["종료", "exit", "quit"]:
            print("\n👋 팩트체커 프로그램을 종료합니다. 안전한 거래 되세요!")
            break
            
        if not question:
            print("⚠️ 질문을 입력해 주세요.")
            continue
            
        print("\n🔍 관련 법령 및 판례 검색 중... 잠시만 기다려주세요...")
        
        try:
            # 상태 그래프 재호출 (동일한 thread_id로 이전 문맥 유지 가능)
            answer = run_turn(thread_id=thread_id, question=question, stage=stage)
            print(f"\n🤖 [팩트체커 답변]:\n{answer}")
            print(f"\n" + "─"*50)
        except Exception as e:
            print(f"\n❌ 에러가 발생했습니다: {e}")
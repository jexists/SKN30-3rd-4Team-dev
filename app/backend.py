"""
backend.py — 그래프 백엔드 공유 모듈

app.py 의 백엔드 로직(그래프 셋업 · run_turn 호출)을 그대로 이식해
멀티페이지(main.py / pages/*.py)에서 공유한다.

핵심: setup_graph() 가 graph(app) 를 프로세스당 1회 빌드해 @st.cache_resource 로 캐시.
      → MemorySaver 단일 인스턴스 유지(멀티턴 보존), 페이지 이동/rerun 마다 재빌드 안 함.
"""

import os
import sys

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


# graph.py / vs_method.py 가 있는 src/core 를 위로 거슬러 올라가며 자동 탐색
def _find_src_core():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        cand = os.path.join(d, "src", "core")
        if os.path.isfile(os.path.join(cand, "graph.py")):
            return cand
        parent = os.path.dirname(d)
        if parent == d:            # 루트 도달
            break
        d = parent
    return None


SRC_DIR = _find_src_core()

# graph / vs_method 가 os.environ 으로 읽는 키들 (st.secrets → 환경변수로 승격)
SECRET_KEYS = ("OPENAI_API_KEY", "DB_URL", "LANGCHAIN_TRACING_V2", "LANGSMITH_API_KEY")


def _secret(key: str, default=None):
    """우선순위: st.secrets(Cloud/.streamlit/secrets.toml) → 환경변수(.env)."""
    try:
        if key in st.secrets:            # secrets 파일 없으면 예외 → 폴백
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)


def _load_secrets_into_env() -> None:
    """백엔드(graph/vs_method)가 os.environ 을 읽으므로, secrets 값을 환경변수로 밀어넣는다."""
    load_dotenv()  # 로컬 .env 폴백
    for k in SECRET_KEYS:
        val = _secret(k)
        if val is not None and val != "":
            os.environ[k] = str(val)


# ══════════════════════════════════════════════
# 그래프 셋업 (프로세스당 1회 · 캐시)
# ══════════════════════════════════════════════
@st.cache_resource(show_spinner="⚙️ 그래프 초기화 중…")
def setup_graph() -> dict:
    """
    graph 모듈(app/run_turn)을 1회 로드·빌드해 캐시한다.
    반환: {"module", "ready", "error", "db_ready"}  (실패해도 UI 는 뜨도록 예외 대신 dict)

    - st.secrets → os.environ 승격 후 import (백엔드는 os.environ 만 사용)
    - @st.cache_resource: 세션·rerun·페이지 이동 across 로 동일 객체 공유 → MemorySaver 하나로 멀티턴 유지
    - 필수값 확인 → import graph(빌드) → DB 스키마 보장(첫 질문 지연/실패 방지)
    """
    result = {"module": None, "ready": False, "error": None, "db_ready": False}
    try:
        _load_secrets_into_env()
        missing = [k for k in ("OPENAI_API_KEY", "DB_URL") if not os.getenv(k)]
        if missing:
            result["error"] = f"secrets/.env 누락: {', '.join(missing)}"
            return result

        if SRC_DIR is None:
            result["error"] = ("src/core/graph.py 를 찾지 못했습니다. "
                               "app 위치 또는 폴더 구조를 확인하세요.")
            return result
        if SRC_DIR not in sys.path:
            sys.path.insert(0, SRC_DIR)     # graph 안의 `import vs_method` 도 여기서 해결

        import graph                         # 모듈 로드 시 app = build_app() 빌드
        result["module"] = graph
        result["ready"] = True

        # DB 스키마 보장 (선택) — 실패해도 앱은 뜨게 하고 경고만
        try:
            import vs_method
            vs_method.ensure_schema(graph.conn())
            result["db_ready"] = True
        except Exception as e:
            result["error"] = f"DB 준비 경고(검색이 안 될 수 있음): {e}"

    except Exception as e:
        result["error"] = f"그래프 로드 실패: {e}"
    return result


# ══════════════════════════════════════════════
# 턴 실행 — graph.run_turn 호출 래퍼
# ══════════════════════════════════════════════
def answer_of(
    gs: dict,
    thread_id: str,
    question: str,
    stage: str,
    doc_paths: list | None,
    market_price: int | None,
) -> str:
    """app.py 의 answer_of 와 동일한 run_turn 호출 시그니처를 유지한다."""
    backend = gs.get("module")
    if backend is None:
        return f"⚠️ 백엔드 미연결로 답변할 수 없습니다. ({gs.get('error')})"
    try:
        return backend.run_turn(
            thread_id, question,
            stage=stage,
            has_document=bool(doc_paths),
            document_paths=doc_paths,       # 여러 파일 경로 리스트
            market_price=market_price,      # 계약 전 유저 입력 시세(원), 없으면 None
        )
    except Exception as e:
        return f"⚠️ 처리 중 오류: {e}"

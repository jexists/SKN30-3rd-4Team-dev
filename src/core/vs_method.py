"""
vs_method.py
전월세 법령 RAG 핵심 모듈 (Supabase + pgvector + OpenAI text-embedding-3-small)

- 청킹: 조항 단위 우선 분할
- 적재: 청크마다 다른 JSONB metadata 동반
- 검색: 코사인 유사도 기준 k개 + metadata 필터
"""

import os
import re

import psycopg
from psycopg.types.json import Json
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1024  # ⚠️ 테이블 VECTOR(N)과 반드시 일치시킬 것

# dimensions=1024 로 차원을 줄여 테이블(VECTOR(1024))과 맞춤
embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIM)


# ──────────────────────────────────────────────
# 연결
# ──────────────────────────────────────────────
def get_conn():
    """
    환경변수 DB_URL 로 Supabase 에 연결.
    SQLAlchemy 형식(postgresql+psycopg://)이 들어와도 raw psycopg 용으로 정리.
    """
    db_url = os.environ["DB_URL"].replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(db_url)


# ──────────────────────────────────────────────
# 스키마 보장 (확장 + 테이블 + 인덱스)
# ──────────────────────────────────────────────
def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS legal_docs (
                id         BIGSERIAL PRIMARY KEY,
                content    TEXT NOT NULL,
                doc_type   TEXT,
                embedding  VECTOR({EMBEDDING_DIM}),
                metadata   JSONB,
                created_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )
        # 벡터 검색용 HNSW (코사인)
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS legal_docs_embedding_idx
            ON legal_docs USING hnsw (embedding vector_cosine_ops);
            """
        )
        # metadata 필터용 GIN
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS legal_docs_metadata_idx
            ON legal_docs USING gin (metadata);
            """
        )
    conn.commit()


def clear_table(conn):
    """테스트 재실행 시 중복 적재를 막기 위해 비움."""
    with conn.cursor() as cur:
        cur.execute("TRUNCATE legal_docs RESTART IDENTITY;")
    conn.commit()


# ──────────────────────────────────────────────
# 청킹 (청크마다 다른 metadata 생성)
# ──────────────────────────────────────────────
def chunk_with_metadata(full_text: str, base_meta: dict) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n제", "\n\n", "\n", ". ", " ", ""],  # '제○조' 경계 우선
    )
    chunks = splitter.split_text(full_text)

    items = []
    for i, chunk in enumerate(chunks):
        article = re.search(r"제\d+조(?:의\d+)?", chunk)
        meta = {
            **base_meta,                                  # 공통 (law_name 등)
            "chunk_index": i,                             # 청크마다 다름
            "article": article.group(0) if article else None,
            "char_len": len(chunk),
        }
        items.append({"content": chunk, "metadata": meta})
    return items


# ──────────────────────────────────────────────
# 적재 (청킹 → 배치 임베딩 → INSERT)
# ──────────────────────────────────────────────
def ingest_document(conn, full_text: str, base_meta: dict, doc_type: str = "law") -> int:
    items = chunk_with_metadata(full_text, base_meta)
    texts = [it["content"] for it in items]
    vectors = embeddings.embed_documents(texts)  # 청크 전체 한 번에 임베딩

    with conn.cursor() as cur:
        for it, vec in zip(items, vectors):
            cur.execute(
                """
                INSERT INTO legal_docs (content, doc_type, embedding, metadata)
                VALUES (%s, %s, %s::vector, %s)
                """,
                (
                    it["content"],
                    doc_type,
                    str(vec),              # pgvector 는 '[...]' 문자열 → ::vector 캐스팅
                    Json(it["metadata"]),  # row 마다 다른 JSONB
                ),
            )
    conn.commit()
    return len(items)


# ──────────────────────────────────────────────
# 검색 (코사인 유사도 + metadata 필터, 기본 k=5)
# ──────────────────────────────────────────────
def search_similar(conn, query: str, k: int = 5, meta_filter: dict = None) -> list[dict]:
    qvec = embeddings.embed_query(query)

    params = [str(qvec)]                 # SELECT 의 거리 계산용 벡터
    where = ""
    if meta_filter:
        clauses = []
        for key, val in meta_filter.items():
            clauses.append("metadata->>%s = %s")
            params.extend([key, str(val)])
        where = "WHERE " + " AND ".join(clauses)

    params.append(str(qvec))             # ORDER BY 용 벡터
    params.append(k)                     # LIMIT

    sql = f"""
        SELECT content, metadata,
               1 - (embedding <=> %s::vector) AS similarity
        FROM legal_docs
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        {"content": r[0], "metadata": r[1], "similarity": round(r[2], 4)}
        for r in rows
    ]
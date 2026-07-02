"""임베딩 결과 Supabase 적재: data/05_vectordb/test → kb_chunks 테이블

embed_chunks.py 가 저장한 [{content, embedding, metadata}] JSON 을 읽어
kb_chunks(content, embedding, metadata) 에 그대로 INSERT 한다 (append — 기존 데이터 유지).
id·created_at 은 DB 기본값(BIGSERIAL, now())으로 채워진다. 임베딩 호출 없음.

실행:
    uv run python src/pipe/ingest_supabase.py
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from psycopg.types.json import Json

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")  # DB_URL + vs_method import 시 OPENAI_API_KEY 필요
sys.path.insert(0, str(ROOT))

from src.core.vs_method import EMBEDDING_DIM, ensure_schema, get_conn  # noqa: E402

VECTOR_DIR = ROOT / "data" / "05_vectordb" / "test"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 한글 깨짐 방지


def ingest_file(conn, path: Path) -> int:
    """임베딩 JSON 하나를 kb_chunks 에 INSERT. 적재 건수 반환."""
    records = json.loads(path.read_text(encoding="utf-8"))
    if not records:
        return 0

    dim = len(records[0]["embedding"])
    if dim != EMBEDDING_DIM:
        raise ValueError(f"{path.name}: 임베딩 차원 {dim} ≠ 테이블 VECTOR({EMBEDDING_DIM})")

    rows = [(r["content"], str(r["embedding"]), Json(r.get("metadata", {}))) for r in records]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO kb_chunks (content, embedding, metadata) VALUES (%s, %s::vector, %s)",
            rows,
        )
    conn.commit()
    return len(rows)


def main() -> None:
    files = sorted(VECTOR_DIR.glob("*.json"))
    if not files:
        print(f"입력 파일 없음: {VECTOR_DIR} — 먼저 embed_chunks.py 를 실행하세요.")
        return

    conn = get_conn()
    try:
        ensure_schema(conn)
        total = 0
        for f in files:
            n = ingest_file(conn, f)
            total += n
            print(f"[OK] {f.name}: {n}건 적재")
        print(f"완료: 총 {total}건 kb_chunks 적재 (append)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

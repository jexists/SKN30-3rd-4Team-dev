"""청크 임베딩 파이프라인: data/04_chunks/test → data/05_vectordb/test

data/04_chunks/test/*.json 의 청킹 결과([{page_content, metadata}])를
vs_method 와 동일한 임베딩(text-embedding-3-small, 1024차원)으로 배치 임베딩하고,
원본과 같은 파일명으로 [{content, embedding, metadata}] JSON 체크포인트를 저장한다.
Supabase 적재는 src/pipe/ingest_supabase.py 가 담당한다 (임베딩/적재 분리).

실행:
    uv run python src/pipe/embed_chunks.py          # 출력 파일이 이미 있으면 스킵 (재임베딩 비용 방지)
    uv run python src/pipe/embed_chunks.py --force  # 전부 다시 임베딩
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")  # vs_method import 시 OpenAIEmbeddings 초기화에 OPENAI_API_KEY 필요
sys.path.insert(0, str(ROOT))

from src.core.vs_method import EMBEDDING_DIM, EMBEDDING_MODEL, embeddings  # noqa: E402

CHUNKS_DIR = ROOT / "data" / "04_chunks" / "final"
VECTOR_DIR = ROOT / "data" / "05_vectordb" / "final"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 한글 깨짐 방지


def embed_file(src_path: Path, out_path: Path) -> int:
    """청크 JSON 하나를 배치 임베딩해 저장. 적재된 청크 수 반환."""
    chunks = json.loads(src_path.read_text(encoding="utf-8"))
    norm = [c for c in chunks if (c.get("page_content") or "").strip()]
    if not norm:
        return 0

    vectors = embeddings.embed_documents([c["page_content"] for c in norm])

    records = [
        {"content": c["page_content"], "embedding": vec, "metadata": c.get("metadata", {})}
        for c, vec in zip(norm, vectors)
    ]
    out_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return len(records)


def main() -> None:
    force = "--force" in sys.argv[1:]
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(CHUNKS_DIR.glob("*.json"))
    if not files:
        print(f"입력 파일 없음: {CHUNKS_DIR}")
        return

    print(f"임베딩 모델: {EMBEDDING_MODEL} ({EMBEDDING_DIM}차원)")
    total = 0
    for f in files:
        out = VECTOR_DIR / f.name
        if out.exists() and not force:
            print(f"[skip] {f.name} (이미 있음 — --force 로 재생성)")
            continue
        n = embed_file(f, out)
        total += n
        print(f"[OK] {f.name}: {n}개 청크 임베딩 → {out.relative_to(ROOT)}")
    print(f"완료: 총 {total}개 청크 임베딩")


if __name__ == "__main__":
    main()

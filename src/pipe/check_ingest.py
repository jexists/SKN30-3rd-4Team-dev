"""적재 상태 점검: data/05_vectordb/final 의 각 파일이 kb_chunks 에 이미 들어갔는지 대조.

ingest_supabase.py 는 파일 단위로 커밋한다(중간에 죽은 파일은 통째로 롤백).
따라서 파일별로 "이미 적재됨 / 안 됨"만 판별하면 재적재 시 중복을 피할 수 있다.

각 파일에서 source_id 를 정규식으로 뽑아(거대한 embedding 은 파싱 안 함) DB 와 대조한다.
  DONE  : 파일의 source_id 가 (거의) 전부 DB 에 있음 → 다시 적재하면 중복
  EMPTY : 하나도 없음 → 아직 안 들어감 (이 파일부터 재개하면 됨)
  PARTIAL: 일부만 (원자적 커밋 상 정상적으론 안 나오지만, 실패 시 참고)

실행:
    uv run python src/pipe/check_ingest.py
"""

import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from src.core.vs_method import get_conn  # noqa: E402

VECTOR_DIR = ROOT / "data" / "05_vectordb" / "final"
SAMPLE = 400  # 파일당 대조할 source_id 표본 수 (앞뒤에서 고르게)

SRC_ID_RE = re.compile(rb'"source_id"\s*:\s*"([^"]+)"')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def sample_source_ids(path: Path, n: int) -> list[str]:
    """파일 앞부분에서 서로 다른 source_id 를 최대 n 개 뽑는다 (embedding 파싱 없이 regex)."""
    ids: dict[str, None] = {}
    if path.suffix == ".jsonl":
        with path.open("rb") as f:
            for line in f:
                m = SRC_ID_RE.search(line)
                if m:
                    ids.setdefault(m.group(1).decode(), None)
                if len(ids) >= n:
                    break
    else:  # .json 배열: 통째로 읽되 regex 로 source_id 만 스캔
        data = path.read_bytes()
        for m in SRC_ID_RE.finditer(data):
            ids.setdefault(m.group(1).decode(), None)
            if len(ids) >= n:
                break
    return list(ids)


def db_present(conn, source_ids: list[str]) -> int:
    if not source_ids:
        return 0
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(DISTINCT metadata->>'source_id') "
            "FROM kb_chunks WHERE metadata->>'source_id' = ANY(%s)",
            (source_ids,),
        )
        return cur.fetchone()[0]


def main() -> None:
    files = sorted(VECTOR_DIR.glob("*.json")) + sorted(VECTOR_DIR.glob("*.jsonl"))
    if not files:
        print(f"입력 파일 없음: {VECTOR_DIR}")
        return

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM kb_chunks")
            print(f"현재 kb_chunks 총 {cur.fetchone()[0]}행\n")

        done, empty = [], []
        for f in files:
            ids = sample_source_ids(f, SAMPLE)
            if not ids:
                print(f"[ SKIP ] {f.name}  (source_id 없음 — 대조 불가)")
                continue
            present = db_present(conn, ids)
            ratio = present / len(ids)
            if ratio >= 0.98:
                tag, bucket = "DONE  ", done
            elif ratio <= 0.5:
                # 원자적 커밋이라 롤백된 파일은 0에 가깝다. 경계에서 걸쳐진
                # source_id 몇 건만 잡혀도 미적재로 보고 재적재 대상에 넣는다.
                tag, bucket = "EMPTY ", empty
            else:
                tag, bucket = "PARTIAL", None  # 예외적 상태 — 수동 확인 필요
            print(f"[{tag}] {f.name}  ({present}/{len(ids)} 표본이 DB 에 존재)")
            if bucket is not None:
                bucket.append(f.name)

        print("\n── 요약 ──")
        print(f"적재됨(DONE) {len(done)}개, 미적재(EMPTY) {len(empty)}개")
        if empty:
            print("\n재개(미적재 파일만 적재):")
            print("  uv run python src/pipe/ingest_supabase.py " + " ".join(empty))
    finally:
        conn.close()


if __name__ == "__main__":
    main()

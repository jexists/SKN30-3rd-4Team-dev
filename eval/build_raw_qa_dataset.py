from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "01_raw"
PROCESSED_PDF_DIRS = [
    ROOT / "data" / "03_processed" / "pdf",
    ROOT / "data" / "03_processed" / "pdf" / "PyPDFloader_X",
    ROOT / "data" / "03_processed" / "pdf" / "PyMuPDF4LLM_X",
    ROOT / "data" / "03_processed" / "PyMuPDFDirectoryLoader",
]
DEFAULT_OUTPUT = ROOT / "data" / "raw_expected_qa.json"


PRE_TOPICS = [
    ("권리관계", "계약 전에 권리관계나 등기상 위험을 어떻게 확인해야 하나요?"),
    ("보증금", "계약 전에 보증금 안전성을 판단할 때 무엇을 확인해야 하나요?"),
    ("대항력", "계약 전에 대항력과 우선변제권을 확보하려면 무엇을 준비해야 하나요?"),
    ("특약", "계약서 특약에는 어떤 내용을 넣거나 확인해야 하나요?"),
    ("중개", "계약 전에 공인중개사나 계약 상대방 확인은 어떻게 해야 하나요?"),
]
POST_TOPICS = [
    ("보증금", "계약 후 보증금을 돌려받지 못하면 어떤 조치를 검토해야 하나요?"),
    ("수선", "계약 후 누수나 하자가 생기면 수선 책임은 어떻게 보나요?"),
    ("갱신", "계약 후 갱신이나 종료 통지는 언제 어떻게 해야 하나요?"),
    ("원상회복", "계약 종료 후 원상회복이나 비용 정산은 어떻게 판단해야 하나요?"),
    ("분쟁", "계약 후 분쟁이 생기면 어떤 절차나 기관을 활용할 수 있나요?"),
]


KEYWORDS = {
    "권리관계": ["등기", "근저당", "압류", "가압류", "가처분", "권리", "소유", "신탁"],
    "보증금": ["보증금", "우선변제", "최우선", "반환", "배당", "임차권등기"],
    "대항력": ["대항력", "전입", "주민등록", "인도", "확정일자", "우선변제"],
    "특약": ["특약", "계약금", "해제", "해지", "담보권", "대출", "보증보험"],
    "중개": ["공인중개", "중개", "설명", "확인", "대리인", "위임장", "신분증"],
    "수선": ["수선", "누수", "하자", "보수", "필요비", "수리", "유지"],
    "갱신": ["갱신", "묵시", "종료", "통지", "6개월", "2개월", "차임"],
    "원상회복": ["원상회복", "관리비", "공과금", "정산", "통상", "파손", "손모"],
    "분쟁": ["분쟁", "조정", "소송", "내용증명", "법원", "상담", "신청"],
}


def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(flatten_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(flatten_text(v) for v in value.values())
    return "" if value is None else str(value)


def split_sentences(text: str) -> list[str]:
    text = clean_text(text)
    marked = re.sub(r"(다\.|요\.|음\.|함\.|됨\.|[.!?。])\s+", r"\1|||", text)
    parts = re.split(r"\|\|\||[-•○ㅇᄋ]\s+", marked)
    out = []
    for part in parts:
        part = clean_text(part)
        if 45 <= len(part) <= 450:
            out.append(part)
    if len(out) < 10:
        out.extend(clean_text(text[i : i + 260]) for i in range(0, min(len(text), 2600), 260))
    return [p for p in out if len(p) >= 35]


def best_sentences(text: str, topic: str, count: int = 5) -> list[str]:
    sentences = split_sentences(text)
    keys = KEYWORDS.get(topic, [])

    def score(sentence: str) -> tuple[int, int]:
        hit_count = sum(1 for key in keys if key in sentence)
        general = sum(
            1
            for key in [
                "임대차",
                "임차인",
                "임대인",
                "계약",
                "주택",
                "상가",
                "법",
                "판례",
                "사례",
            ]
            if key in sentence
        )
        return hit_count * 10 + general, min(len(sentence), 220)

    ranked = sorted(sentences, key=score, reverse=True)
    picked: list[str] = []
    for sentence in ranked:
        if any(sentence[:45] in prev for prev in picked):
            continue
        picked.append(sentence)
        if len(picked) == count:
            break
    while len(picked) < count:
        picked.append("원문에서 직접 확인 가능한 근거가 부족하므로, 관련 조항과 사례를 함께 확인해야 합니다.")
    return picked


def load_json_file(path: Path) -> tuple[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    title = (
        data.get("법령명한글")
        or data.get("법령명_한글")
        or data.get("title")
        or path.stem
    )
    return clean_text(flatten_text(data)), {"title": str(title), "record_count": 1}


def load_jsonl_file(path: Path) -> tuple[str, dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    title = path.stem
    text = " ".join(flatten_text(row) for row in rows)
    return clean_text(text), {"title": title, "record_count": len(rows)}


def load_md_file(path: Path) -> tuple[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    first_heading = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")), path.stem)
    return clean_text(text), {"title": first_heading, "record_count": 1}


def normalized_stem(path: Path) -> str:
    stem = path.stem
    stem = stem.replace("[", "").replace("]", "")
    stem = re.sub(r"[\s_()·\-]+", "", stem)
    return stem


def find_processed_pdf(raw_pdf: Path) -> Path | None:
    raw_norm = normalized_stem(raw_pdf)
    candidates: list[Path] = []
    for base in PROCESSED_PDF_DIRS:
        if not base.exists():
            continue
        candidates.extend(base.glob("*_processed.json"))
    exact = [p for p in candidates if raw_norm in normalized_stem(p) or normalized_stem(p) in raw_norm]
    if exact:
        return sorted(exact, key=lambda p: len(str(p)))[0]
    return None


def load_processed_pdf(path: Path) -> tuple[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    pages = data if isinstance(data, list) else data.get("pages", [])
    texts = []
    for item in pages:
        if isinstance(item, dict):
            texts.append(item.get("page_content") or item.get("text") or flatten_text(item))
    return clean_text(" ".join(texts)), {"processed_source": str(path.relative_to(ROOT)), "record_count": len(texts)}


def load_pdf_file(path: Path) -> tuple[str, dict[str, Any]]:
    processed = find_processed_pdf(path)
    if processed:
        text, meta = load_processed_pdf(processed)
        meta["title"] = path.stem
        return text, meta

    try:
        import fitz  # type: ignore
    except Exception:
        return "", {"title": path.stem, "record_count": 0, "error": "no processed text and pymupdf unavailable"}

    doc = fitz.open(path)
    text = " ".join(page.get_text() for page in doc)
    return clean_text(text), {"title": path.stem, "record_count": doc.page_count}


def load_source(path: Path) -> tuple[str, dict[str, Any]]:
    if path.suffix == ".json":
        return load_json_file(path)
    if path.suffix == ".jsonl":
        return load_jsonl_file(path)
    if path.suffix == ".md":
        return load_md_file(path)
    if path.suffix == ".pdf":
        return load_pdf_file(path)
    return "", {"title": path.stem, "record_count": 0, "error": f"unsupported suffix {path.suffix}"}


def make_keywords(answer: str, topic: str) -> list[str]:
    tokens = [key for key in KEYWORDS.get(topic, []) if key in answer]
    nouns = re.findall(r"[가-힣A-Za-z0-9]{2,}", answer)
    for noun in nouns:
        if noun not in tokens and len(tokens) < 8:
            tokens.append(noun)
    return tokens[:8]


def build_item(source_path: Path, source_meta: dict[str, Any], stage: str, topic: str, idx: int, answer: str) -> dict[str, Any]:
    template = dict(PRE_TOPICS if stage == "pre" else POST_TOPICS)[topic]
    title = source_meta.get("title") or source_path.stem
    question = f"{template} ({title} 근거 기준)"
    return {
        "id": f"{source_path.parent.name}_{source_path.stem}_{stage}_{idx:02d}",
        "source_file": str(source_path.relative_to(ROOT)),
        "source_title": title,
        "stage": stage,
        "topic": topic,
        "question": question,
        "expected_answer": answer,
        "expected_keywords": make_keywords(answer, topic),
        "source_meta": source_meta,
    }


def build_dataset(raw_dir: Path) -> dict[str, Any]:
    items = []
    source_summaries = []
    files = sorted(p for p in raw_dir.rglob("*") if p.is_file())
    for path in files:
        text, meta = load_source(path)
        rel = str(path.relative_to(ROOT))
        meta = {"title": meta.get("title") or path.stem, **meta}
        source_summaries.append({"source_file": rel, "text_chars": len(text), **meta})

        for idx, (topic, _) in enumerate(PRE_TOPICS, start=1):
            answer = best_sentences(text, topic, count=1)[0]
            items.append(build_item(path, meta, "pre", topic, idx, answer))
        for idx, (topic, _) in enumerate(POST_TOPICS, start=1):
            answer = best_sentences(text, topic, count=1)[0]
            items.append(build_item(path, meta, "post", topic, idx, answer))

    return {
        "version": 1,
        "description": "data/01_raw 원천 파일별 계약 전 5개, 계약 후 5개 예상 질문/답변 평가셋",
        "source_root": str(raw_dir.relative_to(ROOT)),
        "source_file_count": len(source_summaries),
        "item_count": len(items),
        "generation_method": "deterministic keyword sentence extraction from raw/processed source text",
        "items": items,
        "sources": source_summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    dataset = build_dataset(args.raw_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {dataset['item_count']} QA items from {dataset['source_file_count']} files to {args.output}")


if __name__ == "__main__":
    main()

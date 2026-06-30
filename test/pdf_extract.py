"""
pdf_extract.py
--------------
PDF에서 텍스트를 '하이브리드'로 긁어오는 범용 함수.

전략 (페이지 단위 분기):
  1) 텍스트 레이어가 충분하면        -> 그대로 추출 (빠르고 정확)
  2) 텍스트가 부족하면(스캔/이미지) -> 해당 페이지만 렌더링 후 OCR 폴백
  3) OCR도 못 잡는 그래픽 글자(벡터 외곽선 제목 등) -> manual_overrides로 수동 보정
  4) 그래도 비면                     -> [빈 페이지]로 표기

의존성:
  pip install pymupdf pytesseract pillow
  # 한국어 OCR: apt-get install tesseract-ocr-kor  (lang="kor+eng")

OCR이 필요 없으면 pytesseract/PIL 없이도 동작함(텍스트 레이어만 사용).
"""

from __future__ import annotations
from dataclasses import dataclass, field
import io
import os
from dotenv import load_dotenv

load_dotenv()  # .env에서 OPENAI_API_KEY, DB_URL 등 환경변수 로드

import pymupdf  # fitz


@dataclass
class Page:
    number: int                 # 1-based 페이지 번호
    text: str                   # 최종 추출 텍스트
    source: str                 # "text" | "ocr" | "override" | "blank"


@dataclass
class ExtractResult:
    pages: list[Page] = field(default_factory=list)

    @property
    def stats(self) -> dict[str, int]:
        s: dict[str, int] = {}
        for p in self.pages:
            s[p.source] = s.get(p.source, 0) + 1
        return s

    def to_text(self, marker: bool = True) -> str:
        out = []
        for p in self.pages:
            if marker:
                out.append(f"\n===== p.{p.number} =====")
            out.append(p.text)
        return "\n".join(out).lstrip()

    def to_markdown(self, title: str | None = None) -> str:
        out = [f"# {title}\n"] if title else []
        for p in self.pages:
            out.append(f"\n\n---\n\n## p.{p.number}\n\n{p.text}")
        return "".join(out).lstrip()


def _ocr_page(page: "pymupdf.Page", lang: str, dpi: int) -> str:
    """페이지를 렌더링해서 OCR. pytesseract/PIL이 없으면 빈 문자열."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img, lang=lang).strip()


def extract_pdf(
    path: str,
    *,
    ocr: bool = True,
    ocr_lang: str = "kor+eng",
    ocr_dpi: int = 350,
    low_text_threshold: int = 30,
    manual_overrides: dict[int, str] | None = None,
) -> ExtractResult:
    """
    PDF 전체를 하이브리드로 추출.

    Args:
        path: PDF 경로
        ocr: 저텍스트 페이지에 OCR 폴백을 돌릴지 여부
        ocr_lang: tesseract 언어 (한국어는 "kor" 또는 "kor+eng")
        ocr_dpi: OCR용 렌더링 해상도. 한글은 300~400 권장
        low_text_threshold: 이 글자 수 미만이면 '텍스트 부족'으로 간주
        manual_overrides: {페이지번호: 텍스트} — OCR도 못 잡는 그래픽 글자 수동 지정.
                          지정된 페이지는 텍스트/OCR을 건너뛰고 이 값을 사용.

    Returns:
        ExtractResult (페이지 리스트 + stats / to_text / to_markdown)
    """
    overrides = manual_overrides or {}
    result = ExtractResult()

    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc):
            pn = i + 1

            # 0) 수동 보정 우선
            if pn in overrides:
                result.pages.append(Page(pn, overrides[pn].strip(), "override"))
                continue

            # 1) 텍스트 레이어
            body = page.get_text("text").strip()
            if len(body) >= low_text_threshold:
                result.pages.append(Page(pn, body, "text"))
                continue

            # 2) OCR 폴백
            if ocr:
                ocr_text = _ocr_page(page, ocr_lang, ocr_dpi)
                if len(ocr_text) >= low_text_threshold:
                    result.pages.append(Page(pn, ocr_text, "ocr"))
                    continue

            # 3) 그래도 비면 빈 페이지
            result.pages.append(Page(pn, "[빈 페이지]", "blank"))

    return result


def find_low_text_pages(path: str, threshold: int = 30) -> list[int]:
    """OCR/보정 대상 후보(텍스트 레이어가 부족한 페이지)만 빠르게 진단."""
    low = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc):
            if len(page.get_text("text").strip()) < threshold:
                low.append(i + 1)
    return low


if __name__ == "__main__":
    from pathlib import Path

    # 이 파일: src/adapter/pdf_extract.py  ->  parents[2] = 프로젝트 루트
    HERE = Path(__file__).resolve().parent          # pdf_extract.py가 있는 폴더
    SRC = HERE / "test.pdf"

    if not SRC.exists():
        raise FileNotFoundError(f"PDF 없음: {SRC}")

    # 1단계: 어느 페이지가 OCR/보정 대상인지 먼저 진단
    print("저텍스트 페이지:", find_low_text_pages(SRC))

    # 2단계: 그중 OCR도 못 잡는 그래픽 제목(장 구분면)만 수동 지정
    DIVIDERS = {
        6:   "Ⅰ. 제도 개요",
        10:  "Ⅱ. 설치 현황",
        14:  "Ⅲ. 조정 관련 FAQ",
        22:  "Ⅳ. 주택 임대차분쟁조정사례",
        118: "Ⅴ. 상가건물 임대차분쟁조정사례",
        154: "Ⅵ. 최신 판례",
    }

    # 3단계: 추출
    res = extract_pdf(SRC, ocr_lang="kor+eng", manual_overrides=DIVIDERS)
    print("stats:", res.stats)

    with open("사례집_전체텍스트.md", "w", encoding="utf-8") as f:
        f.write(res.to_markdown(title="2021 주택·상가건물 임대차분쟁 조정사례집"))
    with open("사례집_전체텍스트.txt", "w", encoding="utf-8") as f:
        f.write(res.to_text())

import os
import io
import base64
import fitz  # PyMuPDF
from PIL import Image
from openai import OpenAI

client = OpenAI()

# OCR 프롬프트: 요약·해석 금지, 보이는 그대로 전사하도록 강제
_OCR_PROMPT = (
    "이 이미지에 있는 모든 텍스트를 빠짐없이 그대로 전사(transcribe)해줘. "
    "요약하거나 의역하지 말고, 줄바꿈과 표 구조는 최대한 보존해. "
    "표는 마크다운 표로 표현하고, 텍스트가 없으면 빈 문자열만 반환해. "
    "설명·머리말 없이 추출된 텍스트만 출력해."
)


def extract_document(path, model="gpt-4o", dpi=200, text_threshold=15):
    """
    파일 종류(텍스트 PDF / 이미지 PDF / 이미지 파일)를 자동 감지해
    텍스트는 직접 추출, 스캔·이미지는 OpenAI 비전 API로 OCR한다.

    Args:
        path (str): PDF 또는 이미지(jpg/jpeg/png 등) 경로
        model (str): OpenAI 비전 모델. 기본 gpt-4o, 정밀도 필요시 gpt-5.4 등
        dpi (int): 이미지 페이지 렌더링 해상도 (높을수록 정확·고비용)
        text_threshold (int): 추출 글자 수가 이 값 미만이면 OCR로 전환

    Returns:
        dict: {"type", "pages": {no: {"text", "method"}}, "text"}
    """
    ext = os.path.splitext(path)[1].lower()
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}

    # --- 분기 1: 이미지 파일이면 바로 비전 OCR ---
    if ext in image_exts:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        text = _ocr_image_api(b64, mime, model)
        return {
            "type": "image",
            "pages": {1: {"text": text, "method": "ocr"}},
            "text": text,
        }

    # --- 분기 2: PDF는 페이지별로 텍스트/OCR 판단 ---
    if ext == ".pdf":
        return _extract_pdf(path, model, dpi, text_threshold)

    raise ValueError(f"지원하지 않는 파일 형식입니다: {ext}")


def _extract_pdf(path, model, dpi, text_threshold):
    doc = fitz.open(path)
    pages = {}

    for page_no, page in enumerate(doc, start=1):
        # 1) 텍스트 레이어 우선 시도 (무료·빠름)
        text = page.get_text("text").strip()

        if len(text) >= text_threshold:
            pages[page_no] = {"text": text, "method": "text"}
        else:
            # 2) 글자 거의 없음 → 스캔/이미지 페이지로 보고 비전 OCR
            pix = page.get_pixmap(dpi=dpi)
            b64 = base64.b64encode(pix.tobytes("png")).decode()
            ocr_text = _ocr_image_api(b64, "image/png", model)
            pages[page_no] = {"text": ocr_text, "method": "ocr"}
            pix = None  # 메모리 즉시 해제

    doc.close()

    full_text = "\n\n".join(
        f"--- Page {no} ({p['method']}) ---\n{p['text']}"
        for no, p in pages.items()
    )
    return {"type": "pdf", "pages": pages, "text": full_text}


def _ocr_image_api(b64_image, mime_type, model):
    """base64 이미지를 OpenAI 비전 모델에 보내 텍스트를 전사한다."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _OCR_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{b64_image}",
                                "detail": "high",  # 작은 글씨 인식률 ↑
                            },
                        },
                    ],
                }
            ],
            max_tokens=4096,
            temperature=0,  # 전사는 창의성 불필요
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[OCR 실패: {e}]"
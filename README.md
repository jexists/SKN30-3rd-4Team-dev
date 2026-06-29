# 전·월세 분쟁 팩트체커

> 계약 전 예방부터 계약 후 갈등까지, 법으로 따져주는 자취생 도우미

세입자(사회초년생)를 위한 챗봇 서비스입니다.
**계약 전** 등기부·특약을 분석해 전세사기 위험을 짚어주고, **계약 후**엔 이사 팁·수리 분쟁·보증금 갈등을 도와줍니다.

## 주요 기능
- 🛡️ **계약 전 챗봇** — 등기부·특약 분석, 전세사기 위험 진단
- 🤝 **계약 후 챗봇** — 이사 팁, 수리 분쟁, 보증금 갈등 대응
- 📄 **PDF 업로드** — 계약서·등기부 문서 분석
- 🖼️ **이미지 정보 읽기(OCR)** — 사진 속 문서 내용 추출

## 기술 스택
Streamlit · LangChain / LangGraph · OpenAI · LangSmith · uv (Mac/Windows 공용)

## 폴더 구조
| 폴더 | 역할 |
|------|------|
| `data/raw/` | 원본 문서 (표준계약서·등기부·법령) |
| `data/processed/` | 로딩·전처리 결과 |
| `data/chunks/` | 청킹 결과 체크포인트 |
| `data/vectordb/` | Chroma 벡터스토어 (재임베딩 비용 절약 위해 커밋) |
| `src/` | 핵심 로직 (문서 로드·청킹·임베딩·검색·프롬프트·에이전트) |
| `app/` | Streamlit 챗봇 UI |
| `eval/` | 평가·검증 |
| `docs/` | 기획서·설계 문서 |

## 시작하기 (Mac / Windows 공통)
```bash
# 1. 의존성 설치 (uv가 .venv와 lock 기반으로 동일 환경 구성)
uv sync

# 2. 환경 변수 설정 — 예시 파일을 복사해 본인 키 입력
cp .env.example .env      # Windows(PowerShell): copy .env.example .env

# 3. 앱 실행 (코드 추가 후)
uv run streamlit run app/main.py
```
> `uv`가 없다면 먼저 설치하세요 → https://docs.astral.sh/uv/

## 협업 워크플로우
- 작업 브랜치 → **`develop`으로 PR** → CodeRabbit 자동 리뷰 → 머지
- `develop` → **`main` 머지** 시 org 저장소로 자동 미러 + Discord 알림
- 커밋 메시지: `<type>: <한글 설명>` (예: `feat: 등기부 분석 기능 추가`)

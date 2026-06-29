# Git 컨벤션 & AI 워크플로우

## 0. 사전 준비 — GitHub CLI (`gh`) 설치

PR 생성에 `gh`가 필요하다. 아래 중 해당하는 OS로 설치한 뒤 로그인한다.

**Mac**
```bash
brew install gh
```

**Windows**
```powershell
winget install --id GitHub.cli
```

**로그인 (공통)**
```bash
gh auth login
# GitHub.com → HTTPS → Login with a web browser 선택
```

설치 확인:
```bash
gh --version
```

---

## 1. 브랜치 전략

작업은 항상 기능 브랜치에서 시작한다. 완료되면 `develop`에 PR을 올리고, CodeRabbit 자동 리뷰를 거쳐 팀원이 머지한다. `main`은 `develop` 머지 시 자동으로 동기화되므로 직접 PR하지 않는다.

브랜치명은 `<prefix>/<영문-kebab-case>` 형태로 짓는다:

| prefix | 언제 |
|--------|------|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 동작 변경 없는 코드 개선 |
| `chore` | 빌드·설정·의존성 |
| `docs` | 문서 |
| `test` | 테스트 |

예: `feat/contract-deviation-detector`, `fix/chroma-embedding-retry`

---

## 2. 커밋 메시지 형식

```
<type>: <한글 설명>
```

`type`은 브랜치 prefix와 동일 (`feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `style`, `perf`).  
설명은 한글로, Co-Authored-By 태그는 절대 붙이지 않는다.

예:
```
feat: 등기부 특약 이탈 탐지 추가
fix: Chroma 임베딩 재시도 오류 수정
docs: 데이터 파이프라인 명세 업데이트
```

---

## 3. AI 워크플로우

### Claude Code 사용 시

Claude Code CLI에서 슬래시 커맨드로 실행한다.

| 상황 | 커맨드 |
|------|-------|
| 새 작업 시작 | `/start <작업 설명>` |
| 커밋 | `/commit` |
| PR 생성 | `/pr` |

- `/start` — 모호도 게이트를 통과하면 `develop` 기준 새 브랜치를 자동 생성한다.
- `/commit` — `main`/`develop`에서 실행하면 브랜치 생성부터 커밋·push까지 한 번에 처리한다.
- `/pr` — 커밋 내역을 분석해 PR 본문을 작성하고 `gh pr create`로 게시한다.

---

### Gemini 사용 시

아래 프롬프트를 복사해 `[대괄호]` 부분만 바꿔서 붙여넣는다.

#### 브랜치 시작

```
[작업 내용]을 구현하려 한다.
아래 순서로 진행해라.

1. git fetch origin develop
2. git checkout origin/develop -b <prefix>/<브랜치명>
   - 브랜치명: 작업 내용을 영문 kebab-case로 요약
   - prefix: feat / fix / refactor / chore / docs / test 중 선택
3. 브랜치 생성 후 브랜치명과 기준 커밋을 보고해라.
```

#### 커밋

```
변경된 파일을 확인하고 커밋해라.
아래 규칙을 반드시 지켜라.

- git status, git diff로 변경 파악
- 스테이징 금지 목록: .env, .venv/, __pycache__/, *.pyc, .ruff_cache/, .pytest_cache/, data/05_vectordb/
- 커밋 메시지 형식: <type>: <한글 설명>
  type = feat | fix | refactor | chore | docs | test | style | perf
- Co-Authored-By 태그 절대 금지
- 커밋 완료 후 git fetch → git rebase origin/<현재브랜치> → git push 순서로 수행
- 충돌 발생 시 자동 해결 금지, 즉시 멈추고 보고
```

#### PR 생성

```
현재 브랜치의 변경사항으로 GitHub PR을 생성해라.
아래 규칙을 반드시 지켜라.

- 미커밋 변경이 있으면 먼저 알리고 중단 (커밋 먼저 안내)
- PR 제목: <type>: <한글 설명> (70자 이내)
- PR 본문 형식:
    📌 배경
    <변경이 필요한 이유>

    ✅ 수정 내역
    1. ...
- gh pr create --base develop 으로 생성, body는 HEREDOC으로 전달
- PR 생성 후 git checkout develop && git pull origin develop
- PR URL 보고 후 "머지는 GitHub 웹에서 직접 해주세요" 안내
- gh pr merge 절대 금지
```

---

## 4. PR 본문 형식

```
📌 배경
<이 작업이 필요한 이유, 해결하려는 문제>

✅ 수정 내역
1. ...
2. ...
```

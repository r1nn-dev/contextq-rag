# docs/ui — UI 목업 및 화면 스크린샷

> 실제 프론트엔드 구현체가 아닌 **설계 의도를 시각화한 목업**이다.

---

## 디렉토리 구조

```
docs/ui/
├── README.md               ← 이 파일
├── landing.html            ← 랜딩 페이지 (서비스 소개 + 로그인 진입)
├── app.html                ← 앱 와이어프레임 (인터랙티브, JS 상태 기반)
└── screenshots/            ← 전체 화면 상태 정적 캡처 (17장)
    ├── 01-home-hero.png
    ├── 02-home-features.png
    ├── ...
    └── 17-admin-users.png
```

---

## landing.html — 랜딩 페이지

**역할**: 서비스의 첫 화면. 소개 섹션 + 로그인·회원가입 CTA.

**포함 섹션**

| 섹션 | 내용 |
|---|---|
| Hero | 서비스 한 줄 설명, 주요 메시지, 시작 버튼 |
| 기능 소개 | SINGLE 모드 / COMPARE 모드 / 출처 기반 답변 3가지 핵심 기능 카드 |
| 로그인 / 회원가입 CTA | 계정 없이도 게스트로 체험 가능함을 안내 |

**열기**

```bash
# 브라우저에서 직접 열기
open docs/ui/landing.html          # macOS
xdg-open docs/ui/landing.html     # Linux
```

**스크린샷 대응**

| 화면 | 파일 |
|---|---|
| 히어로 섹션 | `screenshots/01-home-hero.png` |
| 기능 소개 섹션 | `screenshots/02-home-features.png` |

---

## app.html — 앱 와이어프레임

**역할**: 로그인 이후 전체 사용자 흐름을 인터랙티브하게 탐색하는 와이어프레임.

**작동 방식**: JS 상태(state) 기반 화면 전환. 버튼 클릭 → 상태 변경 → 해당 뷰 렌더링.

> **주의**: 한 번에 하나의 화면만 렌더링되므로 브라우저에서 열었을 때 모든 화면이 동시에 보이지 않는다.  
> 전체 화면 목록은 아래 `screenshots/` 섹션을 참고.

**탐색 가능한 주요 흐름**

| 흐름 | 진입 방법 |
|---|---|
| 게스트 질문 | 초기 화면에서 질문 입력 |
| 회원가입 / 로그인 | 헤더 버튼 클릭 |
| 새 대화 시작 | 로그인 후 사이드바 "새 대화" |
| SSE 스트리밍 답변 | 질문 제출 후 로딩 → 완료 순서로 전환 |
| COMPARE 모드 | 모드 선택 후 두 버전 선택 |
| 대화 이력 | 사이드바 이력 항목 클릭 |
| 관리자 패널 | admin 계정 로그인 후 접근 |

**열기**

```bash
open docs/ui/app.html
```

---

## screenshots/ — 전체 화면 상태 캡처

**역할**: app.html이 JS 상태 기반이라 단독으로 문서 역할이 불충분한 한계를 보완.  
보고서·발표 슬라이드에 직접 삽입할 수 있도록 각 화면을 정적 이미지로 고정.

**파일명 규칙**: `{번호}-{화면-이름}.png` — 번호 prefix로 순서 보장, 슬라이드 삽입 시 파일 탐색 편의.

### 화면 목록

| 번호 | 파일명 | 화면 설명 | 비고 |
|---|---|---|---|
| 01 | `01-home-hero.png` | 홈 히어로 | landing.html 대응 |
| 02 | `02-home-features.png` | 홈 기능 소개 | landing.html 대응 |
| 03 | `03-chat-guest.png` | 게스트 질문 화면 | 로그인 없이 체험 |
| 04 | `04-auth-register.png` | 회원가입 | 이메일·비밀번호 입력 |
| 05 | `05-auth-login.png` | 로그인 | — |
| 06 | `06-chat-new.png` | 새 대화 시작 | 로그인 후 초기 상태 |
| 07 | `07-chat-typing.png` | 질문 입력 중 | 텍스트 입력 상태 |
| 08 | `08-chat-sse-meta.png` | 답변 로딩 | SSE `meta` 이벤트 수신 직후 |
| 09 | `09-chat-done.png` | 답변 완료 | SSE `done` 이벤트, 출처 카드 포함 |
| 10 | `10-chat-no-context.png` | NO_CONTEXT | 문서에 없는 내용 질문 시 |
| 11 | `11-modal-session-limit.png` | 세션 초과 모달 | 게스트 5회 초과 (`GUEST_QUOTA_EXCEEDED`) |
| 12 | `12-compare-input.png` | 비교 모드 입력 | 버전 A / B 선택 UI |
| 13 | `13-compare-done.png` | 비교 모드 결과 | v0.3 ↔ v1.x 나란히 표시 |
| 14 | `14-history-list.png` | 대화 이력 목록 | 사이드바 이력 패널 |
| 15 | `15-history-detail.png` | 대화 이력 상세 | 과거 대화 재열람 |
| 16 | `16-admin-index.png` | 관리자 인덱스 현황 | `source_key`별 ACTIVE 상태 확인 |
| 17 | `17-admin-users.png` | 관리자 사용자 관리 | 가입 계정 조회·제한 설정 |

---

## 화면 업데이트 방법

UI가 변경되면 해당 번호 파일만 교체 커밋.

```bash
# 예시: 09번 화면 교체
cp new-screenshot.png docs/ui/screenshots/09-chat-done.png
git add docs/ui/screenshots/09-chat-done.png
git commit -m "docs(ui): 09-chat-done 화면 업데이트"
```

HTML 목업 변경 시:

```bash
git add docs/ui/landing.html docs/ui/app.html
git commit -m "docs(ui): 목업 HTML 업데이트 — <변경 내용 한 줄>"
```

---

end.
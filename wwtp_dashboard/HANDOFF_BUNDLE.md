# 폐수처리 공정 품질 관제 대시보드 — 인수인계 문서

> 이 문서는 **사내 Claude(또는 담당자)가 맥락 없이 읽고 이어서 작업**할 수 있도록 쓴 문서입니다.
> 코드(`app.py`, `core.py`, `charts.py`, `views.py`)는 **데모 데이터로 이미 동작하는 완성형 프로토타입**입니다.
> 해야 할 일은 크게 두 가지입니다: ① **데이터 소스를 회사 서버로 교체**, ② **회사 실제 설비/규격에 맞게 설정값 수정**.
> 화면 구조와 감지 로직은 아래 "설계 결정" 이유가 있어서 이렇게 만들어졌으니, 이유 없이 바꾸지 마세요.

---

## 1. 목적

폐수처리 공정의 **모든 센서 데이터에서 미세한 변동까지 조기 감지**하는 관제 대시보드.
- 단순히 규격(LSL/USL)을 벗어난 것뿐 아니라, **규격 안에서 이미 평소와 달라지고 있는 것**을 일찍 잡는 게 핵심.
- 센서가 수백 개라서 **한 개씩 클릭해서 보는 방식은 불가능**. "눈으로 훑어서 튀는 걸 찾는" 구조여야 함.

## 2. 설비 구조 (사용자가 알려준 내용)

- 건물 3개 (1동, 2동, 3동)
- 건물마다 공정 4개: **유기, 무기1, 무기2, 산폐수**
- 공정마다 **계열 4개** (A~D계열)
- **유기 계열** (흐름 순서): 전탈조 → 폭기조1~5 → 후탈조 → 재폭기조 → 침전조
  - 폭기조, 재폭기조: **DO, pH**
  - 전탈조, 후탈조: **NO3-N, 외부탄소원 투입유량**
  - 침전조: **SS, torque**
  - → 계열당 센서 18개
- **무기1 / 무기2 / 산폐수 계열** (반응조 3개는 직렬 1→2→3): 반응조1~3 → 응집조 → 침전조
  - 반응조: **pH, 소석회 투입유량, 응결제 투입유량**
  - 응집조: **고분자 투입유량**
  - 침전조: **F, SS**
  - → 계열당 센서 12개
- 전체: 유기 3×4×18 = 216, 무기류 3공정×3동×4계열×12 = 432 → **648개** (전/후탈조·재폭기조·침전조는 계열당 1개씩이라고 확인함)
- 사용자가 "공정이 훨씬 더 많다"고 했으므로 **구조는 반드시 설정(config) 기반**이어야 함 (`core.py`의 `PROCESSES`, `tanks_of()`, `STAGE_SPEC`).
- **데이터**: 서버에서 **5분 평균값이 5분마다 누적**됨. 실시간 갱신 필요.

## 3. 파일 구성

| 파일 | 역할 |
|---|---|
| `app.py` | 진입점. 상단 내비(탭), 헤더 바, 조회 구간 슬라이더, 전역 CSS(다크 관제 테마) |
| `core.py` | **설비 구조, 규격, 데이터 생성/로딩, 이상 감지, 사고 묶기.** 데이터 교체는 여기서만 |
| `charts.py` | Plotly 센서 차트 (규격선, 근접/이탈 영역, 이상 구간 음영, 동료 범위) |
| `views.py` | 화면 4개 |
| `.streamlit/config.toml` | 다크 테마 |
| `requirements.txt` | streamlit, plotly, pandas, numpy |

핵심 객체는 `core.Plant` (`core.get_plant()`가 만들어 `st.cache_resource`로 캐시):
- `meta` : 센서별 1행 DataFrame. 컬럼 `bldg, proc, line, tank, stage, param, unit, lsl, usl, base, sigma, std_limit, dec, G`
  (`G` = 동료 그룹 id = 같은 건물·공정·조종류·항목)
- `idx` : 시간축 `DatetimeIndex` (5분 간격)
- `V` : 값 배열 `(센서 수 × 시간)` ← **실데이터로 채워야 하는 유일한 핵심 배열**
- `F` : 감지 플래그 `{"SPEC","NEAR","HOLD","STD","PEER"}` 각 `(센서×시간) bool`
- `std` : 1시간 이동표준편차, `med` : 동료 그룹 중앙값

## 4. 해야 할 일 (순서대로)

### 4-1. 데모로 먼저 실행해서 확인
```
pip install -r requirements.txt     # 사내망이면 사내 PyPI/휠 사용
streamlit run app.py
```
탭 4개(종합 현황 / 공정 상세 / 한눈에 비교 / 경고 센터)가 에러 없이 떠야 함.

### 4-2. 데이터 소스 교체 — `core.get_plant()`
- 함수 안의 `# ── 데모 데이터 생성 ... ──` 블록(난수 생성 + `ANOMALIES` 주입)만 **서버 조회로 교체**. 그 아래 감지 로직과 화면은 그대로 둠.
- 필요한 것: **센서 태그 ↔ (건물, 공정, 계열, 조, 항목) 매핑표**, DB/API 접속 방법, 시간 구간 조회.
- **DB 종류, 접속 정보, 태그 명명 규칙은 모르는 상태이므로 사용자에게 질문해서 확인할 것. 추측해서 쓰지 말 것.**
- 만들어야 하는 결과: `meta`(센서 목록·규격), `idx`, `V`. 센서 순서는 `meta` 행 순서와 `V` 행 순서가 일치해야 함.
- `ANOMALIES`(데모용 가짜 이상 주입)와 `DEMO` 관련 코드는 실데이터 모드에서 사용하지 않음. **데모 모드는 삭제하지 말고 남겨둘 것**(환경변수 등으로 전환) — 테스트용.

### 4-3. 규격값을 실제 값으로 — `core.STAGE_SPEC`
현재 값은 **전부 내가 임의로 정한 placeholder**임 (예: 폭기조 DO 1.0~4.0, pH 6.5~8.5 등). 실제 관리 규격(LSL/USL)과 `std_limit`(이동표준편차 경고 기준)으로 반드시 교체.
- 하한이 없는 항목은 `NAN`.
- 라인/동마다 규격이 다르면 `STAGE_SPEC` 키를 확장해야 함 (현재는 조 종류+항목 단위).
- `base`, `sigma`, `dec`는 **데모 데이터 생성용**이라 실데이터 모드에서는 무의미. (`dec` = 소수 자리, 표시/반올림용)

### 4-4. 실데이터에서 반드시 챙겨야 할 것 (데모엔 없던 문제)
- **결측(NaN)**: 센서 통신 두절. 현재 코드는 NaN 없음을 가정. `np.median`→`np.nanmedian`, Hold 판정에서 NaN 제외, 결측 구간은 플래그 False 처리 등 필요.
- **점검/교정 중 센서**: 알람 억제(마스킹) 기능 필요.
- **이상치(스파이크)**: 5분 평균이라도 튀는 값 가능. 필요하면 전처리.
- **공정 부하 변화**: 현재 PEER 기준선은 "앞 2일"로 고정. 실제로는 기준선을 **롤링(예: 최근 N일)** 으로 갱신할 것.
- **시계 갱신**: `st.cache_resource`는 한 번 만들고 끝. 5분마다 신규 데이터를 반영하려면 `st.fragment(run_every=...)` 또는 TTL 캐시 + **증분 조회**.
- **규모**: 센서 약 650개 × 5분 간격 × 30일 ≈ 560만 포인트로 메모리에 올릴 만하지만, **원본(초 단위 등)을 통째로 올리지 말고 서버/DB에서 5분 집계 후 가져올 것**. 센서가 수천 개로 늘면 감지(플래그)도 DB/배치로 옮기는 것을 검토.
- **보안**: 이 앱은 사내 데이터를 다룸. 외부 전송 코드 없음을 유지할 것(아래 6번 참고).

## 5. 이상 감지 규칙 (5분 간격 기준) — `core.py`

| 종류 | 정의 | 상수 |
|---|---|---|
| **SPEC 스펙 이탈** | 값 > USL 또는 < LSL | |
| **NEAR 근접** | 규격 안이지만 상/하한에서 규격폭의 10% 이내 | `NEAR_RATIO=0.10` |
| **HOLD** | 같은 값이 1시간(12샘플) 이상 연속 (센서 고착/통신 정지 의심) | `HOLD_N=12` |
| **STD σ 초과** | 1시간 이동표준편차 > 항목별 `std_limit` | `STD_N=12` |
| **PEER 동료 대비 이탈 (조기경보)** | 아래 참고 | `PEER_ALPHA=0.2, PEER_K=5.0, PEER_PERSIST=6` |

### PEER (가장 중요 — 조기감지의 핵심)
같은 **건물·공정·조 종류·항목**의 센서들(예: 한 공정의 폭기조 20개의 DO)은 서로 비슷하게 움직여야 함. 한 센서가 **동료 중앙값에서 벌어지면** 규격 안이어도 이상으로 본다.
1. `d = 센서값 − 동료그룹 중앙값` (시간별)
2. `d`에서 **센서별 평소 평균(오프셋)을 뺀다** ← 빼먹으면 오탐 폭증
3. 평소 편차폭 `σ_d` = **MAD 기반 robust σ** (전체 기간, 이상치에 강함)
4. `d`의 **EWMA(α=0.2)** 가 `±5σ_d` 를 넘고, **6샘플(30분) 연속**이면 플래그 (구간 전체를 역채움)

튜닝 이력(데모, 센서 648개 기준): 오프셋 미제거 + 앞2일 표준편차 + 4σ → 하루 10건 이상 오탐 → 오프셋 제거 + MAD + 5σ → **하루 1건 수준**. 민감도를 올리고 싶으면 `PEER_K`를 낮추되 오탐을 반드시 같이 확인할 것.

### 사고(incident) 묶기
같은 **(건물, 공정, 계열, 조 종류)** 안의 경고는 **사고 1건**으로 묶는다. 예) 한 계열 폭기조 3개가 동시에 DO 저하 → 알람 3건이 아니라 사고 1건. (알람 피로 방지) — `core.incidents()`

## 6. 화면 구성과 설계 결정 (이유)

사용자가 직접 불만을 말해서 바뀐 부분이 많음. **되돌리지 말 것.**

1. **종합 현황** — 센서 전체 요약
   - KPI(정상/전체, 종류별 개수), **"지금 확인할 곳"**(진행 중 사고 순위, 줄을 누르면 그래프가 펼쳐짐, "모두 펼치기" 토글), **공정 카드 12개**(동3×공정4, 계열 A~D 칩 색 + "이상 센서 n/전체" + 조기경보 수, "상세 ›" 버튼으로 공정 상세로 이동)
   - ❌ *히트맵은 사용자가 "뭘 봐야 하는지 모르겠다"고 해서 제거함.* 색만 있고 값·규격·여유가 안 보였기 때문. 센서 650개에서 계층 요약(카드)으로 대체.
2. **공정 상세** — 계열 4개를 **공정 흐름 순서의 조 박스**로 나열(박스 = 버튼, 상태 아이콘/현재값). **이상 있는 조는 자동 펼침**, 박스를 누르면 해당 계열 바로 아래에 센서 그래프 펼침/접힘. "이상 조 모두 펼치기/모두 접기" 버튼.
   - 처음엔 라디오로 조를 골라야 했는데 "클릭하기 힘들다"고 해서 박스 직접 클릭 + 자동 펼침으로 바꿈.
3. **한눈에 비교** — 항목 하나를 고르면 **계열 4 × 조 N개를 서브플롯 격자로 한 화면에** 보여줌(클릭 없이). 같은 열은 y축을 맞춰 혼자 튀는 센서가 눈에 띔. 선 색 = 현재 상태. 기본 항목은 그래프가 가장 많은 항목.
   - 센서가 많아서 "하나씩 클릭"이 불가능하다는 요구에서 나온 핵심 페이지.
4. **경고 센터** — 사고 단위 카드를 **쭉 나열하고 스크롤**(표에서 행을 클릭해야 그래프가 나오던 방식은 사용자가 싫어해서 변경). 카드 안에 센서 그래프(최대 3개). 유형/건물/공정/진행 중 필터, "더 보기".
5. **차트(`charts.py`)**: 추이선 + USL/LSL 점선 + 근접(주황)/이탈(빨강) 배경 + 이상 구간 세로 음영(Hold 파랑, σ 보라, 동료 이탈 분홍) + **동료 범위(회색 띠)와 중앙값(점선)**. 동료 범위가 있어야 "어디서 벌어졌는지" 보임.
6. **디자인**: 다크 관제실 스타일(진한 남색, 시안 포인트, 숫자는 Orbitron 폰트), 사이드바 없음, 상단 탭 + 헤더 바(진행 중 사고 건수 표시). 사용자가 *"AI가 만들면 다 왼쪽 회색 사이드바에 똑같다"* 고 불평해서 의도적으로 일반 Streamlit 기본 모양을 피함. 이 방향 유지.
7. 색상 의미 고정: 빨강 스펙 이탈 / 주황 근접 / 파랑 Hold / 보라 σ 초과 / 분홍 동료 이탈 / 초록 정상 / 회색 해소.

## 7. 사내망 환경 주의

- 사내에서는 **외부 GitHub, 외부 Claude 사용 불가**. 외부 CDN/API 호출이 있으면 안 됨.
- 현재 코드의 외부 의존은 `app.py` CSS의 **Google Fonts `@import`(Orbitron)** 하나뿐. 차단돼도 기본 폰트로 대체되어 동작하지만, 깔끔하게 하려면 폰트 파일을 사내에 넣어 로컬로 불러오거나 `@import`를 제거.
- Streamlit/Plotly는 프론트 리소스를 패키지에 포함하므로 CDN 없이 동작. **`pip install`만 사내 PyPI/오프라인 휠로 해결**하면 됨.
- 사내 데이터를 외부로 보내는 코드(텔레메트리 등) 금지. 필요하면 `.streamlit/config.toml`에 `[browser] gatherUsageStats = false` 추가.

## 8. 검증 방법

- **오탐 확인**: 감지 로직을 건드릴 때마다, 평소(이상 없는) 구간에서 경고가 몇 개 걸리는지 먼저 세어 볼 것. (데모에서는 `get_plant.__wrapped__()`로 직접 호출해 `core.events()`로 확인했음.)
- 데모 모드에서 `ANOMALIES`에 심은 이상 12건이 의도한 유형으로 잡히는지 확인:
  스펙 이탈(2동 유기A 폭기조1·2·3 DO 동시 저하→사고 1건으로 묶임, 2동 무기1 B 반응조2 pH), Hold 3건, σ 1건, **PEER 전용 3건(규격 안이라 임계값으로는 안 잡힘)**, 과거 해소 1건.
- 화면 확인: 4개 탭 모두 예외 없이 렌더링, "상세 ›" 버튼 → 공정 상세 이동, 조 박스 클릭 → 그래프 펼침/접힘.

## 9. 작업 원칙 (사내 Claude에게)

1. **먼저 이 문서를 끝까지 읽고**, 데모를 실행해서 현재 동작을 눈으로 확인한 뒤 수정할 것.
2. 데이터 소스, 태그 매핑, 규격값은 **모르면 사용자에게 질문**. 임의로 지어내지 말 것.
3. 한 번에 다 바꾸지 말고 **① 데이터 연결 → ② 규격/설정 교체 → ③ 오탐 점검 → ④ 화면 미세 조정** 순서로, 단계마다 동작 확인.
4. 화면/감지 규칙을 바꿔야 할 때는 **바꾸는 이유와 영향**을 먼저 사용자에게 설명.
5. 센서가 늘어도 깨지지 않도록 구조는 설정 기반 유지 (하드코딩 금지).

---

## 부록: 사내 Claude에게 처음 줄 지시문 (복사해서 사용)

```
첨부한 HANDOFF.md를 처음부터 끝까지 읽고, 같은 폴더의 코드(app.py, core.py, charts.py, views.py)를 읽어줘.
이 프로젝트는 데모 데이터로 동작하는 폐수처리 공정 관제 대시보드(Streamlit)이고,
이제 우리 회사 서버 데이터로 연결해서 실제로 쓰게 만들려고 해.

규칙:
- HANDOFF.md의 "설계 결정"(6번)과 "감지 규칙"(5번)은 이유가 있으니 내가 허락하기 전에 바꾸지 마.
- 데이터 소스(DB 종류, 접속 방법, 태그 이름 규칙), 실제 규격값은 내가 알려줄 테니 추측하지 말고 모자란 건 질문해.
- 먼저 데모를 실행해서 4개 탭이 정상 동작하는지 확인하고 결과를 알려줘.
- 그다음 HANDOFF.md 4번 순서대로 하나씩 진행하고, 각 단계가 끝날 때마다 무엇을 바꿨는지 요약해줘.

우선 첫 단계로: 데모를 실행해 보고, 데이터 연결에 필요한 정보 중 내가 알려줘야 하는 목록을 질문해줘.
```


---

# 소스 코드 전체 (그대로 같은 이름의 파일로 저장해서 사용)
아래 각 블록의 제목이 파일 경로입니다. `wwtp_dashboard/` 폴더 아래에 같은 이름으로 저장하세요.

## 파일: `requirements.txt`

````text
streamlit>=1.40
plotly>=5.20
pandas>=2.0
numpy>=1.26
````

## 파일: `.streamlit/config.toml`

````toml
[theme]
base = "dark"
primaryColor = "#22d3ee"
backgroundColor = "#0b0f19"
secondaryBackgroundColor = "#121a2b"
textColor = "#e2e8f0"
borderColor = "#1e293b"

[client]
toolbarMode = "minimal"

[browser]
gatherUsageStats = false
````

## 파일: `app.py`

````python
"""폐수처리 공정 품질 현황 대시보드 (데모 데이터, 센서 약 650개).

실행:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="WWTP 품질 관제", page_icon="💧", layout="wide", initial_sidebar_state="collapsed")

import views  # noqa: E402  (set_page_config 이후 import)
from core import get_plant, incidents  # noqa: E402
from views import RANGES  # noqa: E402

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&display=swap');

/* 사이드바 제거 → 상단 내비 + 헤더 바 */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }
.block-container { padding-top: 4.5rem; max-width: 1600px; }

/* 헤더 바 */
.wwtp-bar { display:flex; align-items:center; gap:14px; padding:10px 16px; margin-bottom:6px;
  background: linear-gradient(90deg, rgba(34,211,238,.10), rgba(18,26,43,.0) 70%);
  border:1px solid rgba(34,211,238,.25); border-radius:12px; }
.wwtp-logo { width:38px; height:38px; border-radius:9px; display:flex; align-items:center; justify-content:center;
  background: rgba(34,211,238,.12); border:1px solid rgba(34,211,238,.4); font-size:20px; }
.wwtp-title { font-weight:700; letter-spacing:.04em; color:#f1f5f9; font-size:15px; line-height:1.2; }
.wwtp-sub { color:#64748b; font-size:11px; }
.wwtp-live { font-family:'Orbitron',sans-serif; font-size:10px; padding:2px 8px; border-radius:5px;
  color:#22d3ee; background:rgba(34,211,238,.12); border:1px solid rgba(34,211,238,.4); margin-left:8px; }
.wwtp-pill { margin-left:auto; padding:5px 12px; border-radius:8px; font-size:12px; font-weight:700; }
.wwtp-pill.bad { color:#fca5a5; background:rgba(239,68,68,.15); border:1px solid rgba(239,68,68,.5);
  animation: glow 1.6s infinite; }
.wwtp-pill.ok { color:#86efac; background:rgba(34,197,94,.12); border:1px solid rgba(34,197,94,.4); }
@keyframes glow { 0%,100% { box-shadow:0 0 10px rgba(239,68,68,.6);} 50% { box-shadow:0 0 1px rgba(239,68,68,.2);} }

/* 카드(테두리 컨테이너) */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: rgba(18,26,43,.72); border:1px solid rgba(255,255,255,.07) !important; border-radius:12px;
}
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlockBorderWrapper"] { background: transparent; }

/* 숫자는 계기판 폰트 */
[data-testid="stMetricValue"] { font-family:'Orbitron',sans-serif; color:#22d3ee; font-weight:700; }
[data-testid="stMetricLabel"] { color:#94a3b8; }
h3 { letter-spacing:.02em; }

/* 종합: 지금 확인할 곳 */
.ilist { border:1px solid rgba(255,255,255,.07); border-radius:12px; background:rgba(18,26,43,.72); overflow:hidden; }
.ir { display:grid; grid-template-columns:130px 190px 1fr 90px 70px; gap:10px; padding:9px 14px; font-size:13px;
  border-bottom:1px solid rgba(255,255,255,.05); align-items:center; }
.ir:last-child { border-bottom:none; }
.ik { font-weight:700; } .it { color:#e2e8f0; } .iw { color:#94a3b8; } .ic, .id { color:#64748b; text-align:right; font-size:12px; }

/* 종합: 공정 카드 */
.bh { font-weight:700; color:#cbd5e1; letter-spacing:.05em; margin:14px 0 6px; font-size:13px; }
.pt { display:flex; justify-content:space-between; font-size:14px; margin-bottom:8px; }
.pt b { color:#f1f5f9; font-size:16px; }
.pl { display:flex; gap:6px; margin-bottom:8px; }
.ln { width:30px; text-align:center; padding:2px 0; border:1px solid; border-radius:6px; font-size:12px; font-weight:700; color:#f1f5f9; }
.ps { color:#94a3b8; font-size:12px; margin-bottom:4px; } .ps b { color:#e2e8f0; }

/* 공정 상세: 흐름도(조 = 버튼) */
.lh { display:flex; gap:14px; align-items:baseline; margin:14px 0 6px; font-size:13px; } .lh b { color:#e2e8f0; font-size:14px; }
[class*="st-key-nd-"] button { height:auto; min-height:0; padding:7px 10px; justify-content:flex-start;
  background:rgba(18,26,43,.72); }
[class*="st-key-nd-"] button:hover { background:rgba(34,211,238,.08); }
[class*="st-key-nd-"] button p { font-size:12px; line-height:1.55; text-align:left; margin:0; }
</style>
"""

pages = {
    "overview": st.Page(views.overview, title="종합 현황", icon="🏭", default=True),
    "process": st.Page(views.process, title="공정 상세", icon="🔎", url_path="process"),
    "compare": st.Page(views.compare, title="한눈에 비교", icon="📊", url_path="compare"),
    "alerts": st.Page(views.alerts, title="경고 센터", icon="🚨", url_path="alerts"),
}
st.session_state["_pages"] = pages
nav = st.navigation(list(pages.values()), position="top")

st.markdown(CSS, unsafe_allow_html=True)

plant = get_plant()
n_inc = sum(x["active"] for x in incidents(plant, RANGES[st.session_state.get("range", "24시간")]))
pill = (
    f'<span class="wwtp-pill bad">⚠ 진행 중 사고 {n_inc}건</span>'
    if n_inc
    else '<span class="wwtp-pill ok">● 전 센서 정상</span>'
)
bar, ctl = st.columns([3.2, 1.4], vertical_alignment="center")
bar.markdown(
    f"""<div class="wwtp-bar"><div class="wwtp-logo">💧</div>
    <div><div class="wwtp-title">WWTP QUALITY CONTROL<span class="wwtp-live">LIVE · DEMO</span></div>
    <div class="wwtp-sub">폐수처리 공정 수질 · 센서 {plant.n}개 이상 감지 관제</div></div>{pill}</div>""",
    unsafe_allow_html=True,
)
with ctl:
    c1, c2 = st.columns([3, 1.3], vertical_alignment="bottom")
    c1.select_slider("조회 구간", options=list(RANGES), value="24시간", key="range", help="차트 표시 구간이자 경고 이력 조회 구간")
    with c2.popover("기준", help="경고 기준"):
        st.markdown(
            "- **스펙 이탈** LSL/USL 벗어남\n- **근접** 규격폭 10% 이내\n"
            "- **Hold** 1시간(12샘플) 연속 같은 값\n- **σ 초과** 1시간 이동 표준편차 > 항목별 기준\n"
            "- **동료 대비 이탈** 같은 공정·같은 항목 센서들의 중앙값과 5σ 이상 벌어져 30분 지속 (규격 안이어도 감지)"
        )
        if st.button("데모 데이터 새로 만들기", width="stretch"):
            st.cache_resource.clear()
            st.rerun()

nav.run()
````

## 파일: `core.py`

````python
"""공정 구조 / 규격 / 데모 데이터 / 이상 감지 (센서 약 650개, 5분 간격).

실제 적용 시:
  - STAGE_SPEC 의 규격(LSL/USL, 표준편차 기준)만 실제 값으로 수정
  - _build() 안의 '데모 데이터 생성' 부분을 서버(DB) 조회로 교체 → V(센서×시간) 배열만 채우면 나머지는 그대로 동작
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────────────────────
# 1. 설비 구조
# ─────────────────────────────────────────────────────────────
BUILDINGS = ["1동", "2동", "3동"]
PROCESSES = ["유기", "무기1", "무기2", "산폐수"]
LINES = ["A계열", "B계열", "C계열", "D계열"]


def tanks_of(proc: str) -> list[tuple[str, str, list[str]]]:
    """공정 흐름 순서대로 (조 이름, 규격 종류, 센서 항목들)."""
    if proc == "유기":
        return (
            [("전탈조", "전탈조", ["NO3-N", "외부탄소원"])]
            + [(f"폭기조{i}", "폭기조", ["DO", "pH"]) for i in range(1, 6)]
            + [("후탈조", "후탈조", ["NO3-N", "외부탄소원"]),
               ("재폭기조", "재폭기조", ["DO", "pH"]),
               ("침전조", "유기침전조", ["SS", "torque"])]
        )
    return (
        [(f"반응조{i}", "반응조", ["pH", "소석회", "응결제"]) for i in range(1, 4)]
        + [("응집조", "응집조", ["고분자"]), ("침전조", "무기침전조", ["F", "SS"])]
    )


NAN = np.nan
# (조 종류, 항목): 단위, 하한, 상한, 평상시 값, 평상시 변동(σ), 이동표준편차 경고 기준, 소수 자리
STAGE_SPEC = {
    ("폭기조", "DO"):       dict(unit="mg/L", lsl=1.0, usl=4.0, base=2.3, sigma=0.30, std_limit=0.5, dec=2),
    ("폭기조", "pH"):       dict(unit="pH", lsl=6.5, usl=8.5, base=7.2, sigma=0.12, std_limit=0.22, dec=2),
    ("재폭기조", "DO"):     dict(unit="mg/L", lsl=2.0, usl=6.0, base=3.8, sigma=0.35, std_limit=0.6, dec=2),
    ("재폭기조", "pH"):     dict(unit="pH", lsl=6.5, usl=8.5, base=7.1, sigma=0.12, std_limit=0.3, dec=2),
    ("전탈조", "NO3-N"):    dict(unit="mg/L", lsl=NAN, usl=12.0, base=5.0, sigma=0.7, std_limit=1.5, dec=2),
    ("전탈조", "외부탄소원"): dict(unit="L/h", lsl=5.0, usl=60.0, base=30.0, sigma=3.5, std_limit=8.0, dec=1),
    ("후탈조", "NO3-N"):    dict(unit="mg/L", lsl=NAN, usl=6.0, base=1.8, sigma=0.3, std_limit=0.7, dec=2),
    ("후탈조", "외부탄소원"): dict(unit="L/h", lsl=5.0, usl=40.0, base=18.0, sigma=2.2, std_limit=5.0, dec=1),
    ("유기침전조", "SS"):    dict(unit="mg/L", lsl=NAN, usl=30.0, base=10.0, sigma=1.6, std_limit=4.0, dec=1),
    ("유기침전조", "torque"): dict(unit="%", lsl=20.0, usl=80.0, base=48.0, sigma=3.5, std_limit=8.0, dec=1),
    ("반응조", "pH"):       dict(unit="pH", lsl=9.0, usl=11.5, base=10.2, sigma=0.18, std_limit=0.5, dec=2),
    ("반응조", "소석회"):    dict(unit="L/h", lsl=60.0, usl=260.0, base=150.0, sigma=13.0, std_limit=30.0, dec=1),
    ("반응조", "응결제"):    dict(unit="L/h", lsl=10.0, usl=60.0, base=32.0, sigma=3.0, std_limit=7.0, dec=1),
    ("응집조", "고분자"):    dict(unit="L/h", lsl=5.0, usl=30.0, base=15.0, sigma=1.6, std_limit=3.5, dec=1),
    ("무기침전조", "F"):     dict(unit="ppm", lsl=NAN, usl=15.0, base=6.0, sigma=1.0, std_limit=2.5, dec=2),
    ("무기침전조", "SS"):    dict(unit="mg/L", lsl=NAN, usl=30.0, base=9.0, sigma=1.5, std_limit=4.0, dec=1),
}

# ─────────────────────────────────────────────────────────────
# 2. 감지 규칙 (5분 간격 기준)
# ─────────────────────────────────────────────────────────────
STEP_MIN = 5
PER_DAY = 24 * 60 // STEP_MIN        # 288
N_PTS = 3 * PER_DAY                   # 데모: 3일치
BASE_N = 2 * PER_DAY                  # 앞 2일 = 평소 기준(동료 편차 기준 산정용)

NEAR_RATIO = 0.10                     # 규격폭 10% 이내 → 근접
HOLD_N = 12                           # 12개(=1시간) 연속 같은 값 → Hold
STD_N = 12                            # 이동 표준편차 윈도우 = 1시간
PEER_ALPHA, PEER_K, PEER_PERSIST = 0.2, 5.0, 6   # 동료 대비 편차: EWMA, 5σ, 30분 지속

KIND = {
    "SPEC": dict(label="스펙 이탈", color="#ef4444", icon="🔴", rank=0),
    "NEAR": dict(label="상하한 근접", color="#f97316", icon="🟠", rank=1),
    "HOLD": dict(label="1시간 Hold", color="#3b82f6", icon="🔵", rank=2),
    "STD":  dict(label="표준편차 초과", color="#a855f7", icon="🟣", rank=3),
    "PEER": dict(label="동료 대비 이탈(조기경보)", color="#ec4899", icon="🩷", rank=4),
}
NONE_RANK = 99


# ─────────────────────────────────────────────────────────────
# 3. 데모 이상 상황 (끝에서 n개 구간)
# ─────────────────────────────────────────────────────────────
# (건물, 공정, 계열, 조, 항목): (종류, 길이(샘플), 값, 끝에서 떨어진 샘플수)
#   step : 갑자기 delta 만큼 이동   ramp : 서서히 delta 만큼 이동   bump : 과거에 솟았다 복귀
#   hold : 값 고정                   noisy : ±amp 요동
ANOMALIES = {
    # 블로워 이상: 같은 계열 폭기조 3개 DO 동시 저하 → 사고 1건으로 묶여야 함
    ("2동", "유기", "A계열", "폭기조1", "DO"): ("step", 30, -1.3, 0),
    ("2동", "유기", "A계열", "폭기조2", "DO"): ("step", 30, -1.5, 0),
    ("2동", "유기", "A계열", "폭기조3", "DO"): ("step", 30, -1.0, 0),
    ("2동", "무기1", "B계열", "반응조2", "pH"): ("ramp", 48, 1.5, 0),           # 상한 근접→이탈
    ("3동", "산폐수", "C계열", "침전조", "SS"): ("hold", 30, None, 0),          # 센서 고착
    ("1동", "유기", "D계열", "전탈조", "NO3-N"): ("hold", 18, None, 0),
    ("3동", "무기2", "C계열", "응집조", "고분자"): ("hold", 24, None, 0),
    ("2동", "유기", "B계열", "폭기조4", "pH"): ("noisy", 24, 0.45, 0),          # 변동성 증가
    # ↓ 규격 안이라 임계값으로는 안 잡히고, 동료와 비교해야 보이는 미세 변동
    ("1동", "유기", "C계열", "폭기조2", "DO"): ("ramp", 72, 0.7, 0),
    ("3동", "무기2", "A계열", "반응조1", "소석회"): ("ramp", 90, 38.0, 0),
    ("3동", "유기", "A계열", "후탈조", "외부탄소원"): ("ramp", 60, -7.0, 0),
    # 과거에 있었다가 해소된 이탈
    ("1동", "무기1", "D계열", "침전조", "F"): ("bump", 36, 9.8, 60),
}


# ─────────────────────────────────────────────────────────────
# 4. 데이터 구조
# ─────────────────────────────────────────────────────────────
class Plant:
    """센서 메타 + 값 배열 V(센서×시간) + 감지 플래그 F[종류](센서×시간)."""

    def __init__(self, meta, idx, V, F, std, med):
        self.meta, self.idx, self.V, self.F, self.std, self.med = meta, idx, V, F, std, med
        self.n, self.T = V.shape
        self.G = meta["G"].to_numpy()
        self.lsl = meta["lsl"].to_numpy(float)
        self.usl = meta["usl"].to_numpy(float)
        lo = np.where(np.isnan(self.lsl), 0.0, self.lsl)
        self.margin = (self.usl - lo) * NEAR_RATIO
        self.members = [np.where(self.G == g)[0] for g in range(self.G.max() + 1)]
        self.lookup = {
            (r.bldg, r.proc, r.line, r.tank, r.param): i for i, r in enumerate(meta.itertuples())
        }
        # 지금 시점에서 가장 나쁜 상태(rank), 없으면 NONE_RANK
        self.now_rank = np.full(self.n, NONE_RANK)
        for k, v in KIND.items():
            self.now_rank = np.where(F[k][:, -1], np.minimum(self.now_rank, v["rank"]), self.now_rank)

    def find(self, b, p, l, tank, param) -> int:
        return self.lookup[(b, p, l, tank, param)]

    def sel(self, **kw) -> np.ndarray:
        m = np.ones(self.n, bool)
        for k, v in kw.items():
            m &= self.meta[k].to_numpy() == v
        return np.where(m)[0]

    def active_kinds(self, i: int) -> list[str]:
        return sorted([k for k in KIND if self.F[k][i, -1]], key=lambda k: KIND[k]["rank"])

    def window_kinds(self, i: int, window: int) -> list[str]:
        return sorted([k for k in KIND if self.F[k][i, -window:].any()], key=lambda k: KIND[k]["rank"])

    def spec_text(self, i: int) -> str:
        u = self.meta["unit"].iat[i]
        if np.isnan(self.lsl[i]):
            return f"≤ {self.usl[i]:g} {u}"
        return f"{self.lsl[i]:g} ~ {self.usl[i]:g} {u}"

    def name(self, i: int) -> str:
        m = self.meta.iloc[i]
        return f"{m.bldg} {m.proc} {m.line} {m.tank} {m.param}"


def kind_by_rank(rank: int) -> str | None:
    for k, v in KIND.items():
        if v["rank"] == rank:
            return k
    return None


# ─────────────────────────────────────────────────────────────
# 5. 생성 + 감지
# ─────────────────────────────────────────────────────────────
def _persist_backfill(raw: np.ndarray, n: int) -> np.ndarray:
    """raw 가 n 샘플 이상 연속인 구간을 통째로 True 로."""
    run = np.zeros(raw.shape[0], int)
    end = np.zeros_like(raw)
    for t in range(raw.shape[1]):
        run = np.where(raw[:, t], run + 1, 0)
        end[:, t] = run >= n
    full = end.copy()
    for k in range(1, n):
        full[:, :-k] |= end[:, k:]
    return full


def _apply(V, i, kind, n, arg, off, dec, rng):
    end = V.shape[1] - off
    sl = slice(end - n, end)
    if kind == "ramp":
        V[i, sl] += np.linspace(0, arg, n)
    elif kind == "step":
        V[i, sl] += arg * np.clip(np.arange(n) / 6, 0, 1)
    elif kind == "bump":
        V[i, sl] += arg * np.sin(np.pi * np.arange(n) / (n - 1)) ** 2
    elif kind == "noisy":
        V[i, sl] += rng.uniform(-arg, arg, n)


@st.cache_resource(show_spinner="센서 데이터 생성 중…")
def get_plant() -> Plant:
    rng = np.random.default_rng(11)

    rows = []
    for b in BUILDINGS:
        for p in PROCESSES:
            for l in LINES:
                for tank, stage, params in tanks_of(p):
                    for prm in params:
                        rows.append(dict(bldg=b, proc=p, line=l, tank=tank, stage=stage, param=prm, **STAGE_SPEC[(stage, prm)]))
    meta = pd.DataFrame(rows)
    meta["G"] = meta.groupby(["bldg", "proc", "stage", "param"]).ngroup()  # 동료 그룹
    S, T = len(meta), N_PTS
    G = meta["G"].to_numpy()
    nG = G.max() + 1

    # ── 데모 데이터 생성 (실서비스에서는 DB 조회로 교체) ─────────────
    sig = meta["sigma"].to_numpy()
    sig_g = meta.groupby("G")["sigma"].first().to_numpy()
    phi, k = 0.95, np.sqrt(1 - 0.95**2)
    common = np.empty((nG, T))
    idio = np.empty((S, T))
    common[:, 0] = rng.normal(0, 0.8 * sig_g)
    idio[:, 0] = rng.normal(0, 0.3 * sig)
    for t in range(1, T):
        common[:, t] = phi * common[:, t - 1] + k * rng.normal(0, 0.8 * sig_g)
        idio[:, t] = phi * idio[:, t - 1] + k * rng.normal(0, 0.3 * sig)
    mu = meta["base"].to_numpy() + rng.normal(0, 0.15 * sig)
    V = mu[:, None] + common[G] + idio

    idx = pd.date_range(end=pd.Timestamp.now().floor(f"{STEP_MIN}min"), periods=T, freq=f"{STEP_MIN}min")
    dec = meta["dec"].to_numpy()
    pending_hold = []
    for key, (kind, n, arg, off) in ANOMALIES.items():
        i = meta.index[(meta.bldg == key[0]) & (meta.proc == key[1]) & (meta.line == key[2]) & (meta.tank == key[3]) & (meta.param == key[4])][0]
        if kind == "hold":
            pending_hold.append((i, n, off))
        else:
            _apply(V, i, kind, n, arg, off, dec[i], rng)
    V = np.clip(V, 0, None)
    for d in np.unique(dec):
        m = dec == d
        V[m] = np.round(V[m], int(d))
    for i, n, off in pending_hold:                      # Hold 는 반올림 후 값 고정
        end = T - off
        V[i, end - n:end] = V[i, end - n]
    # ─────────────────────────────────────────────────────────

    lsl, usl = meta["lsl"].to_numpy(float), meta["usl"].to_numpy(float)
    margin = (usl - np.where(np.isnan(lsl), 0.0, lsl)) * NEAR_RATIO
    L, U, M = lsl[:, None], usl[:, None], margin[:, None]

    spec = (V > U) | (V < L)
    near = ((V <= U) & (V >= U - M)) | ((V >= L) & (V <= L + M))

    eq = np.zeros_like(spec)
    eq[:, 1:] = V[:, 1:] == V[:, :-1]
    hold = _persist_backfill(eq, HOLD_N - 1)

    std = pd.DataFrame(V.T).rolling(STD_N, min_periods=STD_N // 2).std().to_numpy().T
    stdx = np.nan_to_num(std, nan=0.0) > meta["std_limit"].to_numpy()[:, None]

    med = np.vstack([np.median(V[G == g], axis=0) for g in range(nG)])
    d = V - med[G]
    d = d - d[:, :BASE_N].mean(axis=1, keepdims=True)      # 평소의 고정 편차(오프셋)는 제외
    # 평소 편차폭: 이상치에 강한 MAD 로 전체 기간에서 추정
    sd_d = np.maximum(1.4826 * np.median(np.abs(d - np.median(d, axis=1, keepdims=True)), axis=1), 1e-9)
    ew = pd.DataFrame(d.T).ewm(alpha=PEER_ALPHA, adjust=False).mean().to_numpy().T
    peer = _persist_backfill(np.abs(ew) > PEER_K * sd_d[:, None], PEER_PERSIST)

    F = {"SPEC": spec, "NEAR": near, "HOLD": hold, "STD": stdx, "PEER": peer}
    return Plant(meta, idx, V, F, std, med)


# ─────────────────────────────────────────────────────────────
# 6. 이벤트 / 사고(incident) 묶기
# ─────────────────────────────────────────────────────────────
def events(plant: Plant, window: int) -> pd.DataFrame:
    """조회 구간 안에서 걸린 (센서, 종류) 별 1행."""
    rows = []
    base = plant.T - window
    for kind, v in KIND.items():
        W = plant.F[kind][:, -window:]
        for i in np.where(W.any(axis=1))[0]:
            w = W[i]
            first = int(np.argmax(w))
            last = window - 1 - int(np.argmax(w[::-1]))
            rows.append(
                dict(i=int(i), kind=kind, rank=v["rank"], active=bool(plant.F[kind][i, -1]),
                     first=plant.idx[base + first], last=plant.idx[base + last], minutes=int(w.sum()) * STEP_MIN)
            )
    return pd.DataFrame(rows, columns=["i", "kind", "rank", "active", "first", "last", "minutes"])


def incidents(plant: Plant, window: int) -> list[dict]:
    """같은 (동·공정·계열·조 종류) 안의 경고는 사고 1건으로 묶는다."""
    ev = events(plant, window)
    if ev.empty:
        return []
    m = plant.meta
    ev["gk"] = list(zip(m["bldg"].to_numpy()[ev["i"]], m["proc"].to_numpy()[ev["i"]],
                        m["line"].to_numpy()[ev["i"]], m["stage"].to_numpy()[ev["i"]]))
    out = []
    for gk, g in ev.groupby("gk", sort=False):
        sids = list(dict.fromkeys(g.sort_values(["rank", "i"])["i"]))
        tanks = sorted({m["tank"].iat[i] for i in sids})
        params = sorted({m["param"].iat[i] for i in sids})
        out.append(
            dict(
                bldg=gk[0], proc=gk[1], line=gk[2], stage=gk[3], sids=sids, ev=g,
                active=bool(g["active"].any()), rank=int(g["rank"].min()),
                first=g["first"].min(), last=g["last"].max(),
                title=f"{gk[0]} · {gk[1]} · {gk[2]}",
                what=f"{', '.join(tanks)} — {', '.join(params)}",
            )
        )
    out.sort(key=lambda x: (not x["active"], x["rank"], -len(x["sids"]), -x["last"].value))
    return out
````

## 파일: `charts.py`

````python
"""Plotly 차트: 추이 + 규격선 + 근접/이탈 구간 + 이상 구간 + 동료 비교."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from core import KIND, Plant

LINE_COLOR = "#22d3ee"


def style(fig: go.Figure) -> go.Figure:
    """다크 관제 테마 공통 스타일."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94a3b8"),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,.05)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,.05)", zeroline=False)
    return fig


def _spans(mask: np.ndarray, x) -> list[tuple]:
    out, start = [], None
    for i, f in enumerate(mask):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((x[start], x[i - 1]))
            start = None
    if start is not None:
        out.append((x[start], x[-1]))
    return out


def sensor_figure(plant: Plant, i: int, window: int, height: int = 230, peers: bool = True) -> go.Figure:
    unit = plant.meta["unit"].iat[i]
    lsl, usl, m = plant.lsl[i], plant.usl[i], plant.margin[i]
    has_l = not np.isnan(lsl)
    x = plant.idx[-window:]
    y = plant.V[i, -window:]

    lo = min(y.min(), lsl if has_l else y.min())
    hi = max(y.max(), usl)
    pad = (hi - lo) * 0.08
    y0, y1 = lo - pad, hi + pad

    fig = go.Figure()

    # 규격 영역: 근접(주황) / 이탈(빨강)
    fig.add_hrect(y0=usl - m, y1=usl, fillcolor="rgba(249,115,22,.14)", line_width=0, layer="below")
    fig.add_hrect(y0=usl, y1=y1, fillcolor="rgba(239,68,68,.12)", line_width=0, layer="below")
    if has_l:
        fig.add_hrect(y0=lsl, y1=lsl + m, fillcolor="rgba(249,115,22,.14)", line_width=0, layer="below")
        fig.add_hrect(y0=y0, y1=lsl, fillcolor="rgba(239,68,68,.12)", line_width=0, layer="below")

    # 이상 구간 세로 음영 (Hold / σ 초과 / 동료 이탈)
    for kind, rgb in (("HOLD", "59,130,246"), ("STD", "168,85,247"), ("PEER", "236,72,153")):
        for a, b in _spans(plant.F[kind][i, -window:], x):
            fig.add_vrect(x0=a, x1=b, fillcolor=f"rgba({rgb},.16)", line_width=0, layer="below")

    # 동료(같은 항목 다른 센서) 범위 + 중앙값
    if peers:
        mem = plant.members[plant.G[i]]
        mem = mem[mem != i]
        if len(mem):
            P = plant.V[mem][:, -window:]
            fig.add_trace(go.Scatter(x=x, y=P.min(axis=0), mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=x, y=P.max(axis=0), mode="lines", line=dict(width=0), fill="tonexty",
                                     fillcolor="rgba(148,163,184,.16)", hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=x, y=np.median(P, axis=0), mode="lines", line=dict(color="#94a3b8", width=1.2, dash="dot"),
                                     hovertemplate="동료 중앙값 %{y:.2f}<extra></extra>", showlegend=False))

    fig.add_trace(
        go.Scatter(x=x, y=y, mode="lines", line=dict(color=LINE_COLOR, width=1.9),
                   hovertemplate="<b>%{y:.2f}</b> " + unit + "<extra></extra>", showlegend=False)
    )
    for kind, size in (("NEAR", 5), ("SPEC", 7)):
        mk = plant.F[kind][i, -window:]
        if mk.any():
            fig.add_trace(go.Scatter(x=x[mk], y=y[mk], mode="markers", marker=dict(color=KIND[kind]["color"], size=size),
                                     hovertemplate=f"{KIND[kind]['label']} %{{y:.2f}}<extra></extra>", showlegend=False))

    fig.add_hline(y=usl, line=dict(color="#ef4444", width=1.3, dash="dash"), annotation_text=f"USL {usl:g}",
                  annotation_position="top left", annotation_font=dict(size=10, color="#ef4444"))
    if has_l:
        fig.add_hline(y=lsl, line=dict(color="#ef4444", width=1.3, dash="dash"), annotation_text=f"LSL {lsl:g}",
                      annotation_position="bottom left", annotation_font=dict(size=10, color="#ef4444"))

    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), showlegend=False, hovermode="x unified",
        xaxis=dict(tickformat="%H:%M" if window <= 288 else "%m/%d %H:%M", showgrid=False),
        yaxis=dict(range=[y0, y1], title=None),
    )
    return style(fig)
````

## 파일: `views.py`

````python
"""화면 3개: 종합 현황(공정 12개) → 공정 상세(계열·조 흐름) → 경고 센터(사고 묶음)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from charts import _spans, sensor_figure, style
from core import (
    BUILDINGS, KIND, LINES, NONE_RANK, PROCESSES, STEP_MIN, get_plant, incidents, kind_by_rank, tanks_of,
)

RANGES = {"3시간": 36, "6시간": 72, "12시간": 144, "24시간": 288, "48시간": 576}
OK_COLOR, RESOLVED_COLOR, DIM = "#22c55e", "#64748b", "#cbd5e1"


# ───────────────────────── 공통 ─────────────────────────
def _ctx():
    return get_plant(), RANGES[st.session_state.get("range", "24시간")]


def _color(rank: int) -> str:
    return OK_COLOR if rank >= NONE_RANK else KIND[kind_by_rank(rank)]["color"]


def _status_text(rank: int) -> str:
    return "정상" if rank >= NONE_RANK else KIND[kind_by_rank(rank)]["label"].split("(")[0]


def _badges(kinds: list[str]) -> str:
    if not kinds:
        return f'<span style="color:{OK_COLOR};font-weight:700">● 정상</span>'
    return "&nbsp;&nbsp;".join(
        f'<span style="color:{KIND[k]["color"]};font-weight:700">● {KIND[k]["label"].split("(")[0]}</span>' for k in kinds
    )


def _legend():
    st.caption(
        "배경: 주황 = 상하한 근접 · 빨강 = 이탈  |  세로 음영: 파랑 = Hold · 보라 = σ 초과 · 분홍 = 동료 대비 이탈  |  "
        "회색 띠/점선 = 같은 항목 다른 센서의 범위/중앙값"
    )


def _header(title: str, sub: str):
    plant = get_plant()
    st.markdown(f"### {title}")
    st.caption(f"{sub}  |  데이터 기준 {plant.idx[-1]:%Y-%m-%d %H:%M} · {STEP_MIN}분 평균 (데모)")


def _sensor_card(plant, i: int, window: int, height: int = 240, tag: str = "", note: str = ""):
    m = plant.meta.iloc[i]
    kinds = plant.active_kinds(i)
    hist = [k for k in plant.window_kinds(i, window) if k not in kinds]
    cur = plant.V[i, -1]
    prev = plant.V[i, -13]
    with st.container(border=True):
        if tag:
            st.markdown(f"**{tag}**")
        c = st.columns([1.1, 1.5])
        c[0].metric(f"{m.param} ({m.unit})", f"{cur:.2f}", f"{cur - prev:+.2f} /1h", delta_color="off")
        with c[1]:
            st.markdown(
                _badges(kinds) if kinds or not hist else f'<span style="color:{RESOLVED_COLOR};font-weight:700">● 해소됨</span>',
                unsafe_allow_html=True,
            )
            line2 = f"규격 {plant.spec_text(i)}  ·  σ {np.nan_to_num(plant.std[i, -1]):.2f}"
            if hist:
                line2 += "  ·  이력: " + ", ".join(KIND[k]["label"].split("(")[0] for k in hist)
            st.caption(line2)
        if note:
            st.caption(note)
        st.plotly_chart(sensor_figure(plant, i, window, height), width="stretch",
                        key=f"c-{i}-{window}-{tag}", config={"displayModeBar": False})


def _incident_charts(plant, x: dict, window: int, prefix: str):
    """사고 1건의 센서 그래프 (최대 3개) + 나머지 센서 목록."""
    sids = x["sids"][:3]
    for col, i in zip(st.columns(len(sids)), sids):
        with col:
            m = plant.meta.iloc[i]
            ks = ", ".join(KIND[k]["label"].split("(")[0] for k in plant.window_kinds(i, window))
            st.caption(f"**{m.tank} · {m.param}**  —  {ks}")
            st.plotly_chart(sensor_figure(plant, i, window, 210), width="stretch",
                            key=f"{prefix}-{i}-{window}", config={"displayModeBar": False})
    if len(x["sids"]) > 3:
        st.caption("외 센서: " + ", ".join(f"{plant.meta['tank'].iat[i]} {plant.meta['param'].iat[i]}" for i in x["sids"][3:]))


# ───────────────────────── 1. 종합 현황 ─────────────────────────
def overview():
    plant, window = _ctx()
    _header("종합 현황", "3개 동 · 12개 공정 · 센서 전체를 한눈에")

    now = {k: int(plant.F[k][:, -1].sum()) for k in KIND}
    n_bad = int((plant.now_rank < NONE_RANK).sum())
    cols = st.columns(6)
    cols[0].metric("🟢 정상 / 전체 센서", f"{plant.n - n_bad} / {plant.n}")
    for c, k in zip(cols[1:], KIND):
        c.metric(f"{KIND[k]['icon']} {KIND[k]['label'].split('(')[0]}", f"{now[k]} 개")

    inc = [x for x in incidents(plant, window) if x["active"]]
    st.subheader("지금 확인할 곳")
    if not inc:
        st.success("진행 중인 경고가 없습니다. 전 공정 정상입니다.")
    else:
        st.caption(f"진행 중 {len(inc)}건 (같은 계열·같은 조의 경고는 1건으로 묶었어요) — 줄을 누르면 그래프가 펼쳐져요")
        all_open = st.toggle("진행 중 사고 모두 펼치기", value=False, key="ov_all_open")
        for n, x in enumerate(inc[:8]):
            label = (
                f"{KIND[kind_by_rank(x['rank'])]['icon']} {_status_text(x['rank'])}  ·  {x['title']}  ·  "
                f"{x['what']}  ·  센서 {len(x['sids'])}개  ·  {x['first']:%H:%M}~"
            )
            with st.expander(label, expanded=(all_open or n == 0)):
                _incident_charts(plant, x, window, f"ov{n}")
        if len(inc) > 8:
            st.caption(f"외 {len(inc) - 8}건 — 경고 센터에서 모두 볼 수 있어요")
        st.page_link(st.session_state["_pages"]["alerts"], label="경고 센터에서 그래프와 함께 보기", icon="🚨")

    st.subheader("공정 현황")
    st.caption("카드 = 공정 1개(계열 4개). A~D 칩의 색은 그 계열에서 가장 나쁜 센서 상태예요. [상세]를 눌러 내려가 보세요.")
    for b in BUILDINGS:
        st.markdown(f'<div class="bh">{b}</div>', unsafe_allow_html=True)
        cols = st.columns(4)
        for col, p in zip(cols, PROCESSES):
            ids = plant.sel(bldg=b, proc=p)
            r = plant.now_rank[ids]
            worst = int(r.min())
            n_b = int((r < NONE_RANK).sum())
            n_peer = int(plant.F["PEER"][ids, -1].sum())
            chips = ""
            for l in LINES:
                lr = int(plant.now_rank[plant.sel(bldg=b, proc=p, line=l)].min())
                chips += f'<span class="ln" style="background:{_color(lr)}33;border-color:{_color(lr)}">{l[0]}</span>'
            sub = f"이상 센서 <b>{n_b}</b> / {len(ids)}" + (f" · 조기경보 <b>{n_peer}</b>" if n_peer else "")
            with col:
                with st.container(border=True):
                    st.markdown(
                        f'<div class="pt"><b>{p}</b><span style="color:{_color(worst)}">● {_status_text(worst)}</span></div>'
                        f'<div class="pl">{chips}</div><div class="ps">{sub}</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("상세 ›", key=f"go-{b}-{p}", width="stretch"):
                        st.session_state["_jump"] = (b, p)
                        st.switch_page(st.session_state["_pages"]["process"])


# ───────────────────────── 2. 공정 상세 ─────────────────────────
def _toggle_node(line: str, tank: str):
    s = set(st.session_state.get("proc_open", set()))
    s ^= {(line, tank)}
    st.session_state["proc_open"] = s


def _set_open(nodes):
    st.session_state["proc_open"] = set(nodes)


def process():
    plant, window = _ctx()
    _header("공정 상세", "계열별 흐름도 — 이상 있는 조는 자동으로 펼쳐지고, 박스를 누르면 펼침/접힘이 바뀌어요")

    jump = st.session_state.pop("_jump", None)
    if jump:
        st.session_state["proc_b"], st.session_state["proc_p"] = jump

    c = st.columns([1, 1, 1.3, 1.3, 2], vertical_alignment="bottom")
    b = c[0].selectbox("건물", BUILDINGS, key="proc_b")
    p = c[1].selectbox("공정", PROCESSES, key="proc_p")
    tanks = tanks_of(p)

    # 조(노드)별 상태 · 현재값
    info = {}
    for l in LINES:
        for tank, stage, params in tanks:
            vals, worst = [], NONE_RANK
            for prm in params:
                i = plant.find(b, p, l, tank, prm)
                worst = min(worst, int(plant.now_rank[i]))
                vals.append((prm, plant.V[i, -1]))
            info[(l, tank)] = (worst, vals)
    abnormal = [k for k, (w, _) in info.items() if w < NONE_RANK]

    if st.session_state.get("_last_proc") != (b, p):          # 공정을 바꾸면 이상 있는 조를 모두 펼침
        st.session_state["_last_proc"] = (b, p)
        st.session_state["proc_open"] = set(abnormal)
    opened = st.session_state.get("proc_open", set())

    c[2].button("이상 조 모두 펼치기", on_click=_set_open, args=(abnormal,), width="stretch")
    c[3].button("모두 접기", on_click=_set_open, args=([],), width="stretch")

    css = []
    for li, l in enumerate(LINES):
        ws = [info[(l, t[0])][0] for t in tanks]
        n_bad = sum(w < NONE_RANK for w in ws)
        extra = f" · 이상 {n_bad}개 조" if n_bad else ""
        st.markdown(
            f'<div class="lh"><b>{l}</b><span style="color:{_color(min(ws))}">● {_status_text(min(ws))}{extra}</span>'
            f'<span style="color:#475569;font-size:11px">흐름: 왼쪽 → 오른쪽</span></div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(len(tanks), gap="small")
        for ti, (tank, stage, params) in enumerate(tanks):
            w, vals = info[(l, tank)]
            icon = "🟢" if w >= NONE_RANK else KIND[kind_by_rank(w)]["icon"]
            label = f"{icon} **{tank}**  \n" + "  \n".join(f"{prm}  {v:.2f}" for prm, v in vals)
            key = f"nd-{li}-{ti}"
            with cols[ti]:
                st.button(label, key=key, on_click=_toggle_node, args=(l, tank), width="stretch")
            is_open = (l, tank) in opened
            glow = f"box-shadow:0 0 10px {_color(w)}66;" if w < NONE_RANK else ""
            border = "2px solid #22d3ee" if is_open else f"1px solid {_color(w)}aa"
            bg = "background:rgba(34,211,238,.10) !important;" if is_open else ""
            css.append(f".st-key-{key} button{{border:{border} !important;{glow}{bg}}}")

        for tank, stage, params in tanks:                          # 펼친 조의 그래프를 해당 계열 바로 아래에
            if (l, tank) in opened:
                st.markdown(f"##### ▼ {b} · {p} · {l} · {tank}")
                for col, prm in zip(st.columns(len(params)), params):
                    with col:
                        _sensor_card(plant, plant.find(b, p, l, tank, prm), window, height=240)
    st.markdown("<style>" + "".join(css) + "</style>", unsafe_allow_html=True)
    _legend()


# ───────────────────────── 3. 한눈에 비교 ─────────────────────────
def compare():
    plant, window = _ctx()
    _header("한눈에 비교", "같은 항목을 계열 × 조로 펼쳐서, 클릭 없이 혼자 튀는 센서를 찾기")

    c = st.columns([1, 1, 2], vertical_alignment="bottom")
    b = c[0].selectbox("건물", BUILDINGS, key="cmp_b")
    p = c[1].selectbox("공정", PROCESSES, key="cmp_p")
    full = c[2].toggle("규격선까지 보이게 스케일 확대 (끄면 데이터에 맞춰 확대)", value=False, key="cmp_full")

    tanks = tanks_of(p)
    params = list(dict.fromkeys(prm for _, _, ps in tanks for prm in ps))
    n_cols = [sum(prm_ in t[2] for t in tanks) for prm_ in params]
    prm = st.radio("항목", params, index=int(np.argmax(n_cols)), horizontal=True, key=f"cmp_prm_{p}")  # 기본: 그래프가 가장 많은 항목
    cols = [t for t in tanks if prm in t[2]]
    nr, nc = len(LINES), len(cols)

    titles = []
    for l in LINES:
        for tank, _, _ in cols:
            i = plant.find(b, p, l, tank, prm)
            ks = plant.active_kinds(i)
            icon = KIND[ks[0]]["icon"] if ks else "🟢"
            titles.append(f"{icon} {l[0]} · {tank}  {plant.V[i, -1]:.2f}")
    fig = make_subplots(rows=nr, cols=nc, subplot_titles=titles, shared_xaxes=True, shared_yaxes="columns",
                        vertical_spacing=0.06, horizontal_spacing=0.025)

    x = plant.idx[-window:]
    for r, l in enumerate(LINES, start=1):
        for ci, (tank, _, _) in enumerate(cols, start=1):
            i = plant.find(b, p, l, tank, prm)
            y = plant.V[i, -window:]
            ks = plant.active_kinds(i)
            color = KIND[ks[0]]["color"] if ks else "#22d3ee"
            for kind, rgb in (("HOLD", "59,130,246"), ("STD", "168,85,247"), ("PEER", "236,72,153")):
                for s0, s1 in _spans(plant.F[kind][i, -window:], x):
                    fig.add_vrect(x0=s0, x1=s1, fillcolor=f"rgba({rgb},.22)", line_width=0, layer="below", row=r, col=ci)
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=color, width=1.4), showlegend=False,
                                     hovertemplate="%{x|%H:%M}  <b>%{y:.2f}</b><extra></extra>"), row=r, col=ci)
            for kind, size in (("NEAR", 4), ("SPEC", 5)):
                mk = plant.F[kind][i, -window:]
                if mk.any():
                    fig.add_trace(go.Scatter(x=x[mk], y=y[mk], mode="markers", marker=dict(color=KIND[kind]["color"], size=size),
                                             showlegend=False, hoverinfo="skip"), row=r, col=ci)
            if not np.isnan(plant.lsl[i]):
                fig.add_hline(y=plant.lsl[i], line=dict(color="#ef4444", width=1, dash="dot"), row=r, col=ci)
            fig.add_hline(y=plant.usl[i], line=dict(color="#ef4444", width=1, dash="dot"), row=r, col=ci)

    # 같은 열(같은 종류의 조)은 y축 범위를 맞춤
    for ci, (tank, _, _) in enumerate(cols, start=1):
        ids = [plant.find(b, p, l, tank, prm) for l in LINES]
        lo = min(plant.V[i, -window:].min() for i in ids)
        hi = max(plant.V[i, -window:].max() for i in ids)
        if full:
            lo = min([lo] + [plant.lsl[i] for i in ids if not np.isnan(plant.lsl[i])])
            hi = max([hi] + [plant.usl[i] for i in ids])
        pad = (hi - lo) * 0.1 or 1
        fig.update_yaxes(range=[lo - pad, hi + pad], col=ci)
    fig.update_annotations(font_size=11)
    fig.update_xaxes(tickformat="%H:%M", showgrid=False)
    fig.update_layout(height=170 * nr + 50, margin=dict(l=8, r=8, t=28, b=8), hovermode="closest")
    st.plotly_chart(style(fig), width="stretch", key=f"cmp-{b}-{p}-{prm}-{window}-{full}", config={"displayModeBar": False})
    st.caption(
        "같은 열 = 같은 종류의 조라 y축을 맞췄어요. 한 줄(계열)이 다른 줄들과 다르게 움직이면 이상 후보예요. "
        "선 색 = 현재 상태(시안=정상) · 붉은 점선 = LSL/USL · 세로 음영: 파랑 Hold, 보라 σ 초과, 분홍 동료 대비 이탈"
    )


# ───────────────────────── 4. 경고 센터 ─────────────────────────
def alerts():
    plant, window = _ctx()
    _header("경고 센터", "사고(같은 계열·같은 조) 단위로 묶어서, 그래프와 함께 쭉 훑어보기")
    inc = incidents(plant, window)
    if not inc:
        st.success(f"최근 {st.session_state.get('range', '24시간')} 동안 경고가 없습니다.")
        return

    f = st.columns([2.6, 1, 1, 1.2], vertical_alignment="bottom")
    kinds = f[0].multiselect("경고 유형", list(KIND), default=list(KIND),
                             format_func=lambda k: f"{KIND[k]['icon']} {KIND[k]['label'].split('(')[0]}")
    bld = f[1].selectbox("건물", ["전체"] + BUILDINGS)
    prc = f[2].selectbox("공정", ["전체"] + PROCESSES)
    only_active = f[3].toggle("진행 중만", value=True)

    def keep(x):
        if bld != "전체" and x["bldg"] != bld:
            return False
        if prc != "전체" and x["proc"] != prc:
            return False
        if only_active and not x["active"]:
            return False
        return bool(set(x["ev"]["kind"]) & set(kinds))

    inc = [x for x in inc if keep(x)]
    if not inc:
        st.info("조건에 맞는 경고가 없습니다.")
        return
    n_act = sum(x["active"] for x in inc)
    st.caption(f"사고 {len(inc)}건 (진행 중 {n_act} · 해소 {len(inc) - n_act})  —  아래로 스크롤하며 확인하세요")
    _legend()

    shown = st.session_state.setdefault("_alert_n", 8)
    for x in inc[:shown]:
        ev = x["ev"]
        with st.container(border=True):
            top = st.columns([3, 2])
            tag = "진행 중" if x["active"] else "해소됨"
            top[0].markdown(
                f'#### <span style="color:{_color(x["rank"])}">●</span> {x["title"]}'
                f'<br><span style="font-size:13px;color:#94a3b8;font-weight:400">{x["what"]}  |  {tag}  |  '
                f'{x["first"]:%H:%M} → {x["last"]:%H:%M}</span>',
                unsafe_allow_html=True,
            )
            top[1].markdown(
                "<br>" + "&nbsp;&nbsp;".join(
                    f'<span style="color:{KIND[k]["color"]};font-weight:700">● {KIND[k]["label"].split("(")[0]}</span>'
                    for k in sorted(set(ev["kind"]), key=lambda k: KIND[k]["rank"])
                ),
                unsafe_allow_html=True,
            )
            _incident_charts(plant, x, window, "a")
    if shown < len(inc):
        if st.button(f"더 보기 ({len(inc) - shown}건 남음)"):
            st.session_state["_alert_n"] = shown + 8
            st.rerun()
````

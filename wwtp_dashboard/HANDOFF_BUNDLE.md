# 폐수처리 공정 품질 관제 대시보드 — 인수인계 문서

> 이 문서는 **사내 Claude(또는 담당자)가 맥락 없이 읽고 이어서 작업**할 수 있도록 쓴 문서입니다.
> 코드(`app.py`, `core.py`, `charts.py`, `views.py`)는 **데모 데이터로 이미 동작하는 완성형 프로토타입**입니다.
> 해야 할 일은 크게 두 가지입니다: ① **데이터 소스를 회사 서버로 교체**, ② **회사 실제 설비/규격에 맞게 설정값 수정**.
> 화면 구조와 감지 로직은 아래 "설계 결정" 이유가 있어서 이렇게 만들어졌으니, 이유 없이 바꾸지 마세요.

---

## 0. 현재 상태 한눈에 보기

| 항목 | 상태 |
|---|---|
| 데모 데이터로 4개 탭 동작 | ✅ 완료 (센서 960개, 5분 간격 8일치) |
| 감지 규칙 8종 + 사고 묶기 | ✅ 완료 (기본 5종 + 공정 연관 3종, 데모 기준 오탐 규칙별 하루 1건 이하) |
| **사내 데이터 연결** | ⬜ **미착수** — `core.get_plant()` 교체 필요 (4-2) |
| **실제 규격값(LSL/USL, σ 기준)** | ⬜ **미착수** — 현재 값은 전부 임의 placeholder (4-3) |
| 결측 / 점검 마스킹 / 기준선 롤링 | ⬜ 미구현 (4-4) |
| 5분 단위 실시간 갱신 | ⬜ 미구현 (4-4) |
| 사내망 반입 확인 (pip, 폰트) | ⬜ 확인 필요 (7번) |
| 전체 현황 디자인 (지시서 6-0) | ✅ 완료 — 요약 바 · 신호등 노드 · 이상점 캔버스 · 트렌드 4단, 클릭 연동 확인 |
| 다른 탭(공정 상세 · 한눈에 비교 · 경고 센터) 지시서 반영 | ⬜ 미착수 — 이전 HMI 개편 상태 그대로 (6-0 아래 '열린 결정') |

**다음에 할 일은 4번 순서대로.** 시작 전에 10번의 질문 목록을 사용자에게 물어볼 것. 화면 작업이 먼저라면 6-0 의 '열린 결정'부터 사용자에게 확인할 것.

## 1. 목적

폐수처리 공정의 **모든 센서 데이터에서 미세한 변동까지 조기 감지**하는 관제 대시보드.
- 단순히 규격(LSL/USL)을 벗어난 것뿐 아니라, **규격 안에서 이미 평소와 달라지고 있는 것**을 일찍 잡는 게 핵심.
- 센서가 수백 개라서 **한 개씩 클릭해서 보는 방식은 불가능**. "눈으로 훑어서 튀는 걸 찾는" 구조여야 함.

## 2. 설비 구조 (사용자가 알려준 내용)

- 건물 3개 (1동, 2동, 3동)
- 건물마다 공정 4개: **유기, 무기1, 무기2, 산폐수**
- 공정마다 **계열 4개** (A~D계열)
- **유기 계열** (흐름 순서): 전탈조 → 폭기조1~5 → 후탈조 → 재폭기조 → 침전조
  - 폭기조, 재폭기조: **DO, pH, 공기개도(%)**
  - 전탈조, 후탈조: **NO3-N, 외부탄소원 투입유량, 탄소원개도(%)**
  - 침전조: **SS, torque**
  - → 계열당 센서 26개
- **무기1 / 무기2 / 산폐수 계열** (반응조 3개는 직렬 1→2→3): 반응조1~3 → 응집조 → 침전조
  - 반응조: **pH, CaOH2·AFR·FR 투입 농도, CaOH2개도(%)**
  - 응집조: **Polymer 투입 농도**
  - 침전조: **F, SS**
  - → 계열당 센서 18개
- 전체: 유기 3동×4계열×26 = 312, 무기류 3공정×3동×4계열×18 = 648 → **960개**
- **약품 태그 이름 (사용자가 알려줌, 2026-11-04)**: `CaoH2_Concetraion`, `AFR_Concentration`, `FR_Concentraion`(약품), `Polymer_Concentration`(고분자). 유량이 아니라 **농도**. 철자는 사용자가 적은 그대로 — 실제 태그명과 대조 필요. 화면 이름은 CaOH2/AFR/FR/Polymer.
- ⚠ **데모 가정(실제 확인 필요)**: AFR·FR 이 어느 조에 들어가는지 모름 → 데모는 반응조1~3 모두에 3종을 둠. 개도 태그(공기개도, 탄소원개도, CaOH2개도)도 공정 연관 규칙 시연용으로 넣은 것이라 실제 태그가 있는지 확인할 것. 농도 단위(mg/L)도 가정.
- 사용자가 "공정이 훨씬 더 많다"고 했으므로 **구조는 반드시 설정(config) 기반**이어야 함 (`core.py`의 `PROCESSES`, `tanks_of()`, `STAGE_SPEC`).
- **데이터**: 서버에서 **5분 평균값이 5분마다 누적**됨. 실시간 갱신 필요.

## 3. 파일 구성

| 파일 | 역할 |
|---|---|
| `app.py` | 진입점. 상단 내비(탭), 헤더 바, 조회 구간 슬라이더, 전역 CSS(밝은 현장 모니터 테마) |
| `core.py` | **설비 구조, 규격, 데이터 생성/로딩, 이상 감지, 사고 묶기.** 데이터 교체는 여기서만 |
| `charts.py` | Plotly 차트 2종: `trend_figure`(전체 현황 ④ 트렌드 — 영역 차트 + 임계치 점선 + 빨강/노랑 음영 + 큰 붉은 점 + 경고 문구), `sensor_figure`(공정 상세·경고 센터 — 선 + 근접/이탈 가로 띠 + 경고 종류별 세로 음영 + 동료 범위) |
| `views.py` | 화면 4개. 전체 현황은 `_banner`(① 요약 바) · `_flow`(② 노드·화살표) · `_canvas`(③ 캔버스) · `_detail`(④ 트렌드), 선택 상태는 `st.session_state["ov_sel"]` 하나로 연동 |
| `.streamlit/config.toml` | 밝은 테마 + 사용 통계 전송 끄기. **폴더째 유지** |
| `requirements.txt` | streamlit, plotly, pandas, numpy |
| `CLAUDE.md` | 이 폴더에서 Claude를 시작하면 자동으로 이 문서를 읽게 하는 파일 + 작업 규칙 |
| `HANDOFF.md` | 이 문서 |
| `HANDOFF_BUNDLE.md` | 이 문서 + 코드 전체를 한 파일로 합친 것 (채팅창에 붙여넣기용). 코드가 바뀌면 낡으므로 **폴더 사용 시 무시** |

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
탭 4개(전체 현황 / 공정 상세 / 한눈에 비교 / 경고 센터)가 에러 없이 떠야 함.

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
| **VALVE 개도-투입 불일치** | 앞 7일로 계열·조마다 `투입 = a + b·개도` 를 맞추고, 잔차의 EWMA 가 ±5σ(MAD) 를 30분 넘게 벗어남. 개도·투입 센서 둘 다 표시. 막힘·펌프 정지(개도↑ 투입 그대로) / 누설(개도↓ 투입 그대로) | `VALVE_PAIRS`, `VALVE_K=5.0` |
| **AIR DO↓ 공기개도↑** | 2시간 기울기가 평소(앞 7일) 대비 DO 는 −2.5σ 아래, 공기개도는 +2.5σ 위로 30분 동시. 하락이 멈춰도 DO 가 평소보다 낮고 개도가 높은 동안은 유지. 산기관 막힘·부하 급증 | `AIR_PAIRS`, `AIR_N=24, AIR_K=2.5` |
| **RATIO 고분자 부족** | 같은 계열 약품(CaOH2·AFR·FR, 각자 평소 대비 배율의 평균) 대비 Polymer 비율(로그)이 평소(앞 7일)보다 5σ 낮게 30분. 반응조→응집조 10분 지연 반영. Polymer 센서에 표시 | `RATIO_RULES`, `RATIO_K=5.0, RATIO_LAG=2` |

### PEER (가장 중요 — 조기감지의 핵심)
같은 **건물·공정·조 종류·항목**의 센서들(예: 한 공정의 폭기조 20개의 DO)은 서로 비슷하게 움직여야 함. 한 센서가 **동료 중앙값에서 벌어지면** 규격 안이어도 이상으로 본다.
1. `d = 센서값 − 동료그룹 중앙값` (시간별)
2. `d`에서 **센서별 평소 평균(오프셋)을 뺀다** ← 빼먹으면 오탐 폭증
3. 평소 편차폭 `σ_d` = **MAD 기반 robust σ** (전체 기간, 이상치에 강함)
4. `d`의 **EWMA(α=0.2)** 가 `±5σ_d` 를 넘고, **6샘플(30분) 연속**이면 플래그 (구간 전체를 역채움)

튜닝 이력(데모, 센서 648개 기준): 오프셋 미제거 + 앞2일 표준편차 + 4σ → 하루 10건 이상 오탐 → 오프셋 제거 + MAD + 5σ → **하루 1건 수준**. 민감도를 올리고 싶으면 `PEER_K`를 낮추되 오탐을 반드시 같이 확인할 것.

### 공정 연관 규칙 (2026-11-04 사용자 요청으로 추가)
- 규칙은 코드가 아니라 **설정 표**(`VALVE_PAIRS`, `AIR_PAIRS`, `RATIO_RULES`)로 정의. (조 종류, 항목) 짝만 적으면 **같은 동·공정·계열·조 안의 태그끼리 자동으로 짝지어져** 전 계열에 적용됨. 센서마다 하나씩 넣지 않음.
- 평소 관계는 **앞 7일**(`BASE7_N`)로 학습 → 데모 기간을 8일로 늘린 이유.
- 순위(rank): 연관 규칙 3종은 원인을 더 구체적으로 짚으므로 **PEER 보다 앞**(칸 색·정렬에서 우선). SPEC > NEAR > HOLD > STD > VALVE > AIR > RATIO > PEER.
- 1·2단계 경고(고분자 부족만 = 주의, + 침전조 SS·F 상승 = 경고)는 제안만 했고 아직 묶지 않음. 지금은 두 사고가 따로 뜸.
- 사용자와 논의한 후속 후보(미구현): 개도 100%/0% 포화, 헌팅(5분 평균이라 빠른 헌팅은 안 보임 — 표준편차로 대체 가능), 설정값-측정값 차이, 약품 탱크 레벨, 데이터에서 관계를 찾아 제안하고 체크만 받는 방식, 7일 기준 표준편차·2시간 Hold·기울기(상한 도달 예상 시간).

### 사고(incident) 묶기
같은 **(건물, 공정, 계열, 조 종류)** 안의 경고는 **사고 1건**으로 묶는다. 예) 한 계열 폭기조 3개가 동시에 DO 저하 → 알람 3건이 아니라 사고 1건. (알람 피로 방지) — `core.incidents()`

## 6. 화면 구성과 설계 결정 (이유)

사용자가 직접 불만을 말해서 바뀐 부분이 많음. **되돌리지 말 것.**

### 6-0. 디자인 지시서 (2026-11-04 사용자, 화면 작업의 기준)
> 역할: 대규모 산업 공정·수처리 시설 모니터링의 수석 UI/UX 디자이너 겸 Streamlit/Plotly 개발자.
> 목표: **격자형 카드 나열 금지. 3초 안에 어떤 공정에 이상점이 생겼는지 즉시 알 수 있는 공정 흐름(Process Flow) 중심 대시보드.**
> 1. **공정 신호등 노드** — 공정 파이프라인 노드마다 Green/Yellow/Red. Red·Yellow 노드는 테두리·배경에 은은한 글로우 애니메이션.
> 2. **차트 이상점** — 임계치를 넘는 점은 Plotly 위 큰 붉은 점 + 상단 경고 텍스트 자동 표시. 정상 범위를 벗어난 구간은 배경 붉은 음영.
> 3. **이벤트 스택** — 화면 최상단에 해결이 시급한 주요 이상점 요약 바 (예: "🚨 [STAGE 03] 호기성 폭기조 DO 농도 급감 (1.2 mg/L) - 조치 필요"). 누르면 관련 차트·노드 연동.
> 4. **영향 화살표** — 앞 단계 공정에 이상이 생기면 다음 단계로 가는 화살표가 주황/빨강.
> 구조: Core = 이상 데이터가 든 시계열 생성 · Charts = 영역 차트 + 임계치 점선 + 이상점 마커 · Views = 메인 흐름 노드 → 이상점 요약 캔버스 → 공정 상세 트렌드 3단.
>
> 이 지시서 전에 시도한 것(사용자가 모두 반려): 밝은 운전 보드(표), HMI 패널 + 알람 기록, 디자인 캔버스 시안 5종(계통도·브리핑·규격 위치 띠·배치도·기록계).
>
> 신호등 기준(구현 결정): **빨강 = 조치 필요** = 스펙 이탈 · 개도-투입 불일치 · DO↓ 공기개도↑ · 고분자 부족 / **노랑 = 확인 필요** = 상하한 근접 · Hold · 표준편차 초과 · 동료 대비 이탈 (`core.KIND[...]["sev"]`). 노드·요약 바는 **지금 걸려 있는** 경고로 판단하고, 빨강이 하나라도 있으면 빨강(순위 숫자보다 우선).

1. **전체 현황** (2026-11-04 디자인 지시서 6-0 으로 다시 만듦) — 위에서 아래로 4단, 모두 같은 '선택'으로 연동:
   - ① **주요 이상점 요약 바**(이벤트 스택, 최대 5줄): 시급한 순(빨강 → 노랑, 같은 단계면 경고 순위 → 최근). 문장 = `[STAGE nn] 공정 조 · 동 계열 탱크 항목 현상 (현재값 단위) — 조치/확인 필요`. 빨강 바는 맥박처럼 빛남. **누르면** 그 사고가 선택됨.
   - ② **공정 흐름**: 공정(유기·무기1·무기2·산폐수)마다 한 줄, 조 종류 = 노드(STAGE 01…, 폭기조1~5·반응조1~3은 노드 하나). 노드 = 신호등(초록/노랑/빨강) + 이상 수/전체 + 대표 센서 현재값, 노랑·빨강은 글로우 애니메이션. 노드 사이 **영향 화살표**는 앞 노드가 노랑이면 주황, 빨강이면 빨강 + "영향". 오른쪽 위 동 필터(전체/1·2·3동). 노드를 **누르면** 그 노드가 선택됨.
   - ③ **이상점 요약 캔버스**(Plotly): 세로 = 이상이 있었던 공정·조(흐름 순서), 가로 = 조회 구간. 사고마다 지속 막대 + 지금 점(진행 중 = 큰 색 점, 해소 = 회색 빈 점). **점을 누르면**(`on_select`) 그 사고가 선택됨. 같은 줄의 사고는 높이를 나눠 겹치지 않게 함.
   - ④ **공정 상세 트렌드**: 선택된 사고(또는 노드)의 센서 최대 4개, `charts.trend_figure` — 영역 차트 + USL/LSL 점선 + 이상 구간 음영(빨강/노랑) + 임계치 밖 점 = 큰 붉은 점 + 위쪽 경고 문구.
   - 선택된 바·노드·캔버스 점은 검정 테두리로 함께 강조. 아무것도 안 눌렀으면 가장 시급한 사고가 선택된 상태.
   - 한계: Streamlit 이라 '주시(마우스 올림)'만으로는 연동 안 되고 클릭해야 함. 테스트 창에서 페이지를 새로 연 직후 캔버스 첫 클릭이 한 번 무시되는 현상을 봄(두 번째부터 정상) — 실제 브라우저에서 다시 확인 필요.
   - ❌ *예전 히트맵은 사용자가 "뭘 봐야 하는지 모르겠다"고 해서 제거함.* 색만 있고 값·규격·여유가 안 보였기 때문. 지금 화면은 노드에 대표 값, 트렌드에 규격선을 같이 보여 줌.
   - **열린 결정 (사용자 확인 필요, 2026-11-04 기준)**:
     1. 차트 통일 — 경고 센터·공정 상세 그래프도 `trend_figure`(영역 차트) 로 바꿀지, 화면마다 지금처럼 둘지. 바꾸면 모양은 통일되지만 경고 종류별 색 구분과 동료 범위 띠가 없어짐. 사용자가 "전체 현황 그래프 아래는 연한 파랑으로 채워져 있는데 경고 센터엔 없다"고 물어봐서 이 차이를 설명했고, 아직 답 없음.
     2. 신호등 기준 — 빨강/노랑 분류(6-0 끝)는 구현하며 정한 것. 사용자가 다르게 원하면 `core.KIND[...]["sev"]` 만 고치면 됨.
     3. 나머지 탭에 지시서(6-0) 적용 여부와 범위.
2. **공정 상세** — 계열 4개를 **공정 흐름 순서의 탱크**로 나열하고 탱크 사이를 **배관(→)**으로 이음(P&ID 처럼). 탱크 = 버튼(이름 + 항목별 현재값, 고정폭 숫자). 정상 탱크는 회색 테두리로 조용하게, 이상 탱크는 경고 색 테두리 + 왼쪽 굵은 띠 + 이상 항목만 굵은 경고 색. **이상 있는 조는 자동 펼침**, 탱크를 누르면 해당 계열 바로 아래에 센서 그래프 펼침/접힘. "이상 조 모두 펼치기/모두 접기" 버튼. 펼친 그래프 위에는 카드·metric 위젯 대신 한 줄 머리글(항목 · 큰 현재값 · 1시간 변화 · 상태, 아래 규격·σ·이력).
   - 처음엔 라디오로 조를 골라야 했는데 "클릭하기 힘들다"고 해서 박스 직접 클릭 + 자동 펼침으로 바꿈. 탱크를 버튼으로 둔 이유도 이것(HTML 그림은 클릭이 안 됨).
3. **한눈에 비교** — 항목 하나를 고르면 **계열 4 × 조 N개를 서브플롯 격자로 한 화면에** 보여줌(클릭 없이). 같은 열은 y축을 맞춰 혼자 튀는 센서가 눈에 띔. 선 색 = 현재 상태, 제목 옆 색 사각형 + 경고 이름. 기본 항목은 그래프가 가장 많은 항목.
   - 센서가 많아서 "하나씩 클릭"이 불가능하다는 요구에서 나온 핵심 페이지.
4. **경고 센터** — 위: **알람 타임라인**(사고마다 한 줄, 경고 종류별 색 막대로 언제부터 얼마나, 점선 = 지금). 아래: 사고별로 굵은 윗선 + 왼쪽 색 막대 머리(시각 · 위치 · 조/항목 · 진행 중/해소 · 경고 종류) 아래 센서 그래프(최대 3개)를 **쭉 나열하고 스크롤**(표에서 행을 클릭해야 그래프가 나오던 방식은 사용자가 싫어해서 변경, 카드 상자도 없앰). 유형/건물/공정/진행 중 필터, "더 보기".
5. **차트(`charts.py`)** — 지금 두 가지가 공존함(의도된 차이, 통일 여부는 위 1번 전체 현황의 열린 결정):
   - `trend_figure` (전체 현황 ④): 지시서대로 **영역 차트**(선 아래 연한 청록 채움) + USL/LSL 붉은 점선 + 이상 구간 세로 음영은 신호등 2색(빨강 = 조치 필요, 노랑 = 확인 필요) + 임계치 밖 점 = 큰 붉은 점 + 위쪽 경고 문구 + 동료 중앙값 점선.
   - `sensor_figure` (공정 상세·경고 센터): 선만(채움 없음) + USL/LSL 점선 + 근접(주황)/이탈(빨강) **가로 띠** + 이상 구간 세로 음영을 **경고 종류별 색**(Hold 파랑, σ 보라, 동료 이탈 분홍, 개도-투입 갈색 …) + **동료 범위(회색 띠)와 중앙값(점선)** + 작은 빨강/주황 점. 동료 범위가 있어야 "어디서 벌어졌는지" 보임. 가로 띠·회색 띠가 이미 깔려 있어 여기에 영역 채우기를 더하면 색이 겹침.
6. **디자인**: **밝은 현장 모니터 + HMI 패널 스타일**(2026-11-04 사용자 요청으로 다크 관제 테마에서 바꿈). 연회색 바탕, 직각·1px 선·그림자 없음, 헤더는 상자 없이 굵은 밑줄, 숫자는 고정폭 글꼴(D2Coding/Consolas, 사내 PC 기본 글꼴 — 외부 CDN 아님), 탭 아이콘은 Streamlit 내장 Material 아이콘(이모지 아님), 와이드 모니터용 최대 폭 1920px. 사이드바 없음, 상단 탭 + 헤더(진행 중 사고 건수). 사용자가 *"AI가 만들면 다 왼쪽 회색 사이드바에 똑같다"* 고 불평해서 일반 Streamlit 기본 모양을 피함. 테마는 `.streamlit/config.toml`, 화면 CSS는 `app.py`의 `CSS`, 차트는 `charts.style()`.
7. 색상 의미 고정: 빨강 스펙 이탈 / 주황 근접 / 파랑 Hold / 보라 σ 초과 / 분홍 동료 이탈 / 갈색 개도-투입 불일치 / 하늘색 DO↓ 공기개도↑ / 남색 고분자 부족 / 초록 정상 / 회색 해소. (색은 `core.KIND` 하나에서만 정의 — 보드 칸·차트 음영이 여기서 가져감)
8. **템플릿 금지 원칙** (2026-11-04 사용자 지시, 모든 화면에 적용): 카드·KPI 타일 네모칸 나열, 둥근 모서리+그림자, 그라데이션, 이모지 아이콘 남발, 똑같은 너비 그리드 금지. 현장 HMI·계장 도면처럼 선·글자 크기·공정 흐름으로 구분하고, 정상은 조용하게·이상만 강하게. 4개 탭 모두 적용함(전체 현황은 이후 6-0 지시서로 다시 만듦, 공정 상세 배관 흐름도, 경고 센터 타임라인, 한눈에 비교 이모지 제거). `core.KIND` 의 `icon`(이모지)은 이제 화면에서 쓰지 않음.

## 7. 사내망 환경 주의

- 사내에서는 **외부 GitHub, 외부 Claude 사용 불가**. 외부 CDN/API 호출이 있으면 안 됨.
- 현재 코드의 외부 의존은 `app.py` CSS의 **Google Fonts `@import`(Orbitron)** 하나뿐. 차단돼도 기본 폰트로 대체되어 동작하지만, 깔끔하게 하려면 폰트 파일을 사내에 넣어 로컬로 불러오거나 `@import`를 제거.
- Streamlit/Plotly는 프론트 리소스를 패키지에 포함하므로 CDN 없이 동작. **`pip install`만 사내 PyPI/오프라인 휠로 해결**하면 됨.
- 사내 데이터를 외부로 보내는 코드(외부 API, CDN, 텔레메트리) 금지. Streamlit 사용 통계 전송은 `.streamlit/config.toml`의 `gatherUsageStats = false`로 **이미 꺼져 있음** — `.streamlit` 폴더를 빼먹지 말 것.

## 8. 검증 방법

- **오탐 확인**: 감지 로직을 건드릴 때마다, 평소(이상 없는) 구간에서 경고가 몇 개 걸리는지 먼저 세어 볼 것. (데모에서는 `get_plant.__wrapped__()`로 직접 호출해 `core.events()`로 확인했음.)
- 데모 모드에서 `ANOMALIES`에 심은 이상이 의도한 유형으로 잡히는지 확인:
  스펙 이탈(2동 유기A 폭기조1·2·3 DO 동시 저하→사고 1건으로 묶임, 2동 무기1 B 반응조2 pH), Hold 3건, σ 1건, **PEER 전용 2건(1동 유기C 폭기조2 DO, 3동 무기2 A 반응조1 AFR — 규격 안이라 임계값으로는 안 잡힘)**, 과거 해소 1건,
  **VALVE**(1동 무기1 A 반응조2: CaOH2개도↑ 투입↓ = 소석회 막힘. 3동 유기A 후탈조 외부탄소원 감소도 개도 변화 없이 줄어서 VALVE 로도 잡힘),
  **AIR**(3동 유기B 폭기조3 DO↓ 공기개도↑), **RATIO**(2동 무기2 D: AFR·FR 50%↑, Polymer 그대로 → 고분자 부족, 뒤이어 침전조 SS↑).
- 2026-11-04 측정(심지 않은 센서 기준): 앞 7일 하루 평균 NEAR 1.1 · PEER 0.3 · 나머지 0. 최근 1일 VALVE·AIR·PEER 각 1건(VALVE·AIR 는 짝 센서 쪽이 같이 표시된 것. AIR 1건은 2동 유기A 폭기조3 DO 급락 때 공기개도가 우연히 같이 올라 걸린 것).
- 화면 확인: 4개 탭 모두 예외 없이 렌더링, 전체 현황: 요약 바·노드·캔버스 점을 각각 눌러 노드 강조와 ④ 트렌드가 같은 사고로 바뀌는지, 노드 신호등이 지금 경고 기준과 맞는지, 탱크 클릭 → 그래프 펼침/접힘, 경고 센터 타임라인 막대 = 사고 목록과 같은 건수.

## 9. 작업 원칙 (사내 Claude에게)

1. **먼저 이 문서를 끝까지 읽고**, 데모를 실행해서 현재 동작을 눈으로 확인한 뒤 수정할 것.
2. 데이터 소스, 태그 매핑, 규격값은 **모르면 사용자에게 질문**. 임의로 지어내지 말 것.
3. 한 번에 다 바꾸지 말고 **① 데이터 연결 → ② 규격/설정 교체 → ③ 오탐 점검 → ④ 화면 미세 조정** 순서로, 단계마다 동작 확인.
4. 화면/감지 규칙을 바꿔야 할 때는 **바꾸는 이유와 영향**을 먼저 사용자에게 설명.
5. 센서가 늘어도 깨지지 않도록 구조는 설정 기반 유지 (하드코딩 금지).

## 10. 사용자에게 먼저 물어볼 질문 목록 (모르는 것들)

1. **데이터 소스**: DB/히스토리안 종류(Oracle, MSSQL, PostgreSQL, PI 등), 접속 방식, 읽기 전용 계정 여부, 테이블/뷰 구조
2. **센서 태그**: 태그 이름 규칙, 태그 → (건물, 공정, 계열, 조, 항목) 매핑표가 있는지
3. **시간**: 5분 평균의 타임스탬프 기준(구간 시작/끝), 타임존, 수집 지연(몇 분 늦게 들어오는지)
4. **결측 표기**: NULL인지 특수값(-999 등)인지, 품질 코드가 있는지
5. **실제 규격**: 항목별 LSL/USL, 이동표준편차 경고 기준, 건물/계열마다 다른지
6. **점검/교정 중 표시**를 알 수 있는 신호가 있는지 (알람 억제용)
7. **설비 구조 차이**: 이 문서(2번)와 실제가 다른 곳 (조 개수, 센서 종류, 흐름 순서)
8. **배포**: 어느 서버에서 실행하는지, 접속 주소/포트, 동시 사용자 수, 로그인/권한 필요 여부
9. **보관/갱신**: 화면에서 며칠 치를 볼지, 몇 분마다 새로고침할지

## 11. 알려진 한계 / 미구현

- PEER 오탐: 데모에서 **하루 1건 이하** 남아 있음. 실데이터에서는 더 달라질 수 있으므로 반드시 실측 후 `PEER_K`, `PEER_PERSIST` 재조정.
- 동료 그룹이 작은 항목(전탈조/후탈조처럼 같은 공정 안에 4개뿐)은 중앙값이 불안정함. 한 센서가 크게 벗어나면 중앙값도 같이 흔들림.
- PEER 기준선이 **고정 기간(앞 2일)** 기반. 롤링 갱신 미구현.
- 데이터를 **전부 메모리에 올리는 구조**. 센서가 수천 개 이상이 되면 DB/배치로 감지를 옮겨야 함.
- 한눈에 비교는 **건물 1개 × 공정 1개** 단위. 전 건물 동시 비교, **자동 순회 모드**(관제실 모니터용)는 제안만 했고 미구현.
- Google Fonts(Orbitron) 외부 의존 1건 (막혀도 기본 폰트로 동작).
- 전체 현황 연동은 클릭으로만 됨(Streamlit 은 마우스 올림 이벤트를 서버로 보내지 않음). 캔버스 점 첫 클릭이 한 번 무시되는 현상을 테스트 창에서 봄 — 실제 브라우저 재확인 필요.
- `STAGE_SPEC`의 규격, `ANOMALIES`는 **데모용 가짜 값**. 새 개도 태그·약품 농도 단위·AFR/FR 투입 위치도 데모 가정.
- 연관 규칙의 평소 관계(앞 7일)는 **고정 기간**. 실데이터에서는 PEER 와 같이 롤링 갱신 필요. 이상이 섞인 기간으로 학습하면 그 관계가 '정상'이 되므로 경고 구간은 빼고 학습할 것.
- 데모의 관계는 단순(투입 = 개도 비례, 고분자 = 약품 10분 지연 비례). 실제 공정은 지연·비선형이 더 클 수 있어 `VALVE_K`, `RATIO_K`, `RATIO_LAG`, `AIR_K` 를 실측으로 재조정해야 함.

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
base = "light"
primaryColor = "#0e7490"
backgroundColor = "#eef2f6"
secondaryBackgroundColor = "#ffffff"
textColor = "#0f172a"
borderColor = "#cbd5e1"

[client]
toolbarMode = "minimal"

[browser]
gatherUsageStats = false
````

## 파일: `app.py`

````python
"""폐수처리 공정 품질 현황 대시보드 (데모 데이터, 센서 약 960개).

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

/* 템플릿 금지: 둥근 카드·그림자·타일 대신 현장 HMI 패널처럼 선과 글자 크기로 구분 */
:root { --mono: 'D2Coding', 'Consolas', 'Menlo', monospace; --ink:#0f172a; --rule:#1e293b; --mute:#64748b; }

/* 사이드바 제거 → 상단 내비 + 헤더 바. 현장 모니터(와이드)에 맞춰 폭을 넓게 */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }
.block-container { padding-top: 4.5rem; max-width: 1920px; }

/* 헤더: 상자 없이 굵은 밑줄 하나 */
.wwtp-bar { display:flex; align-items:center; gap:14px; padding:2px 0 8px; margin-bottom:4px; border-bottom:3px solid var(--rule); }
.wwtp-mark { font-family:var(--mono); font-weight:800; font-size:13px; letter-spacing:.1em; color:#fff; background:var(--rule); padding:7px 9px; }
.wwtp-title { font-weight:800; letter-spacing:.06em; color:var(--ink); font-size:15px; line-height:1.2; }
.wwtp-sub { color:var(--mute); font-size:11px; }
.wwtp-live { font-family:var(--mono); font-size:10px; padding:1px 6px; color:#0e7490; border:1px solid #0e7490; margin-left:8px; }
.wwtp-pill { margin-left:auto; padding:6px 14px; font-size:13px; font-weight:800; font-family:var(--mono); letter-spacing:.04em; }
.wwtp-pill.bad { color:#fff; background:#dc2626; animation: glow 1.6s infinite; }
.wwtp-pill.ok { color:#fff; background:#16a34a; }
@keyframes glow { 0%,100% { box-shadow:0 0 0 0 rgba(220,38,38,.55);} 50% { box-shadow:0 0 0 5px rgba(220,38,38,0);} }

/* 테두리 컨테이너·펼침 상자: 직각, 그림자 없음 */
div[data-testid="stVerticalBlockBorderWrapper"] { background:#ffffff; border:1px solid #cbd5e1 !important; border-radius:0 !important; box-shadow:none; }
[data-testid="stExpander"] details { border-radius:0 !important; border-color:#cbd5e1 !important; background:#ffffff; }

/* 숫자는 계기판 폰트 */
[data-testid="stMetricValue"] { font-family:'Orbitron',sans-serif; color:#0e7490; font-weight:700; }
[data-testid="stMetricLabel"] { color:#475569; }
h3 { letter-spacing:.02em; }
.sec { font-weight:800; font-size:13px; letter-spacing:.08em; color:var(--ink); border-bottom:2px solid var(--rule);
  margin:18px 0 6px; padding-bottom:3px; display:flex; justify-content:space-between; align-items:baseline; }
.sec span { font-weight:400; letter-spacing:0; color:var(--mute); font-size:12px; }

/* 전체 현황 ① 주요 이상점 요약 바 (색·깜빡임은 views._banner 가 바마다 넣음) */
[class*="st-key-bn-"] button { justify-content:flex-start; border:0 !important; border-radius:0 !important; padding:8px 14px !important;
  min-height:0; height:auto; }
[class*="st-key-bn-"] button div { width:100%; justify-content:flex-start; text-align:left; }
[class*="st-key-bn-"] button p { font-size:14px; font-weight:700; text-align:left; color:#ffffff; margin:0; }
[class*="st-key-bn-"] button:hover { filter:brightness(1.08); }
.st-key-bn-0 button { padding:13px 16px !important; }
.st-key-bn-0 button p { font-size:17px; font-weight:800; }
.ok-bar { background:#16a34a; color:#fff; font-weight:800; padding:12px 16px; }
@keyframes pulseR { 0%,100% { box-shadow:0 0 0 0 rgba(220,38,38,0); } 50% { box-shadow:0 0 16px 2px rgba(220,38,38,.55); } }

/* 전체 현황 ② 공정 흐름 노드(신호등 + 글로우) + 영향 화살표 */
[class*="st-key-fn-"] button { height:auto; min-height:0; padding:8px 10px; justify-content:flex-start; border-radius:6px !important; }
[class*="st-key-fn-"] button p { font-size:12px; line-height:1.45; text-align:left; margin:0; color:#475569; }
[class*="st-key-fn-"] button em { font-style:normal; font-weight:800; font-size:13px; color:var(--ink); }
[class*="st-key-fn-"] button strong { font-weight:800; }
@keyframes glowR { 0%,100% { box-shadow:0 0 4px 0 rgba(220,38,38,.25); } 50% { box-shadow:0 0 18px 4px rgba(220,38,38,.5); } }
@keyframes glowY { 0%,100% { box-shadow:0 0 3px 0 rgba(245,158,11,.25); } 50% { box-shadow:0 0 16px 3px rgba(245,158,11,.5); } }
.ln2 { font-weight:800; font-size:16px; color:var(--ink); line-height:1.2; }
.ln2 small { display:block; font-size:11.5px; font-weight:700; margin-top:2px; }
.fa { position:relative; height:40px; }
.fa i { position:absolute; left:0; right:11px; top:24px; height:4px; background:var(--c); }
.fa i::after { content:""; position:absolute; right:-11px; top:-6px; border-left:12px solid var(--c);
  border-top:8px solid transparent; border-bottom:8px solid transparent; }
.fa b { position:absolute; left:0; right:0; top:4px; text-align:center; font-size:10.5px; color:var(--c); }

/* 공정 상세: 계열 머리 + 탱크(버튼) + 탱크 사이 배관 */
.lh { display:flex; gap:12px; align-items:center; margin:16px 0 6px; font-size:13px; font-weight:700;
  border-bottom:1px solid #94a3b8; padding-bottom:4px; }
.lh b { background:var(--rule); color:#fff; font-family:var(--mono); padding:2px 9px; font-size:13px; }
[class*="st-key-nd-"] { position:relative; }
[class*="st-key-nd-"]::after { content:""; position:absolute; top:50%; right:-1rem; width:1rem; height:3px;
  background:#475569; transform:translateY(-50%); }
[class*="st-key-nd-"]::before { content:""; position:absolute; top:50%; right:-1rem; transform:translateY(-50%);
  border-left:8px solid #475569; border-top:6px solid transparent; border-bottom:6px solid transparent; z-index:1; }
[class*="st-key-nd-"] button { height:auto; min-height:0; padding:6px 10px; justify-content:flex-start; background:#ffffff;
  border-radius:0 !important; box-shadow:none !important; }
[class*="st-key-nd-"] button:hover { background:#f1f5f9; }
[class*="st-key-nd-"] button p { font-size:12px; line-height:1.5; text-align:left; margin:0; font-family:var(--mono); color:var(--mute); }
[class*="st-key-nd-"] button em { font-style:normal; font-family:'Malgun Gothic',sans-serif; font-weight:800; font-size:13px; color:var(--ink); }
[class*="st-key-nd-"] button strong { font-weight:800; }
.xh { margin:8px 0 2px; font-size:13px; color:var(--mute); border-left:4px solid #0e7490; padding-left:8px; }
.xh b { color:var(--ink); }

/* 센서 머리글 (카드·metric 위젯 대신 선 하나) */
.sh { border-top:2px solid var(--rule); padding:4px 0 0; display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 10px; }
.sh .p { font-weight:800; font-size:13px; color:var(--ink); }
.sh .v { font-family:var(--mono); font-size:24px; font-weight:700; line-height:1.1; }
.sh .u { color:var(--mute); font-size:12px; margin-left:-6px; }
.sh .dl { font-family:var(--mono); color:var(--mute); font-size:12px; }
.sh .s { margin-left:auto; font-size:12.5px; font-weight:800; }
.sh .x { flex-basis:100%; font-size:11.5px; color:var(--mute); }

/* 경고 센터: 사고 머리 (카드 대신 왼쪽 색 막대 + 굵은 윗선) */
.ih { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 14px; margin:18px 0 6px; padding:6px 10px;
  border-top:2px solid var(--rule); border-left:6px solid var(--c); background:#ffffff; font-size:13px; }
.ih .t { font-family:var(--mono); font-weight:700; color:var(--ink); }
.ih b { font-size:15px; color:var(--ink); }
.ih .w { color:#475569; }
.ih .g { font-family:var(--mono); font-size:11px; padding:1px 6px; border:1px solid currentColor; color:var(--c); }
.ih .ks { margin-left:auto; font-weight:800; }
</style>
"""

pages = {
    "overview": st.Page(views.overview, title="전체 현황", icon=":material/monitor_heart:", default=True),
    "process": st.Page(views.process, title="공정 상세", icon=":material/account_tree:", url_path="process"),
    "compare": st.Page(views.compare, title="한눈에 비교", icon=":material/grid_view:", url_path="compare"),
    "alerts": st.Page(views.alerts, title="경고 센터", icon=":material/notifications:", url_path="alerts"),
}
st.session_state["_pages"] = pages
nav = st.navigation(list(pages.values()), position="top")

st.markdown(CSS, unsafe_allow_html=True)

plant = get_plant()
n_inc = sum(x["active"] for x in incidents(plant, RANGES[st.session_state.get("range", "24시간")]))
pill = (
    f'<span class="wwtp-pill bad">진행 중 사고 {n_inc}</span>'
    if n_inc
    else '<span class="wwtp-pill ok">전 센서 정상</span>'
)
bar, ctl = st.columns([3.2, 1.4], vertical_alignment="center")
bar.markdown(
    f"""<div class="wwtp-bar"><div class="wwtp-mark">WWTP</div>
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
            "- **동료 대비 이탈** 같은 공정·같은 항목 센서들의 중앙값과 5σ 이상 벌어져 30분 지속 (규격 안이어도 감지)\n"
            "- **개도-투입 불일치** 개도에 비해 투입량·농도가 평소(앞 7일) 관계에서 5σ 이상 벗어나 30분 지속 (막힘·펌프 정지·누설)\n"
            "- **DO↓ 공기개도↑** 2시간 동안 DO 는 떨어지고 공기 밸브는 열리는 게 평소보다 뚜렷하게 30분 지속 (산기관 막힘·부하 급증)\n"
            "- **고분자 부족** 같은 계열 약품(CaOH2·AFR·FR) 투입 대비 Polymer 비율이 평소보다 5σ 낮게 30분 지속"
        )
        if st.button("데모 데이터 새로 만들기", width="stretch"):
            st.cache_resource.clear()
            st.rerun()

nav.run()
````

## 파일: `core.py`

````python
"""공정 구조 / 규격 / 데모 데이터 / 이상 감지 (센서 약 960개, 5분 간격).

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
            [("전탈조", "전탈조", ["NO3-N", "외부탄소원", "탄소원개도"])]
            + [(f"폭기조{i}", "폭기조", ["DO", "pH", "공기개도"]) for i in range(1, 6)]
            + [("후탈조", "후탈조", ["NO3-N", "외부탄소원", "탄소원개도"]),
               ("재폭기조", "재폭기조", ["DO", "pH", "공기개도"]),
               ("침전조", "유기침전조", ["SS", "torque"])]
        )
    # 약품 농도 태그: CaOH2 = CaoH2_Concetraion, AFR = AFR_Concentration, FR = FR_Concentraion, Polymer = Polymer_Concentration
    # (투입 위치는 데모 가정: 반응조마다 3종 모두. 실제 위치가 다르면 여기만 고치면 됨)
    return (
        [(f"반응조{i}", "반응조", ["pH", "CaOH2", "AFR", "FR", "CaOH2개도"]) for i in range(1, 4)]
        + [("응집조", "응집조", ["Polymer"]), ("침전조", "무기침전조", ["F", "SS"])]
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
    ("반응조", "CaOH2"):    dict(unit="mg/L", lsl=150.0, usl=700.0, base=400.0, sigma=30.0, std_limit=70.0, dec=1),
    ("반응조", "AFR"):      dict(unit="mg/L", lsl=20.0, usl=120.0, base=60.0, sigma=5.0, std_limit=12.0, dec=1),
    ("반응조", "FR"):       dict(unit="mg/L", lsl=5.0, usl=50.0, base=25.0, sigma=2.5, std_limit=6.0, dec=1),
    ("응집조", "Polymer"):  dict(unit="mg/L", lsl=1.0, usl=6.0, base=3.0, sigma=0.2, std_limit=0.5, dec=2),
    # 개도(%) — 하한/상한 근처면 근접 경고 = 밸브가 끝까지 붙은 상태(제어 여유 없음)
    ("폭기조", "공기개도"):   dict(unit="%", lsl=5.0, usl=95.0, base=50.0, sigma=5.0, std_limit=10.0, dec=1),
    ("재폭기조", "공기개도"): dict(unit="%", lsl=5.0, usl=95.0, base=40.0, sigma=5.0, std_limit=10.0, dec=1),
    ("전탈조", "탄소원개도"): dict(unit="%", lsl=5.0, usl=95.0, base=45.0, sigma=4.0, std_limit=8.0, dec=1),
    ("후탈조", "탄소원개도"): dict(unit="%", lsl=5.0, usl=95.0, base=35.0, sigma=4.0, std_limit=8.0, dec=1),
    ("반응조", "CaOH2개도"):  dict(unit="%", lsl=5.0, usl=95.0, base=50.0, sigma=4.0, std_limit=8.0, dec=1),
    ("무기침전조", "F"):     dict(unit="ppm", lsl=NAN, usl=15.0, base=6.0, sigma=1.0, std_limit=2.5, dec=2),
    ("무기침전조", "SS"):    dict(unit="mg/L", lsl=NAN, usl=30.0, base=9.0, sigma=1.5, std_limit=4.0, dec=1),
}

# ─────────────────────────────────────────────────────────────
# 2. 감지 규칙 (5분 간격 기준)
# ─────────────────────────────────────────────────────────────
STEP_MIN = 5
PER_DAY = 24 * 60 // STEP_MIN        # 288
N_PTS = 8 * PER_DAY                   # 데모: 8일치 (7일 기준 + 최근 1일)
BASE_N = 2 * PER_DAY                  # 앞 2일 = 평소 기준(동료 편차 기준 산정용)
BASE7_N = 7 * PER_DAY                 # 앞 7일 = 평소 관계 기준(개도-투입, 투입 비율)

NEAR_RATIO = 0.10                     # 규격폭 10% 이내 → 근접
HOLD_N = 12                           # 12개(=1시간) 연속 같은 값 → Hold
STD_N = 12                            # 이동 표준편차 윈도우 = 1시간
PEER_ALPHA, PEER_K, PEER_PERSIST = 0.2, 5.0, 6   # 동료 대비 편차: EWMA, 5σ, 30분 지속

# 공정 연관 규칙 — (조 종류, 항목) 짝을 설정으로. 같은 동·공정·계열·조 안의 태그끼리 자동으로 짝지어짐
VALVE_PAIRS = [                       # (조 종류, 개도 항목, 투입 항목): 개도에 비해 투입이 평소와 다름
    ("전탈조", "탄소원개도", "외부탄소원"),
    ("후탈조", "탄소원개도", "외부탄소원"),
    ("반응조", "CaOH2개도", "CaOH2"),
]
VALVE_K = 5.0                         # 평소 관계(7일 회귀)에서 벗어난 정도, EWMA 기준 5σ
AIR_PAIRS = [("폭기조", "DO", "공기개도"), ("재폭기조", "DO", "공기개도")]   # (조 종류, DO, 공기 개도)
AIR_N, AIR_K = 24, 2.5                # 2시간 기울기: DO 는 평소보다 2.5σ 넘게 하락, 개도는 2.5σ 넘게 상승 (1시간은 흔들림이 커서 서서히 오는 막힘을 놓침)
RATIO_RULES = [                       # 약품 투입이 늘었는데 고분자가 따라가지 않음 (같은 계열 안)
    dict(dose_stage="반응조", dose=["CaOH2", "AFR", "FR"], target_stage="응집조", target="Polymer"),
]
RATIO_K, RATIO_LAG = 5.0, 2           # 고분자 ÷ 약품 비율이 평소보다 5σ 낮음, 반응조→응집조 10분 지연

# sev: 신호등 단계 — red = 조치 필요(규격 이탈·설비/공정 이상), yellow = 확인 필요(근접·센서 이상 의심·조기경보)
KIND = {
    "SPEC": dict(label="스펙 이탈", color="#ef4444", icon="🔴", rank=0, sev="red"),
    "NEAR": dict(label="상하한 근접", color="#f97316", icon="🟠", rank=1, sev="yellow"),
    "HOLD": dict(label="1시간 Hold", color="#3b82f6", icon="🔵", rank=2, sev="yellow"),
    "STD":  dict(label="표준편차 초과", color="#a855f7", icon="🟣", rank=3, sev="yellow"),
    # 공정 연관 규칙은 원인을 더 구체적으로 짚으므로 동료 대비 이탈보다 앞 순위(칸 색·정렬 우선)
    "VALVE": dict(label="개도-투입 불일치", color="#92400e", icon="🟤", rank=4, sev="red"),
    "AIR":  dict(label="DO↓ 공기개도↑", color="#0891b2", icon="💨", rank=5, sev="red"),
    "RATIO": dict(label="고분자 부족(투입 비율)", color="#4f46e5", icon="⚗️", rank=6, sev="red"),
    "PEER": dict(label="동료 대비 이탈(조기경보)", color="#ec4899", icon="🩷", rank=7, sev="yellow"),
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
    ("3동", "무기2", "C계열", "응집조", "Polymer"): ("hold", 24, None, 0),
    ("2동", "유기", "B계열", "폭기조4", "pH"): ("noisy", 24, 0.45, 0),          # 변동성 증가
    # ↓ 규격 안이라 임계값으로는 안 잡히고, 동료와 비교해야 보이는 미세 변동
    ("1동", "유기", "C계열", "폭기조2", "DO"): ("ramp", 72, 0.7, 0),
    ("3동", "무기2", "A계열", "반응조1", "AFR"): ("ramp", 90, 15.0, 0),
    ("3동", "유기", "A계열", "후탈조", "외부탄소원"): ("ramp", 60, -7.0, 0),
    # 과거에 있었다가 해소된 이탈
    ("1동", "무기1", "D계열", "침전조", "F"): ("bump", 36, 9.8, 60),
    # ↓ 공정 연관 규칙
    # 소석회 배관 막힘: 개도는 계속 열리는데 투입 농도는 오히려 떨어짐 → 개도-투입 불일치
    ("1동", "무기1", "A계열", "반응조2", "CaOH2개도"): ("ramp", 60, 30.0, 0),
    ("1동", "무기1", "A계열", "반응조2", "CaOH2"): ("ramp", 60, -50.0, 0),
    # 산기관 막힘: DO 는 떨어지고 공기 밸브는 계속 열림 → DO↓ 공기개도↑
    ("3동", "유기", "B계열", "폭기조3", "DO"): ("ramp", 48, -1.5, 0),
    ("3동", "유기", "B계열", "폭기조3", "공기개도"): ("ramp", 48, 30.0, 0),
    # 약품(AFR·FR) 투입 50% 증가, 고분자는 그대로 → 고분자 부족, 뒤따라 침전조 SS 상승
    **{("2동", "무기2", "D계열", f"반응조{i}", prm): ("ramp", 72, arg, 0)
       for i in range(1, 4) for prm, arg in (("AFR", 30.0), ("FR", 12.5))},
    ("2동", "무기2", "D계열", "침전조", "SS"): ("ramp", 30, 7.0, 0),
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


def _pairs(meta: pd.DataFrame, stage: str, pa: str, pb: str) -> tuple[np.ndarray, np.ndarray]:
    """같은 동·공정·계열·조 안의 (항목 pa, 항목 pb) 센서 번호 짝."""
    key = ["bldg", "proc", "line", "tank"]
    a = meta[(meta.stage == stage) & (meta.param == pa)].reset_index()
    b = meta[(meta.stage == stage) & (meta.param == pb)].reset_index()
    m = a.merge(b, on=key, suffixes=("_a", "_b"))
    return m["index_a"].to_numpy(), m["index_b"].to_numpy()


def _ratio_groups(meta: pd.DataFrame, rule: dict) -> list[tuple[np.ndarray, int]]:
    """계열마다 (약품 센서들, 고분자 센서) — 약품 조와 고분자 조가 둘 다 있는 계열만."""
    out = []
    dose = meta[(meta.stage == rule["dose_stage"]) & meta.param.isin(rule["dose"])]
    tgt = meta[(meta.stage == rule["target_stage"]) & (meta.param == rule["target"])]
    for (b, p, l), g in dose.groupby(["bldg", "proc", "line"], sort=False):
        t = tgt.index[(tgt.bldg == b) & (tgt.proc == p) & (tgt.line == l)]
        if len(t):
            out.append((g.index.to_numpy(), int(t[0])))
    return out


def _ewm(x: np.ndarray) -> np.ndarray:
    return pd.DataFrame(x.T).ewm(alpha=PEER_ALPHA, adjust=False).mean().to_numpy().T


def _robust_z(x: np.ndarray, n: int) -> np.ndarray:
    """앞 n 샘플(평소)의 중앙값·MAD 로 표준화."""
    base = x[:, :n]
    med = np.nanmedian(base, axis=1, keepdims=True)
    sd = np.maximum(1.4826 * np.nanmedian(np.abs(base - med), axis=1, keepdims=True), 1e-9)
    return (x - med) / sd


def _slope(x: np.ndarray, n: int) -> np.ndarray:
    """최근 n 샘플 직선 기울기(샘플당). 앞쪽 n-1 개는 0."""
    w = np.arange(n) - (n - 1) / 2
    w = w / (w ** 2).sum()
    out = np.zeros_like(x)
    out[:, n - 1:] = np.lib.stride_tricks.sliding_window_view(x, n, axis=1) @ w
    return out


def _lag(x: np.ndarray, k: int) -> np.ndarray:
    out = np.roll(x, k, axis=-1)
    out[..., :k] = x[..., :1]
    return out


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
    # 평소 관계: 투입량은 개도를 따라가고, 고분자는 같은 계열 약품 투입을 10분 늦게 따라감
    for stage, pv, pf in VALVE_PAIRS:
        iv, jf = _pairs(meta, stage, pv, pf)
        V[jf] = mu[jf, None] * V[iv] / mu[iv, None] + 0.5 * idio[jf]
    for rule in RATIO_RULES:
        for ids, t in _ratio_groups(meta, rule):
            C = (V[ids] / mu[ids, None]).mean(axis=0)
            V[t] = mu[t] * _lag(C, RATIO_LAG) + 0.5 * idio[t]

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

    # 개도-투입 불일치: 앞 7일로 '투입 = a + b·개도' 를 계열·조마다 맞추고, 그 관계에서 벗어나면 (개도·투입 둘 다 표시)
    valve = np.zeros_like(spec)
    for stage, pv, pf in VALVE_PAIRS:
        iv, jf = _pairs(meta, stage, pv, pf)
        X, Y = V[iv], V[jf]
        xb, yb = X[:, :BASE7_N], Y[:, :BASE7_N]
        b = ((xb - xb.mean(1, keepdims=True)) * (yb - yb.mean(1, keepdims=True))).sum(1) / \
            np.maximum(((xb - xb.mean(1, keepdims=True)) ** 2).sum(1), 1e-9)
        a = yb.mean(1) - b * xb.mean(1)
        r = _robust_z(Y - (a[:, None] + b[:, None] * X), BASE7_N)
        f = _persist_backfill(np.abs(_ewm(r)) > VALVE_K, PEER_PERSIST)
        valve[iv] |= f
        valve[jf] |= f

    # DO↓ 공기개도↑: 2시간 기울기가 평소(앞 7일) 대비 DO 는 크게 하락, 개도는 크게 상승을 30분 이상 동시에
    air = np.zeros_like(spec)
    for stage, pdo, pv in AIR_PAIRS:
        ido, iv = _pairs(meta, stage, pdo, pv)
        zdo = _robust_z(_slope(V[ido], AIR_N), BASE7_N)
        zv = _robust_z(_slope(V[iv], AIR_N), BASE7_N)
        f = _persist_backfill((zdo < -AIR_K) & (zv > AIR_K), PEER_PERSIST)
        # 하락이 멈춰도 DO 가 평소보다 낮고 개도가 평소보다 열린 상태면 경고 유지
        low = (_robust_z(V[ido], BASE7_N) < -AIR_K) & (_robust_z(V[iv], BASE7_N) > AIR_K)
        for t in range(1, T):
            f[:, t] |= f[:, t - 1] & low[:, t]
        air[ido] |= f
        air[iv] |= f

    # 고분자 부족: 같은 계열 약품 투입(평소 대비 배율 평균) 대비 고분자 비율이 평소보다 낮음 (고분자 센서에 표시)
    ratio = np.zeros_like(spec)
    for rule in RATIO_RULES:
        for ids, t in _ratio_groups(meta, rule):
            med_d = np.median(V[ids, :BASE7_N], axis=1, keepdims=True)
            C = (V[ids] / med_d).mean(axis=0)
            P = V[t] / np.median(V[t, :BASE7_N])
            lr = np.log(np.maximum(P, 1e-9)) - np.log(np.maximum(_lag(C, RATIO_LAG), 1e-9))
            z = _robust_z(lr[None, :], BASE7_N)
            ratio[t] = _persist_backfill(_ewm(z) < -RATIO_K, PEER_PERSIST)[0]

    F = {"SPEC": spec, "NEAR": near, "HOLD": hold, "STD": stdx, "PEER": peer,
         "VALVE": valve, "AIR": air, "RATIO": ratio}
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
"""Plotly 차트: 센서 추이(sensor_figure) · 이상점 트렌드(trend_figure, 전체 현황용)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from core import KIND, Plant

LINE_COLOR = "#0e7490"
BAND_KINDS = [k for k in KIND if k not in ("SPEC", "NEAR")]   # 세로 음영으로 보여 줄 경고


def rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def style(fig: go.Figure) -> go.Figure:
    """밝은 현장 모니터 테마 공통 스타일."""
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#475569"),
    )
    fig.update_xaxes(gridcolor="rgba(15,23,42,.07)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(15,23,42,.07)", zeroline=False)
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

    # 이상 구간 세로 음영 (Hold / σ 초과 / 동료 이탈 / 공정 연관 규칙) — 색은 KIND 의 경고 색
    for kind in BAND_KINDS:
        for a, b in _spans(plant.F[kind][i, -window:], x):
            fig.add_vrect(x0=a, x1=b, fillcolor=f"rgba({rgb(KIND[kind]['color'])},.16)", line_width=0, layer="below")

    # 동료(같은 항목 다른 센서) 범위 + 중앙값
    if peers:
        mem = plant.members[plant.G[i]]
        mem = mem[mem != i]
        if len(mem):
            P = plant.V[mem][:, -window:]
            fig.add_trace(go.Scatter(x=x, y=P.min(axis=0), mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=x, y=P.max(axis=0), mode="lines", line=dict(width=0), fill="tonexty",
                                     fillcolor="rgba(100,116,139,.16)", hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=x, y=np.median(P, axis=0), mode="lines", line=dict(color="#64748b", width=1.2, dash="dot"),
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


SEV_RGB = {"red": "220,38,38", "yellow": "245,158,11"}


def trend_figure(plant: Plant, i: int, window: int, height: int = 260) -> go.Figure:
    """이상점 트렌드: 영역 차트 + 임계치(USL/LSL) 점선 + 이상 구간 음영(조치 필요 = 빨강, 확인 필요 = 노랑)
    + 임계치를 넘은 점은 큰 붉은 마커 + 차트 위쪽 경고 문구."""
    unit, dec = plant.meta["unit"].iat[i], int(plant.meta["dec"].iat[i])
    lsl, usl = plant.lsl[i], plant.usl[i]
    has_l = not np.isnan(lsl)
    x = plant.idx[-window:]
    y = plant.V[i, -window:]
    lo = min(y.min(), lsl if has_l else y.min())
    hi = max(y.max(), usl)
    pad = (hi - lo) * 0.08
    y0, y1 = lo - pad, hi + pad

    fig = go.Figure()
    red = np.zeros(window, bool)
    yel = np.zeros(window, bool)
    for k, v in KIND.items():
        if v["sev"] == "red":
            red |= plant.F[k][i, -window:]
        else:
            yel |= plant.F[k][i, -window:]
    yel &= ~red
    for mask, sev in ((red, "red"), (yel, "yellow")):
        for a, b in _spans(mask, x):
            fig.add_vrect(x0=a, x1=b, fillcolor=f"rgba({SEV_RGB[sev]},.13)", line_width=0, layer="below")

    # 영역 차트: 아래 경계(y0)까지 채움
    fig.add_trace(go.Scatter(x=x, y=np.full(window, y0), mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=LINE_COLOR, width=1.8), fill="tonexty",
                             fillcolor="rgba(14,116,144,.12)", showlegend=False,
                             hovertemplate="%{x|%H:%M}  <b>%{y:." + str(dec) + "f}</b> " + unit + "<extra></extra>"))
    mem = plant.members[plant.G[i]]
    mem = mem[mem != i]
    if len(mem):
        fig.add_trace(go.Scatter(x=x, y=np.median(plant.V[mem][:, -window:], axis=0), mode="lines",
                                 line=dict(color="#94a3b8", width=1, dash="dot"), showlegend=False,
                                 hovertemplate="동료 중앙값 %{y:.2f}<extra></extra>"))

    for val, name in ((usl, "USL"), (lsl if has_l else None, "LSL")):
        if val is not None:
            fig.add_hline(y=val, line=dict(color="#dc2626", width=1.4, dash="dash"), annotation_text=f"{name} {val:g}",
                          annotation_position="top left" if name == "USL" else "bottom left",
                          annotation_font=dict(size=10, color="#dc2626"))

    out = (y > usl) | ((y < lsl) if has_l else np.zeros(window, bool))
    if out.any():
        fig.add_trace(go.Scatter(x=x[out], y=y[out], mode="markers", showlegend=False,
                                 marker=dict(color="#dc2626", size=11, line=dict(color="#ffffff", width=1.5)),
                                 hovertemplate="임계치 초과 %{x|%H:%M}  <b>%{y:." + str(dec) + "f}</b><extra></extra>"))

    # 상단 경고 문구
    text, color = "", "#b45309"
    if out.any():
        dev = np.where(y > usl, y - usl, (lsl - y) if has_l else 0)
        j = int(np.argmax(np.where(out, dev, -np.inf)))
        low = has_l and y[j] < lsl
        text = (f"⚠ {'하한 이탈' if low else '상한 초과'} · {'최저' if low else '최고'} {y[j]:.{dec}f} {unit} ({x[j]:%H:%M})"
                f" · 임계치 밖 {int(out.sum()) * 5}분")
        color = "#dc2626"
    else:
        kinds = plant.active_kinds(i) or plant.window_kinds(i, window)
        if kinds:
            first = int(np.argmax(plant.F[kinds[0]][i, -window:]))
            text = f"⚠ {KIND[kinds[0]]['label'].split('(')[0]} · {x[first]:%H:%M}부터"
            color = "#dc2626" if KIND[kinds[0]]["sev"] == "red" else "#b45309"
    if text:
        fig.add_annotation(xref="paper", yref="paper", x=0, y=1.02, xanchor="left", yanchor="bottom", showarrow=False,
                           text=f"<b>{text}</b>", font=dict(size=12, color=color))

    fig.update_layout(height=height, margin=dict(l=8, r=8, t=28, b=8), showlegend=False, hovermode="x unified",
                      xaxis=dict(tickformat="%H:%M" if window <= 288 else "%m/%d %H:%M", showgrid=False),
                      yaxis=dict(range=[y0, y1], title=None))
    return style(fig)
````

## 파일: `views.py`

````python
"""화면 4개: 전체 현황(공정 흐름·이상점 연동) → 공정 상세(계열·조 흐름) → 한눈에 비교 → 경고 센터(사고 묶음)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from charts import BAND_KINDS, LINE_COLOR, _spans, rgb, sensor_figure, style, trend_figure
from core import (
    BUILDINGS, KIND, LINES, NONE_RANK, PROCESSES, STEP_MIN, get_plant, incidents, kind_by_rank, tanks_of,
)

RANGES = {"3시간": 36, "6시간": 72, "12시간": 144, "24시간": 288, "48시간": 576}
OK_COLOR, RESOLVED_COLOR = "#16a34a", "#64748b"


# ───────────────────────── 공통 ─────────────────────────
def _ctx():
    return get_plant(), RANGES[st.session_state.get("range", "24시간")]


def _color(rank: int) -> str:
    return OK_COLOR if rank >= NONE_RANK else KIND[kind_by_rank(rank)]["color"]


def _status_text(rank: int) -> str:
    return "정상" if rank >= NONE_RANK else KIND[kind_by_rank(rank)]["label"].split("(")[0]


def _legend():
    st.caption(
        "배경: 주황 = 상하한 근접 · 빨강 = 이탈  |  세로 음영: 파랑 = Hold · 보라 = σ 초과 · 분홍 = 동료 대비 이탈 · "
        "갈색 = 개도-투입 불일치 · 하늘색 = DO↓ 공기개도↑ · 남색 = 고분자 부족  |  "
        "회색 띠/점선 = 같은 항목 다른 센서의 범위/중앙값"
    )


def _header(title: str, sub: str):
    plant = get_plant()
    st.markdown(f"### {title}")
    st.caption(f"{sub}  |  데이터 기준 {plant.idx[-1]:%Y-%m-%d %H:%M} · {STEP_MIN}분 평균 (데모)")


def _sensor_head(plant, i: int, window: int) -> str:
    """센서 머리글 한 줄: 항목 · 현재값(이상이면 경고 색) · 1시간 변화 · 상태, 아래에 규격·σ·이력."""
    m = plant.meta.iloc[i]
    dec = int(m.dec)
    kinds = plant.active_kinds(i)
    hist = [k for k in plant.window_kinds(i, window) if k not in kinds]
    cur, d = plant.V[i, -1], plant.V[i, -1] - plant.V[i, -13]
    if kinds:
        state = " · ".join(f'<span style="color:{KIND[k]["color"]}">{_kind_name(k)}</span>' for k in kinds)
    elif hist:
        state = f'<span style="color:{RESOLVED_COLOR}">해소됨</span>'
    else:
        state = f'<span style="color:{OK_COLOR}">정상</span>'
    extra = f"규격 {plant.spec_text(i)} · σ {np.nan_to_num(plant.std[i, -1]):.2f}"
    if hist:
        extra += " · 이력: " + ", ".join(_kind_name(k) for k in hist)
    vcol = KIND[kinds[0]]["color"] if kinds else "var(--ink)"
    return (f'<div class="sh"><span class="p">{m.param}</span><span class="v" style="color:{vcol}">{cur:.{dec}f}</span>'
            f'<span class="u">{m.unit}</span><span class="dl">{d:+.{dec}f} /1h</span><span class="s">{state}</span>'
            f'<div class="x">{extra}</div></div>')


def _sensor_card(plant, i: int, window: int, height: int = 240):
    st.markdown(_sensor_head(plant, i, window), unsafe_allow_html=True)
    st.plotly_chart(sensor_figure(plant, i, window, height), width="stretch",
                    key=f"c-{i}-{window}", config={"displayModeBar": False})


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


# ───────────────────────── 1. 전체 현황 ─────────────────────────
# 공정 흐름 중심 (사용자 디자인 지시서, 2026-11-04): 3초 안에 어느 공정이 이상인지 보이게.
#   ① 주요 이상점 요약 바(이벤트 스택) → ② 공정 흐름 노드(신호등 + 글로우 + 영향 화살표)
#   → ③ 이상점 요약 캔버스(시간축) → ④ 공정 상세 트렌드.
#   바·노드·캔버스 점 중 어느 것을 눌러도 같은 '선택'으로 묶여 노드 강조와 아래 트렌드가 함께 바뀜.
SEV_COLOR = {"red": "#dc2626", "yellow": "#f59e0b", "green": "#16a34a"}
SEV_TEXT = {"red": "조치 필요", "yellow": "확인 필요", "green": "정상"}
IMPACT_COLOR = {"red": "#dc2626", "yellow": "#f97316", "green": "#94a3b8"}   # 다음 단계로 가는 화살표
BANNER_N = 5


def _kind_name(k: str) -> str:
    return KIND[k]["label"].split("(")[0]


def _sev(rank: int) -> str:
    return "green" if rank >= NONE_RANK else KIND[kind_by_rank(rank)]["sev"]


def _sev_ids(plant, ids) -> tuple[str, int | None]:
    """센서 묶음의 지금 신호등과 대표 센서: 빨강(조치 필요) 경고가 하나라도 있으면 빨강, 그 외 이상이 있으면 노랑."""
    if not len(ids):
        return "green", None
    red = np.zeros(len(ids), bool)
    for k, v in KIND.items():
        if v["sev"] == "red":
            red |= plant.F[k][ids, -1]
    if red.any():
        return "red", int(ids[np.argmax(red)])
    r = plant.now_rank[ids]
    return ("yellow", int(ids[np.argmin(r)])) if r.min() < NONE_RANK else ("green", None)


def _stages(p: str) -> list[str]:
    """공정 흐름 순서의 조 종류 (폭기조1~5, 반응조1~3 은 노드 하나)."""
    return list(dict.fromkeys(stage for _, stage, _ in tanks_of(p)))


def _stage_name(stage: str) -> str:
    return stage.replace("유기침전조", "침전조").replace("무기침전조", "침전조")


def _ikey(x: dict) -> tuple:
    return (x["bldg"], x["proc"], x["line"], x["stage"])


def _now(plant, x: dict) -> tuple[int, str]:
    """사고의 '지금' 가장 심한 경고 (순위, 센서). 이미 풀린 경고(조회 구간 안 과거)는 빼고 판단."""
    best, pick = (True, NONE_RANK), x["sids"][0]
    for i in x["sids"]:
        for k in plant.active_kinds(i):                      # 빨강(조치 필요)을 순위보다 먼저 봄
            cand = (KIND[k]["sev"] != "red", KIND[k]["rank"])
            if cand < best:
                best, pick = cand, i
    return (best[1], pick) if best[1] < NONE_RANK else (x["rank"], x["sids"][0])


def _headline(plant, x: dict) -> str:
    """이상점 요약 문장: [STAGE nn] 공정 조 · 위치 항목 현상 (현재값 단위)."""
    rank, i = _now(plant, x)
    m = plant.meta.iloc[i]
    k = kind_by_rank(rank)
    v = plant.V[i, -1]
    low = (not np.isnan(plant.lsl[i])) and v < (plant.lsl[i] + plant.usl[i]) / 2
    what = {
        "SPEC": ("농도 급감 · 하한 이탈" if m.param == "DO" else "하한 이탈") if low else "상한 초과",
        "NEAR": "하한 근접" if low else "상한 근접",
        "HOLD": "값 고정 1시간+ (센서·통신 확인)", "STD": "변동 급증", "VALVE": "개도-투입 불일치 (막힘·펌프 의심)",
        "AIR": "DO 하락 · 공기개도 상승 (산기관 의심)", "RATIO": "고분자 부족 (약품 대비)", "PEER": "동료 대비 이탈",
    }[k]
    n = _stages(m.proc).index(m.stage) + 1
    return (f"[STAGE {n:02d}] {m.proc} {_stage_name(m.stage)} · {m.bldg} {m.line} {m.tank} {m.param} {what} "
            f"({v:.{int(m.dec)}f} {m.unit})")


def _select(kind: str, key: tuple):
    st.session_state["ov_sel"] = (kind, key)


def _resolve_selection(inc: list[dict]):
    """캔버스 점 클릭을 반영하고, 지금 선택(사고 또는 노드)을 돌려줌. 없으면 가장 시급한 사고."""
    ev = st.session_state.get("ov_canvas")
    try:
        pts = ev["selection"]["points"] if ev else []
    except (KeyError, TypeError):
        pts = []
    if pts:
        cd = pts[0].get("customdata")
        cd = cd[0] if isinstance(cd, (list, tuple)) else cd
        if cd and cd != st.session_state.get("_ov_canvas_last"):   # 새로 누른 점만 반영 (바·노드 클릭을 덮어쓰지 않게)
            st.session_state["_ov_canvas_last"] = cd
            st.session_state["ov_sel"] = ("inc", tuple(cd.split("|")))
    sel = st.session_state.get("ov_sel")
    if sel and sel[0] == "inc" and not any(_ikey(x) == tuple(sel[1]) for x in inc):
        sel = None
    if not sel and inc:
        sel = ("inc", _ikey(inc[0]))
    return sel


def _banner(plant, act: list[dict], sel):
    """① 주요 이상점 요약 바: 시급한 순(조치 필요 → 확인 필요). 누르면 그 이상점으로 아래 전체가 연동."""
    css = []
    if not act:
        st.markdown('<div class="ok-bar">전 공정 정상 — 진행 중인 이상점 없음</div>', unsafe_allow_html=True)
        return
    for n, x in enumerate(act[:BANNER_N]):
        sev = _sev(_now(plant, x)[0])
        key = f"bn-{n}"
        st.button(("🚨 " if sev == "red" else "⚠ ") + _headline(plant, x) + f" — {SEV_TEXT[sev]}",
                  key=key, on_click=_select, args=("inc", _ikey(x)), width="stretch")
        bg = "#dc2626" if sev == "red" else "#b45309"
        rule = f".st-key-{key} button{{background:{bg} !important;"
        if sev == "red":
            rule += "animation:pulseR 1.8s ease-in-out infinite;"
        if sel == ("inc", _ikey(x)):
            rule += "outline:3px solid #0f172a;outline-offset:2px;"
        css.append(rule + "}")
    if len(act) > BANNER_N:
        st.caption(f"외 {len(act) - BANNER_N}건 진행 중 — 아래 캔버스와 경고 센터에서 모두 볼 수 있어요")
    st.markdown("<style>" + "".join(css) + "</style>", unsafe_allow_html=True)


def _flow(plant, bsel: str | None, sel_node: tuple | None):
    """② 공정 흐름 노드: 공정마다 한 줄, 조 종류 = 노드(신호등), 노드 사이 화살표 = 앞 단계의 영향."""
    css = []
    for pi, p in enumerate(PROCESSES):
        stages = _stages(p)
        widths = [0.75] + sum(([1, 0.3] for _ in stages), [])[:-1]
        cols = st.columns(widths, vertical_alignment="center", gap="small")
        lane = plant.sel(proc=p, **({"bldg": bsel} if bsel else {}))
        lsev = _sev_ids(plant, lane)[0]
        cols[0].markdown(f'<div class="ln2">{p}<small style="color:{SEV_COLOR[lsev]}">● {SEV_TEXT[lsev]}</small></div>',
                         unsafe_allow_html=True)
        for si, stage in enumerate(stages):
            ids = plant.sel(proc=p, stage=stage, **({"bldg": bsel} if bsel else {}))
            sev, j = _sev_ids(plant, ids)
            n_bad = int((plant.now_rank[ids] < NONE_RANK).sum())
            label = f"*STAGE {si + 1:02d} · {_stage_name(stage)}*  \n**● {SEV_TEXT[sev]}**  \n이상 {n_bad} / {len(ids)}"
            if j is not None:
                m = plant.meta.iloc[j]
                label += f"  \n{m.bldg} {m.line[0]} {m.tank} {m.param} {plant.V[j, -1]:.{int(m.dec)}f}"
            key = f"fn-{pi}-{si}"
            cols[1 + 2 * si].button(label, key=key, on_click=_select, args=("node", (p, stage)), width="stretch")
            rule = {
                "red": "border:2px solid #dc2626 !important;background:#fef2f2 !important;animation:glowR 1.8s ease-in-out infinite;",
                "yellow": "border:2px solid #f59e0b !important;background:#fffbeb !important;animation:glowY 2.2s ease-in-out infinite;",
                "green": "border:1px solid #cbd5e1 !important;background:#ffffff !important;",
            }[sev]
            if sel_node == (p, stage):
                rule += "outline:3px solid #0f172a;outline-offset:3px;"
            strong = {"red": "#dc2626", "yellow": "#b45309", "green": "#16a34a"}[sev]
            css.append(f".st-key-{key} button{{{rule}}}.st-key-{key} button strong{{color:{strong};}}")
            if si < len(stages) - 1:                          # 영향 화살표: 앞 단계(이 노드)가 이상이면 주황/빨강
                c = IMPACT_COLOR[sev]
                cols[2 + 2 * si].markdown(f'<div class="fa" style="--c:{c}"><b>{"영향" if sev != "green" else ""}</b><i></i></div>',
                                          unsafe_allow_html=True)
    st.markdown("<style>" + "".join(css) + "</style>", unsafe_allow_html=True)


def _canvas(plant, inc: list[dict], window: int, sel) -> go.Figure:
    """③ 이상점 요약 캔버스: 세로 = 공정·조(흐름 순서), 가로 = 시간. 사고마다 지속 막대 + 지금 점. 점을 누르면 선택."""
    used = {(it["proc"], it["stage"]) for it in inc}
    lanes = [(p, s) for p in PROCESSES for s in _stages(p) if (p, s) in used] or [(PROCESSES[0], _stages(PROCESSES[0])[0])]
    ypos = {ls: n for n, ls in enumerate(lanes)}
    x = plant.idx[-window:]
    step = x[1] - x[0]
    # 같은 줄(공정·조)에 사고가 여럿이면 높이를 하나씩 나눠 줌 → 점이 겹치지 않아 따로 누를 수 있음
    slot, count = {}, {}
    for it in inc:
        ls = (it["proc"], it["stage"])
        slot[_ikey(it)] = count.get(ls, 0)
        count[ls] = count.get(ls, 0) + 1
    fig = go.Figure()
    for it in inc:
        sev = _sev(_now(plant, it)[0] if it["active"] else it["rank"])
        n_in = count[(it["proc"], it["stage"])]
        y = ypos[(it["proc"], it["stage"])] + (slot[_ikey(it)] - (n_in - 1) / 2) * min(0.24, 0.8 / n_in)
        key = "|".join(_ikey(it))
        color = SEV_COLOR[sev] if it["active"] else "#94a3b8"
        end = "" if it["active"] else f"{it['last']:%H:%M}"      # 사내 Python 3.11 이하에서도 되게 f-string 중첩 안 함
        hover = f"{it['title']}<br>{it['what']}<br>{_status_text(it['rank'])} · {it['first']:%H:%M}~{end}"
        fig.add_trace(go.Scatter(x=[it["first"], it["last"] + step], y=[y, y], mode="lines", line=dict(color=color, width=6),
                                 customdata=[key, key], hovertext=[hover, hover], hoverinfo="text", showlegend=False))
        picked = sel == ("inc", _ikey(it))                     # 선택된 점은 굵은 검정 테두리 (덮는 원을 따로 그리면 옆 점 클릭을 가로챔)
        fig.add_trace(go.Scatter(x=[it["last"] + step], y=[y], mode="markers", customdata=[key], hovertext=[hover],
                                 hoverinfo="text", showlegend=False,
                                 marker=dict(size=14 if picked else (12 if it["active"] else 9),
                                             color=color if it["active"] else "#ffffff",
                                             line=dict(color="#0f172a" if picked else ("#ffffff" if it["active"] else "#94a3b8"),
                                                       width=3 if picked else 2))))
    fig.add_vline(x=x[-1] + step, line=dict(color="#0f172a", width=1, dash="dot"))
    for n in range(1, len(lanes)):
        if lanes[n][0] != lanes[n - 1][0]:                      # 공정 경계선
            fig.add_hline(y=n - 0.5, line=dict(color="#94a3b8", width=1))
    fig.update_yaxes(tickvals=list(range(len(lanes))), ticktext=[f"{p} · {_stage_name(s)}" for p, s in lanes],
                     range=[len(lanes) - 0.5, -0.5], showgrid=False, tickfont=dict(size=12, color="#0f172a"))
    fig.update_xaxes(range=[x[0], x[-1] + step * 6], tickformat="%H:%M" if window <= 288 else "%m/%d %H:%M")
    fig.update_layout(height=58 * len(lanes) + 50, margin=dict(l=8, r=8, t=8, b=8), hovermode="closest",
                      clickmode="event+select", dragmode=False)
    return style(fig)


def _detail(plant, sel, inc: list[dict], window: int, bsel: str | None):
    """④ 공정 상세 트렌드: 선택된 이상점(또는 노드)의 센서 추이."""
    if sel and sel[0] == "inc":
        x = next(it for it in inc if _ikey(it) == tuple(sel[1]))
        title, sub = f"{x['title']} · {x['what']}", f"{_status_text(x['rank'])} · {x['first']:%H:%M}부터"
        sids = x["sids"][:4]
    elif sel and sel[0] == "node":
        p, stage = sel[1]
        ids = plant.sel(proc=p, stage=stage, **({"bldg": bsel} if bsel else {}))
        bad = [int(i) for i in ids[np.argsort(plant.now_rank[ids], kind="stable")] if plant.now_rank[i] < NONE_RANK]
        title = f"{p} · {_stage_name(stage)}" + (f" · {bsel}" if bsel else "")
        sub = f"이상 센서 {len(bad)}개" if bad else "이상 없음 — 첫 계열 센서를 보여 줌"
        sids = bad[:4] or [int(i) for i in ids[:2]]
    else:
        return
    st.markdown(f'<div class="sec">④ 공정 상세 트렌드<span>{title} — {sub}</span></div>', unsafe_allow_html=True)
    for k in range(0, len(sids), 2):
        for col, i in zip(st.columns(2), sids[k:k + 2]):
            with col:
                st.markdown(_sensor_head(plant, i, window), unsafe_allow_html=True)
                st.plotly_chart(trend_figure(plant, i, window), width="stretch", key=f"tr-{i}-{window}",
                                config={"displayModeBar": False})


def overview():
    plant, window = _ctx()
    all_inc = incidents(plant, window)
    # 시급한 순: 조치 필요(red) → 확인 필요, 같은 단계면 경고 순위 → 최근 시작
    act = sorted([x for x in all_inc if x["active"]],
                 key=lambda x: (_sev(_now(plant, x)[0]) != "red", _now(plant, x)[0], -x["first"].value))
    sel = _resolve_selection(act + [x for x in all_inc if not x["active"]])

    st.markdown('<div class="sec" style="margin-top:0">① 주요 이상점<span>시급한 순 · 누르면 아래 노드·캔버스·트렌드가 함께 바뀜</span></div>',
                unsafe_allow_html=True)
    _banner(plant, act, sel)

    head, filt = st.columns([3, 1.4], vertical_alignment="bottom")
    head.markdown('<div class="sec">② 공정 흐름<span>신호등: 초록 정상 · 노랑 확인 필요 · 빨강 조치 필요 · 화살표 색 = 앞 단계 이상의 영향</span></div>',
                  unsafe_allow_html=True)
    b = filt.segmented_control("동", ["전체"] + BUILDINGS, default="전체", key="ov_b", label_visibility="collapsed")
    bsel = None if b in (None, "전체") else b
    sel_node = (sel[1][1], sel[1][3]) if sel and sel[0] == "inc" else (tuple(sel[1]) if sel else None)
    _flow(plant, bsel, sel_node)

    shown = [x for x in all_inc if not bsel or x["bldg"] == bsel]
    st.markdown(f'<div class="sec">③ 이상점 요약 캔버스<span>{len(shown)}건 · 이상이 있었던 공정만 · 막대 = 지속 시간, 큰 점 = 지금 진행 중 · 점을 누르면 아래 트렌드로</span></div>',
                unsafe_allow_html=True)
    st.plotly_chart(_canvas(plant, shown, window, sel), width="stretch", key="ov_canvas", on_select="rerun",
                    selection_mode="points", config={"displayModeBar": False})

    _detail(plant, sel, all_inc, window, bsel)


# ───────────────────────── 2. 공정 상세 ─────────────────────────
# 조 = 누를 수 있는 탱크(버튼), 탱크 사이는 배관(→)으로 이어 공정 흐름을 그대로 보여 줌. 카드·이모지 없음.
def _toggle_node(line: str, tank: str):
    s = set(st.session_state.get("proc_open", set()))
    s ^= {(line, tank)}
    st.session_state["proc_open"] = s


def _set_open(nodes):
    st.session_state["proc_open"] = set(nodes)


def process():
    plant, window = _ctx()
    _header("공정 상세", "계열별 공정 흐름 — 이상 있는 조는 자동으로 펼쳐지고, 탱크를 누르면 그래프가 펼쳐지거나 접혀요")

    jump = st.session_state.pop("_jump", None)
    if jump:
        st.session_state["proc_b"], st.session_state["proc_p"] = jump

    c = st.columns([1, 1, 1.3, 1.3, 2], vertical_alignment="bottom")
    b = c[0].selectbox("건물", BUILDINGS, key="proc_b")
    p = c[1].selectbox("공정", PROCESSES, key="proc_p")
    tanks = tanks_of(p)
    dec = plant.meta["dec"].to_numpy()

    # 조(노드)별 상태 · 현재값
    info = {}
    for l in LINES:
        for tank, stage, params in tanks:
            vals, worst = [], NONE_RANK
            for prm in params:
                i = plant.find(b, p, l, tank, prm)
                worst = min(worst, int(plant.now_rank[i]))
                vals.append((prm, plant.V[i, -1], int(dec[i]), bool(plant.active_kinds(i))))
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
        st.markdown(f'<div class="lh"><b>{l}</b><span style="color:{_color(min(ws))}">{_status_text(min(ws))}{extra}</span></div>',
                    unsafe_allow_html=True)
        cols = st.columns(len(tanks), gap="small")
        for ti, (tank, stage, params) in enumerate(tanks):
            w, vals = info[(l, tank)]
            # 탱크 이름은 기울임(*) → CSS 로 굵은 머리글, 이상 항목은 굵게(**) → CSS 로 그 탱크의 경고 색
            label = f"*{tank}*  \n" + "  \n".join(
                f"**{prm} {v:.{d}f}**" if bad else f"{prm} {v:.{d}f}" for prm, v, d, bad in vals
            )
            key = f"nd-{li}-{ti}"
            with cols[ti]:
                st.button(label, key=key, on_click=_toggle_node, args=(l, tank), width="stretch")
            col = _color(w)
            is_open = (l, tank) in opened
            edge = col if w < NONE_RANK else "#475569"                # 정상 탱크는 조용하게 (색 띠 없음)
            rule = (f".st-key-{key} button{{border:2px solid {edge} !important;"
                    f"border-left:{8 if w < NONE_RANK else 2}px solid {edge} !important;"
                    f"{'background:#ecfeff !important;' if is_open else ''}}}"
                    f".st-key-{key} button strong{{color:{col};}}")
            if ti == len(tanks) - 1:                                   # 마지막 탱크 뒤에는 배관 없음
                rule += f".st-key-{key}::before,.st-key-{key}::after{{display:none;}}"
            css.append(rule)

        for tank, stage, params in tanks:                          # 펼친 조의 그래프를 해당 계열 바로 아래에
            if (l, tank) in opened:
                st.markdown(f'<div class="xh">{b} · {p} · {l} · <b>{tank}</b></div>', unsafe_allow_html=True)
                for col_, prm in zip(st.columns(len(params)), params):
                    with col_:
                        _sensor_card(plant, plant.find(b, p, l, tank, prm), window, height=230)
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
            mark = f" <span style='color:{KIND[ks[0]]['color']}'>■ {_kind_name(ks[0])}</span>" if ks else ""
            titles.append(f"<b>{l[0]}</b> · {tank}  {plant.V[i, -1]:.2f}{mark}")
    fig = make_subplots(rows=nr, cols=nc, subplot_titles=titles, shared_xaxes=True, shared_yaxes="columns",
                        vertical_spacing=0.06, horizontal_spacing=0.025)

    x = plant.idx[-window:]
    for r, l in enumerate(LINES, start=1):
        for ci, (tank, _, _) in enumerate(cols, start=1):
            i = plant.find(b, p, l, tank, prm)
            y = plant.V[i, -window:]
            ks = plant.active_kinds(i)
            color = KIND[ks[0]]["color"] if ks else LINE_COLOR
            for kind in BAND_KINDS:
                for s0, s1 in _spans(plant.F[kind][i, -window:], x):
                    fig.add_vrect(x0=s0, x1=s1, fillcolor=f"rgba({rgb(KIND[kind]['color'])},.22)", line_width=0, layer="below", row=r, col=ci)
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
        "선 색 = 현재 상태(청록=정상) · 붉은 점선 = LSL/USL · 세로 음영 = 경고 구간(색은 경고 종류, 위쪽 '기준' 참고)"
    )


# ───────────────────────── 4. 경고 센터 ─────────────────────────
# 카드 목록 대신: 위에 시간축 알람 타임라인(사고마다 언제부터 얼마나), 아래에 선으로 구분한 사고별 그래프 목록.
def _timeline(plant, inc: list[dict], window: int) -> go.Figure:
    x = plant.idx[-window:]
    step = x[1] - x[0]
    labels, seen = [], set()
    for n, it in enumerate(inc):
        what = it["what"] if len(it["what"]) <= 28 else it["what"][:27] + "…"
        lab = f"{it['title']} · {what}"
        labels.append(lab if lab not in seen else f"{lab} ({n})")
        seen.add(labels[-1])
    fig = go.Figure()
    for kind in sorted(KIND, key=lambda k: -KIND[k]["rank"]):        # 덜 심한 것부터 그려서 심한 게 위에 보이게
        xs, ys = [], []
        for lab, it in zip(labels, inc):
            mask = plant.F[kind][it["sids"], -window:].any(axis=0)
            for s0, s1 in _spans(mask, x):
                xs += [s0, s1 + step, None]
                ys += [lab, lab, None]
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=KIND[kind]["color"], width=11),
                                     name=_kind_name(kind), hovertemplate=f"{_kind_name(kind)}<br>%{{x|%m/%d %H:%M}}<extra></extra>"))
    fig.add_vline(x=x[-1], line=dict(color="#1e293b", width=1, dash="dot"))
    fig.update_yaxes(categoryorder="array", categoryarray=labels, autorange="reversed", showgrid=True,
                     gridcolor="rgba(15,23,42,.06)", tickfont=dict(size=12, color="#0f172a"))
    fig.update_xaxes(tickformat="%H:%M" if window <= 288 else "%m/%d %H:%M", range=[x[0], x[-1] + step])
    fig.update_layout(height=26 * len(inc) + 80, margin=dict(l=8, r=8, t=30, b=8),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, font=dict(size=11), traceorder="reversed"))
    return style(fig)


def alerts():
    plant, window = _ctx()
    _header("경고 센터", "사고(같은 계열·같은 조) 단위 — 위 타임라인으로 언제부터인지 보고, 아래로 스크롤하며 그래프 확인")
    inc = incidents(plant, window)
    if not inc:
        st.success(f"최근 {st.session_state.get('range', '24시간')} 동안 경고가 없습니다.")
        return

    f = st.columns([2.6, 1, 1, 1.2], vertical_alignment="bottom")
    kinds = f[0].multiselect("경고 유형", list(KIND), default=list(KIND), format_func=_kind_name)
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
    st.markdown(f'<div class="sec">알람 타임라인<span>사고 {len(inc)}건 · 진행 중 {n_act} · 해소 {len(inc) - n_act} · 점선 = 지금</span></div>',
                unsafe_allow_html=True)
    st.plotly_chart(_timeline(plant, inc, window), width="stretch", key=f"tl-{window}-{len(inc)}", config={"displayModeBar": False})

    st.markdown('<div class="sec">사고별 그래프<span>아래로 스크롤하며 확인</span></div>', unsafe_allow_html=True)
    _legend()
    shown = st.session_state.setdefault("_alert_n", 8)
    for x in inc[:shown]:
        ks = " · ".join(f'<span style="color:{KIND[k]["color"]}">{_kind_name(k)}</span>'
                        for k in sorted(set(x["ev"]["kind"]), key=lambda k: KIND[k]["rank"]))
        st.markdown(
            f'<div class="ih" style="--c:{_color(x["rank"])}"><span class="t">{x["first"]:%H:%M} → {x["last"]:%H:%M}</span>'
            f'<b>{x["title"]}</b><span class="w">{x["what"]}</span>'
            f'<span class="g">{"진행 중" if x["active"] else "해소됨"}</span><span class="ks">{ks}</span></div>',
            unsafe_allow_html=True,
        )
        _incident_charts(plant, x, window, "a")
    if shown < len(inc):
        if st.button(f"더 보기 ({len(inc) - shown}건 남음)"):
            st.session_state["_alert_n"] = shown + 8
            st.rerun()
````

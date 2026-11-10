"""공정 구조 / 규격 / 데모 데이터 / 이상 감지 (센서 약 960개, 5분 간격).

실제 적용 시:
  - STAGE_SPEC 의 규격(LSL/USL, 표준편차 기준)만 실제 값으로 수정
  - _build() 안의 '데모 데이터 생성' 부분을 서버(DB) 조회로 교체 → V(센서×시간) 배열만 채우면 나머지는 그대로 동작
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

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


def _cache_resource(fn):
    """Streamlit 이면 st.cache_resource, Dash 등 다른 프레임워크(WWTP_NO_STREAMLIT=1)면 lru_cache.
    감지 로직(core)이 화면 프레임워크에 묶이지 않게 하려는 분기."""
    if os.environ.get("WWTP_NO_STREAMLIT"):
        from functools import lru_cache
        return lru_cache(maxsize=1)(fn)
    import streamlit as st
    return st.cache_resource(show_spinner="센서 데이터 생성 중…")(fn)


@_cache_resource
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

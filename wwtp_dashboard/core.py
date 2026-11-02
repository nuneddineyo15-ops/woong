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

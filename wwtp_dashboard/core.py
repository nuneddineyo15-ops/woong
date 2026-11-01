"""공정 구조 / 규격 / 데모 데이터 생성 / 이상 판정 로직."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────────────────────
# 1. 설정 (실제 적용 시 여기만 고치면 됨)
# ─────────────────────────────────────────────────────────────
PLANT = {
    "1동(메인)": {"유기폐수": ["A계열", "B계열"], "무기폐수": ["A계열"]},
    "2동(신관)": {"고농도": ["A계열"], "불산": ["A계열", "B계열"]},
}

# lsl / usl : 규격 하한 / 상한 (없으면 None)
# std_limit : 이동 표준편차 경고 기준 (항목마다 단위가 달라서 항목별로 둠)
PARAMS = {
    "pH":  dict(unit="pH",   lsl=6.0, usl=8.5,  base=7.2,   sigma=0.20, std_limit=0.5),
    "DO":  dict(unit="mg/L", lsl=2.0, usl=8.0,  base=5.0,   sigma=0.5,  std_limit=1.2),
    "F":   dict(unit="ppm",  lsl=None, usl=15.0, base=6.5,   sigma=0.9,  std_limit=3.0),
    "COD": dict(unit="mg/L", lsl=None, usl=40.0, base=28.0,  sigma=1.8,  std_limit=5.0),
    "처리량": dict(unit="m³/h", lsl=50.0, usl=200.0, base=120.0, sigma=6.0, std_limit=10.0),
}

NEAR_RATIO = 0.10   # 규격폭의 10% 이내로 상/하한에 붙으면 "근접" 경고
HOLD_MIN = 60       # 같은 값이 60분 이상 이어지면 Hold
STD_WINDOW = 60     # 이동 표준편차 윈도우(분)
N_MIN = 24 * 60     # 데모 데이터 길이(1분 간격 24시간)

KIND = {
    "SPEC": dict(label="스펙 이탈", color="#ef4444", icon="🔴", rank=0),
    "NEAR": dict(label="상하한 근접", color="#f97316", icon="🟠", rank=1),
    "HOLD": dict(label="1시간 Hold", color="#3b82f6", icon="🔵", rank=2),
    "STD":  dict(label="표준편차 초과", color="#a855f7", icon="🟣", rank=3),
}
FLAG_COL = {"SPEC": "spec", "NEAR": "near", "HOLD": "hold", "STD": "stdx"}

Key = tuple  # (건물, 시스템, 계열, 항목)


def all_keys() -> list[Key]:
    return [
        (b, s, l, p)
        for b, systems in PLANT.items()
        for s, lines in systems.items()
        for l in lines
        for p in PARAMS
    ]


def all_lines() -> list[tuple]:
    return [(b, s, l) for b, systems in PLANT.items() for s, lines in systems.items() for l in lines]


def line_label(b: str, s: str, l: str) -> str:
    return f"{b} › {s} › {l}"


def spec_text(p: dict) -> str:
    if p["lsl"] is None:
        return f"≤ {p['usl']:g} {p['unit']}"
    return f"{p['lsl']:g} ~ {p['usl']:g} {p['unit']}"


# ─────────────────────────────────────────────────────────────
# 2. 이상 판정
# ─────────────────────────────────────────────────────────────
def near_margin(p: dict) -> float:
    lo = p["lsl"] if p["lsl"] is not None else 0.0
    return (p["usl"] - lo) * NEAR_RATIO


def analyze(values: pd.Series, p: dict) -> pd.DataFrame:
    """값 시계열 → 값 + 4가지 경고 플래그 DataFrame."""
    v = values.astype(float)
    lsl, usl, m = p["lsl"], p["usl"], near_margin(p)

    spec = v > usl
    near = (v <= usl) & (v >= usl - m)
    if lsl is not None:
        spec |= v < lsl
        near |= (v >= lsl) & (v <= lsl + m)

    run_id = (v.diff().fillna(1) != 0).cumsum()
    hold = v.groupby(run_id).transform("size") >= HOLD_MIN

    roll_std = v.rolling(STD_WINDOW, min_periods=STD_WINDOW // 2).std()
    stdx = roll_std > p["std_limit"]

    return pd.DataFrame(
        {"value": v, "std": roll_std, "spec": spec, "near": near, "hold": hold, "stdx": stdx}
    )


# ─────────────────────────────────────────────────────────────
# 3. 데모 데이터
# ─────────────────────────────────────────────────────────────
# (kind, 길이(분), 인자, 끝에서 떨어진 위치(분))
#  drift : 지금까지 서서히 arg 로 이동   bump : 과거에 arg 까지 솟았다 복귀
#  hold  : arg 값으로 고정              noisy : ±arg 만큼 요동
ANOMALIES: dict[Key, tuple] = {
    ("1동(메인)", "유기폐수", "A계열", "pH"):  ("drift", 60, 8.38, 0),    # 상한 근접
    ("1동(메인)", "유기폐수", "B계열", "DO"):  ("drift", 50, 1.3, 0),     # 하한 이탈
    ("1동(메인)", "무기폐수", "A계열", "DO"):  ("hold", 90, 3.42, 0),     # Hold
    ("1동(메인)", "무기폐수", "A계열", "F"):   ("bump", 120, 15.4, 100),  # 과거 상한 이탈(해소)
    ("2동(신관)", "불산", "A계열", "F"):       ("noisy", 60, 6.0, 0),     # 표준편차 초과
    ("2동(신관)", "불산", "B계열", "처리량"):  ("hold", 70, 118.4, 0),    # Hold
    ("2동(신관)", "고농도", "A계열", "COD"):   ("drift", 60, 37.8, 0),    # 상한 근접
}


def _ar1(rng: np.random.Generator, n: int, mu: float, sigma: float, phi: float = 0.98) -> np.ndarray:
    eps = rng.normal(0, sigma * np.sqrt(1 - phi**2), n)
    x = np.empty(n)
    x[0] = mu
    for t in range(1, n):
        x[t] = mu + phi * (x[t - 1] - mu) + eps[t]
    return x


def _apply(x: np.ndarray, kind: str, n: int, arg: float, off: int, rng: np.random.Generator):
    end = len(x) - off
    sl = slice(end - n, end)
    if kind == "drift":
        x[sl] = np.linspace(x[sl.start], arg, n) + rng.normal(0, 0.003 * abs(arg), n)
    elif kind == "bump":
        shape = np.sin(np.pi * np.arange(n) / (n - 1)) ** 2
        x[sl] = x[sl] + shape * (arg - x[sl].mean())
    elif kind == "noisy":
        x[sl] = x[sl] + rng.uniform(-arg, arg, n)
    elif kind == "hold":
        x[sl] = arg


@st.cache_data(show_spinner=False)
def load_data() -> dict[Key, pd.DataFrame]:
    end = pd.Timestamp.now().floor("min")
    idx = pd.date_range(end=end, periods=N_MIN, freq="min")
    rng = np.random.default_rng(7)

    data = {}
    for key in all_keys():
        p = PARAMS[key[3]]
        mu = p["base"] + rng.normal(0, p["sigma"] * 0.3)
        x = _ar1(rng, N_MIN, mu, p["sigma"])
        if key in ANOMALIES:
            kind, n, arg, off = ANOMALIES[key]
            _apply(x, kind, n, arg, off, rng)
        x = np.round(np.clip(x, 0, None), 2)
        data[key] = analyze(pd.Series(x, index=idx), p)
    return data


# ─────────────────────────────────────────────────────────────
# 4. 요약 / 경고 목록
# ─────────────────────────────────────────────────────────────
def active_kinds(df: pd.DataFrame) -> list[str]:
    last = df.iloc[-1]
    return sorted([k for k, c in FLAG_COL.items() if bool(last[c])], key=lambda k: KIND[k]["rank"])


def window_kinds(df: pd.DataFrame, lookback: int) -> list[str]:
    w = df.iloc[-lookback:]
    return sorted([k for k, c in FLAG_COL.items() if w[c].any()], key=lambda k: KIND[k]["rank"])


def alert_events(data: dict[Key, pd.DataFrame], lookback: int) -> pd.DataFrame:
    """조회 구간 안에서 한 번이라도 걸린 (센서, 유형) 별 이벤트 1행."""
    rows = []
    for key, df in data.items():
        w = df.iloc[-lookback:]
        p = PARAMS[key[3]]
        for kind, col in FLAG_COL.items():
            m = w[col]
            if not m.any():
                continue
            times = w.index[m.values]
            rows.append(
                dict(
                    key=key,
                    kind=kind,
                    active=bool(df[col].iloc[-1]),
                    rank=KIND[kind]["rank"],
                    first=times[0],
                    last=times[-1],
                    minutes=int(m.sum()),
                    now=float(df["value"].iloc[-1]),
                    unit=p["unit"],
                    spec=spec_text(p),
                )
            )
    ev = pd.DataFrame(rows)
    if ev.empty:
        return ev
    return ev.sort_values(["active", "rank", "last"], ascending=[False, True, False]).reset_index(drop=True)

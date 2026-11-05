"""데이터 접근: 현재 데이터(Plant)와 '데이터 버전'.

사내 적용: 윈도우 스케줄러가 5분마다 결과 파일을 갱신하면 환경변수 WWTP_DATA_FILE 에 그 경로를 지정.
파일 수정 시각이 바뀔 때만 버전이 바뀌고, 그때만 화면의 해당 부분이 다시 그려짐 (dcc.Interval + dcc.Store).
get_plant() 가 그 파일을 읽도록 교체하는 건 core.py 의 몫 (HANDOFF.md 4-2).
"""
from __future__ import annotations

import os
from functools import lru_cache

import core

DATA_FILE = os.environ.get("WWTP_DATA_FILE")


def _mtime() -> float:
    try:
        return os.path.getmtime(DATA_FILE) if DATA_FILE else 0.0
    except OSError:
        return 0.0


_last_mtime = _mtime()


def plant():
    """파일이 바뀌었으면 캐시를 비우고 다시 읽음 (데모 데이터에서는 항상 같은 객체)."""
    global _last_mtime
    m = _mtime()
    if m != _last_mtime:
        _last_mtime = m
        core.get_plant.cache_clear()
        incs.cache_clear()
    return core.get_plant()


def version() -> str:
    p = plant()
    return f"{p.idx[-1]:%Y-%m-%d %H:%M}|{_last_mtime}"


@lru_cache(maxsize=32)
def incs(ver: str, window: int) -> list[dict]:
    """사고 목록 (같은 데이터 버전·구간이면 한 번만 계산해서 모든 콜백이 공유)."""
    return core.incidents(plant(), window)

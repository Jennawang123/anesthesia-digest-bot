"""匯率換算測試。換算邏輯離線測，取匯率另有 --live 測試。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fx_rate import fetch_krw_twd, to_twd  # noqa: E402


def test_換算取整數():
    # 1,774,600 KRW × 0.022492 = 39,914.3032
    assert to_twd(1774600, 0.022492) == 39914


def test_換算四捨五入():
    assert to_twd(100, 0.5) == 50
    assert to_twd(101, 0.5) == 51


def test_匯率為None時回傳None():
    assert to_twd(1774600, None) is None


@pytest.mark.live
def test_實際取得匯率():
    rate, fetched_at = fetch_krw_twd()
    # KRW→TWD 合理範圍，2026-08 實測為 0.0225
    assert 0.015 < rate < 0.035
    assert fetched_at

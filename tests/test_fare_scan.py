"""批次掃描的調度與中止邏輯測試。

不碰 Playwright：run_workers 接受注入的 scan 函式，
純粹驗證並行、節流與「連續查無結果即中止」的行為。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fare_scan import run_workers  # noqa: E402


def _run(todo, scan, handle=None, **kw):
    calls = []
    saved = []

    async def wrapped(combo):
        calls.append(combo["id"])
        return scan(combo)

    def save(combo, result):
        saved.append((combo["id"], result))

    c = asyncio.run(run_workers(todo, wrapped, handle or save,
                                delay=0, progress_every=0, **kw))
    return c, calls, saved


def _combos(n):
    return [{"id": f"c{i}", "legs": []} for i in range(n)]


def test_全部有票時掃完所有組合():
    c, calls, saved = _run(_combos(30), lambda x: {"status": "ok",
                                                   "priceKRW": 1})
    assert len(calls) == 30
    assert c["ok"] == 30
    assert c["aborted"] is False


def test_連續查無結果達門檻即中止():
    # 排隊中的 worker 必須在醒來後再檢查一次中止旗標，
    # 否則 gather 早就把全部 worker 放行了（2026-08-20 實際踩過：
    # 連續 200 組空白仍繼續掃，全被誤記成 no_result）
    c, calls, saved = _run(_combos(200), lambda x: {"status": "no_result"},
                           empty_abort=15, concurrency=2)
    assert c["aborted"] is True
    assert len(calls) < 40, f"中止後仍掃了 {len(calls)} 組"


def test_中止前已取得的結果仍會落地():
    c, calls, saved = _run(_combos(100), lambda x: {"status": "no_result"},
                           empty_abort=15, concurrency=2)
    assert len(saved) == len(calls)


def test_有票會把連續空白計數歸零():
    # 間歇性查無票不該中止：每隔一組就有票
    def scan(combo):
        n = int(combo["id"][1:])
        return {"status": "ok", "priceKRW": 1} if n % 2 else {
            "status": "no_result"}

    c, calls, saved = _run(_combos(100), scan, empty_abort=15, concurrency=1)
    assert c["aborted"] is False
    assert len(calls) == 100


def test_連續查詢失敗也會中止():
    # 斷網時每組要等 60 秒逾時，不中止就白跑幾百組
    c, calls, saved = _run(_combos(200),
                           lambda x: {"status": "error", "error": "斷線"},
                           error_abort=15, concurrency=2)
    assert c["aborted"] is True
    assert len(calls) < 40, f"中止後仍掃了 {len(calls)} 組"


def test_有票會同時重置兩種連續計數():
    # 只要還查得到票就代表鏈路正常，兩種異常計數都該歸零
    def scan(combo):
        n = int(combo["id"][1:])
        if n % 10 == 0:
            return {"status": "ok", "priceKRW": 1}
        return {"status": "error"} if n % 20 < 10 else {"status": "no_result"}

    c, calls, saved = _run(_combos(100), scan, empty_abort=15,
                           error_abort=15, concurrency=1)
    assert c["aborted"] is False
    assert len(calls) == 100


def test_網路未就緒時會等待重試():
    # launchd 在 09:30 觸發時機器常剛喚醒、Wi-Fi 還沒連上
    from fare_scan import wait_for_network
    seq = iter([False, False, True])
    slept = []
    assert wait_for_network(probe=lambda: next(seq), tries=5, interval=60,
                            sleep=slept.append) is True
    assert slept == [60, 60]


def test_網路一直不通就放棄():
    from fare_scan import wait_for_network
    slept = []
    assert wait_for_network(probe=lambda: False, tries=3, interval=60,
                            sleep=slept.append) is False
    assert len(slept) == 2      # 最後一次失敗後不必再等


def test_網路本來就通不會等待():
    from fare_scan import wait_for_network
    slept = []
    assert wait_for_network(probe=lambda: True, sleep=slept.append) is True
    assert slept == []

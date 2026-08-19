"""掃描組合產生測試。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fare_combos import (PHASE1, PHASE2, PHASE3, PHASE4, combo_id,  # noqa: E402
                         date_windows, generate)

PHASE1 = {
    "asia_in": ["ICN", "PUS"],
    "asia_out": ["ICN", "PUS"],
    "long_haul": ["VIE", "MXP"],
    "windows": {
        "leg1": ("2026-12-21", "2026-12-23"),
        "leg2": ("2027-02-25", "2027-02-27"),
        "leg3": ("2027-03-05", "2027-03-08"),
        "leg4": ("2027-04-14", "2027-04-16"),
    },
}


def test_日期窗展開為每日清單():
    assert date_windows("2026-12-21", "2026-12-23") == [
        "2026-12-21", "2026-12-22", "2026-12-23"]


def test_四天窗展開四天():
    assert len(date_windows("2027-03-05", "2027-03-08")) == 4


def test_phase1總組合數為864():
    # 城市對 2×2=4，目的地 2，日期 3×3×4×3=108 → 4×2×108 = 864
    assert len(generate(PHASE1)) == 864


def test_每組合為四段且首段飛台北():
    combos = generate(PHASE1)
    for c in combos[:20]:
        assert len(c["legs"]) == 4
        assert c["legs"][0][2] == "TPE"
        assert c["legs"][1][1] == "TPE"
        assert c["legs"][3][1] == "TPE"


def test_長程段來回為同一目的地():
    for c in generate(PHASE1)[:20]:
        assert c["legs"][1][2] == c["legs"][2][1]


def test_combo_id穩定且唯一():
    combos = generate(PHASE1)
    ids = [c["id"] for c in combos]
    assert len(set(ids)) == len(ids)
    # 同樣輸入必須得到同樣 id，否則重複掃描會產生重複記錄
    assert combo_id(combos[0]["legs"]) == combos[0]["id"]


def test_phase2為美西且不含SEA():
    assert PHASE2["long_haul"] == ["LAX", "SFO"]
    assert "SEA" not in PHASE2["long_haul"]


def test_phase2總組合數為864():
    # 城市對 2×2=4，目的地 2，日期 108 → 864
    assert len(generate(PHASE2)) == 864


def test_phase2與phase1的組合id不重疊():
    # 兩階段結果存在同一個檔案，id 不可碰撞
    ids1 = {c["id"] for c in generate(PHASE1)}
    ids2 = {c["id"] for c in generate(PHASE2)}
    assert not (ids1 & ids2)


def test_phase2日期窗與phase1相同():
    assert PHASE2["windows"] == PHASE1["windows"]


def test_phase3為泰國進出且涵蓋全部長程點():
    # BKK 只有一個機場，泰國進出只有 BKK→BKK 一種 open-jaw
    assert PHASE3["asia_in"] == ["BKK"]
    assert PHASE3["asia_out"] == ["BKK"]
    assert PHASE3["long_haul"] == ["VIE", "MXP", "AMS", "LAX", "SFO"]


def test_phase3總組合數為540():
    # 城市對 1×1=1，目的地 5，日期 108 → 540
    assert len(generate(PHASE3)) == 540


def test_phase4為韓國進出加AMS():
    # AMS 補進既有的韓國進出，不重掃已有的 VIE/MXP/LAX/SFO
    assert PHASE4["asia_in"] == ["ICN", "PUS"]
    assert PHASE4["long_haul"] == ["AMS"]


def test_phase4總組合數為432():
    # 城市對 2×2=4，目的地 1，日期 108 → 432
    assert len(generate(PHASE4)) == 432


def test_新增兩階段與既有階段id皆不重疊():
    # 四個階段共用同一個結果檔，id 不可碰撞
    sets = [{c["id"] for c in generate(cfg)}
            for cfg in (PHASE1, PHASE2, PHASE3, PHASE4)]
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            assert not (sets[i] & sets[j])


def test_新增兩階段的日期窗沿用phase1():
    assert PHASE3["windows"] == PHASE1["windows"]
    assert PHASE4["windows"] == PHASE1["windows"]


def test_腿1出發地與腿4目的地同國():
    # 境外票的前提：回到出發國才構成 open-jaw
    for cfg, group in ((PHASE3, {"BKK"}), (PHASE4, {"ICN", "PUS"})):
        for c in generate(cfg):
            assert c["legs"][0][1] in group
            assert c["legs"][3][2] in group

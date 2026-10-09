"""關鍵字篩選測試。標題皆為實抓樣本。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from points_watch import sources  # noqa: E402

PASS = [
    "Buy IHG Points for as low as 0.5 cents each",
    "Buy Alaska Atmos Rewards Points With 100% Bonus (1.88 Cents Each): Worth It?",
    "IHG Buy Points Buy Points 100% Bonus Sale Through February 5, 2026",
    "Alaska Airlines Buy Miles Up To 120% Bonus Sale Until October 19, 2026",
    "Buy Choice Privileges Points At 40% Off: 0.62 Cents Each, Worth It?",
    # 以下兩則不是買點促銷，但關鍵字層擋不掉，交給 Haiku 判否
    "Alaska Atmos Rewards’ Global Getaways Award Sale: Save Up To 50%",
    "Last Chance Deals: IHG points sale, United portal promo, Hotels.com gift card discount, & more",
]

BLOCK = [
    "Hilton Honors Buy Points 120% Bonus Sale + Increased Limit October 7 – November 21, 2026",
    "Buy Marriott points for as low as 0.81 cents each",
    "IHG One Rewards Premier Select Credit Card Review: Is The $350 Annual Fee Worth It?",
    "100% transfer bonus from Wyndham Rewards to United MileagePlus",
    "Marriott Bonvoy To Air Canada Aeroplan 15% Points Transfer Bonus: Worth It?",
    "(EXPIRED) Buy Choice Points, get 40% bonus (0.74c per point)",
    "Chase IHG One Rewards Credit Card Eligibility Rules Explained",
    "Southwest sale: Save up to 40% on cash & award flights",
]


@pytest.mark.parametrize("title", PASS)
def test_candidate(title):
    assert sources.is_candidate(title)


@pytest.mark.parametrize("title", BLOCK)
def test_not_candidate(title):
    assert not sources.is_candidate(title)


def test_nine_programs():
    assert set(sources.PROGRAMS) == {
        "IHG", "CHOICE", "LIFEMILES", "AEROPLAN", "UNITED",
        "ALASKA", "AA", "FLYINGBLUE", "VIRGIN",
    }


def test_feed_urls_paginate():
    feed = {"name": "x", "url": "https://x.test/feed/"}
    assert sources.feed_urls(feed, 2) == [
        "https://x.test/feed/", "https://x.test/feed/?paged=2",
    ]

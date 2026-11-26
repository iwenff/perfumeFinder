import pytest

from app.services.perfume_parser import parse
from app.utils.price import extract_price
from app.utils.text import normalize


@pytest.mark.parametrize(("text", "expected"), [
    ("1 850 ₽", (1850, "RUB")), ("RUB 1\u202f850,50", (1850.5, "RUB")),
    ("1850 рублей", (1850, "RUB")), ("€ 75.50", (75.5, "EUR")),
    ("1.850,50 ₽", (1850.5, "RUB")), ("USD 1,850.50", (1850.5, "USD")),
    ("1200 ₽ или 1500 ₽", None), ("скидка 15%", None),
])
def test_price(text, expected):
    assert extract_price(text) == expected


@pytest.mark.parametrize("volume", ["10 мл", "10мл", "10 ml", "10ml"])
def test_volume(volume):
    offer, = parse(f"Tom Ford Oud Wood {volume} — 1 850 ₽", "tom ford oud wood", 10)
    assert (offer.volume, offer.price) == (10, 1850)


def test_normalization():
    assert normalize("  ＴＯＭ   Ford, Oud-Wood! ") == "tom ford oud wood"
    offer, = parse("TOM, FORD  OUD-WOOD 7,5ml — 1000", "Tom Ford Oud Wood", 7.5)
    assert offer.price == 1000


def test_multiple_perfumes_and_volumes():
    caption = """Tom Ford Oud Wood
    2 мл — 550 ₽; 10 мл — 1850 ₽
    Dior Sauvage
    10 мл — 1200 ₽"""
    assert [offer.price for offer in parse(caption, "Tom Ford Oud Wood", None)] == [550, 1850]
    assert [offer.price for offer in parse(caption, "Dior Sauvage", 10)] == [1200]
    prices = parse("Oud Wood 5ml — 900 ₽ / 10ml — 1750 ₽", "Oud Wood", None)
    assert [offer.price for offer in prices] == [900, 1750]


def test_uncertain_price_never_taken_from_another_perfume():
    text = "Oud Wood 10мл / Dior Sauvage 30мл — 4000 ₽"
    assert parse(text, "Oud Wood", 10)[0].price is None
    assert parse(text, "Oud Wood", 30) == []
    assert parse("Oud Wood и Dior Sauvage 10мл — 4000 ₽", "Oud Wood", 10) == []
    assert parse("Oud Wood 10мл: от 500 ₽", "Oud Wood", 10)[0].price is None


def test_price_before_volume_and_unknown_volume():
    assert parse("Oud Wood: 900 ₽ за 5ml", "Oud Wood", 5)[0].price == 900
    assert parse("Oud Wood в наличии", "Oud Wood", None)[0].volume is None


def test_comma_separated_offers_with_distinct_prices():
    text = "Oud Wood 10мл — 1850 ₽, Dior Sauvage 10мл — 500 ₽"
    assert parse(text, "Oud Wood", None)[0].price == 1850
    assert parse(text, "Dior Sauvage", None)[0].price == 500
    assert len(parse(text, "Oud Wood", None)) == 1


def test_continued_row_belongs_to_the_last_fragrance():
    text = "Oud Wood 10мл — 1850 ₽, Dior Sauvage 30мл — 500 ₽\n50 мл — 1000 ₽"
    assert [offer.volume for offer in parse(text, "Oud Wood", None)] == [10]
    assert [offer.volume for offer in parse(text, "Dior Sauvage", None)] == [30, 50]

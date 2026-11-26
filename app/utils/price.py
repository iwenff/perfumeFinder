import re

AMOUNT = (
    r"(?:\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?"
    r"|\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?"
    r"|(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:[.,]\d{1,2})?)"
)
CURRENCY = r"(?:₽|руб(?:лей|ля|ль)?\.?(?!\w)|р\.?(?!\w)|RUB\b|€|\$|EUR\b|USD\b)"
PRICE = re.compile(
    rf"(?<![\d.,])(?:(?P<amount>{AMOUNT})\s*(?P<unit>{CURRENCY})"
    rf"|(?P<prefix>{CURRENCY})\s*(?P<number>{AMOUNT})(?![\d.,]))", re.I
)
BARE = re.compile(rf"\s*[:=—–-]\s*(?P<amount>{AMOUNT})\s*[.!]?\s*$")


def amount(raw: str, *, grouped_price: bool = False) -> float:
    value = "".join(raw.split())
    value = re.sub(r"(?<=\d)[.,](?=\d{3}(?:[.,]|$))", "", value) if grouped_price else value
    return float(value.replace(",", "."))


def extract_price(text: str, *, bare: bool = False) -> tuple[float, str] | None:
    matches = list(PRICE.finditer(text))
    if len(matches) == 1:
        match = matches[0]
        value = amount(match["amount"] or match["number"], grouped_price=True)
        unit = (match["unit"] or match["prefix"]).casefold()
        currency = {"€": "EUR", "eur": "EUR", "$": "USD", "usd": "USD"}.get(unit, "RUB")
        return (value, currency) if value > 0 else None
    if not matches and bare and (match := BARE.fullmatch(text)):
        value = amount(match["amount"], grouped_price=True)
        if value > 0:
            return value, "RUB"
    return None

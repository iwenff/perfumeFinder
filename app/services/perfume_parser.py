import re
import unicodedata
from dataclasses import dataclass

from app.utils.price import BARE, PRICE, amount, extract_price
from app.utils.text import normalize

VOLUME = re.compile(r"(?<![\w.,])(?P<value>\d+(?:[.,]\d+)?)\s*(?:мл|ml)\b", re.I)
SEPARATOR = re.compile(r"[;|•\n]+")
FIRST_VOLUME = re.compile(r"^[\s:;,/()\[\]–—-]*(?:(?:отливант|пробник|флакон)\s*[:–—-]?\s*)?$", re.I)
LIST_BOUNDARY = re.compile(
    r"[,/]\s+(?!(?:или|либо|за|по|от|до|вместо)\b)(?=[^\W\d_])", re.I,
)
VOLUME_ROW = re.compile(r"^[\s\-–—•*🧴💧]*(?:отливант\s+)?$", re.I)


@dataclass(frozen=True)
class Parsed:
    name: str
    volume: float | None
    price: float | None
    currency: str | None
    snippet: str


def parse(text: str, query: str, requested: float | None) -> list[Parsed]:
    words = normalize(query).split()
    if not words:
        return []
    pattern = re.compile(r"(?<![^\W_])" + r"[\W_]+".join(map(re.escape, words))
                         + r"(?![^\W_])")
    offers = []
    current = None
    pending = None
    # Keep original spans, including for Unicode case-fold expansions.
    for segment in SEPARATOR.split(text):
        original = segment.strip()
        line = unicodedata.normalize("NFKC", original)
        if not line:
            continue
        names = list(pattern.finditer(line.casefold()))
        if names:
            offsets = [index for index, char in enumerate(line) for _ in char.casefold()]
            for index, match in enumerate(names):
                start = offsets[match.start()]
                end = offsets[match.end() - 1] + 1
                stop = offsets[names[index + 1].start()] if index + 1 < len(names) else len(line)
                current = line[start:end]
                tail = line[end:stop]
                volumes = list(VOLUME.finditer(tail))
                prefix = tail[:volumes[0].start()] if volumes else ""
                before = _price_before_volume(prefix)
                snippet = original[max(0, start - 15):]
                if volumes and (FIRST_VOLUME.fullmatch(prefix) or before):
                    items, can_continue = _volume_offers(current, tail, snippet, volumes, requested, before)
                    offers.extend(items)
                    if not can_continue:
                        current = None
                    pending = None
                else:
                    pending = Parsed(current, None, None, None, snippet[:280])
                    if volumes:
                        current = None
            continue

        volumes = list(VOLUME.finditer(line))
        if current and volumes and VOLUME_ROW.fullmatch(line[:volumes[0].start()]):
            pending = None
            items, can_continue = _volume_offers(current, line, original, volumes, requested)
            offers.extend(items)
            if not can_continue:
                current = None
        else:
            if pending and requested is None:
                offers.append(pending)
            current = pending = None
    if pending and requested is None:
        offers.append(pending)
    return offers


def _volume_offers(name, text, snippet, volumes, requested, before=None):
    items = []
    for index, match in enumerate(volumes):
        volume = amount(match["value"])
        end = volumes[index + 1].start() if index + 1 < len(volumes) else len(text)
        tail = text[match.end():end].strip(" ,/\t")
        boundary = LIST_BOUNDARY.search(tail) if index + 1 < len(volumes) else None
        field = tail[:boundary.start()] if boundary else tail
        explicit = _price_field(field)
        if index == 0 and before:
            if not tail.strip(" )]"):
                explicit = before
            elif explicit != before:
                explicit = None
        if volume > 0 and (requested is None or volume == requested):
            price, currency = explicit or (None, None)
            items.append(Parsed(name, volume, price, currency, snippet.strip()[:280]))
        # An unrecognized field between two volumes can contain another
        # fragrance name. Stop attributing volumes to this fragrance there.
        if boundary or (tail.strip(" ()[]:.–—-") and not _price_field(tail)):
            return items, False
    return items, True


def _price_field(tail: str):
    field = re.sub(r"^\s*[:=—–-]\s*", "", tail).strip(" ()[]").rstrip("!.")
    if BARE.fullmatch(tail):
        return extract_price(tail, bare=True)
    if PRICE.fullmatch(field):
        return extract_price(field)
    return None


def _price_before_volume(prefix):
    match = re.fullmatch(r"\s*(.*?)\s+за\s+", prefix, re.I)
    return _price_field(match[1]) if match else None

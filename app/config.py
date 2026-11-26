import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
DATA = ROOT / "data"

PATTERNS = {
    "BOT_TOKEN": r"[1-9][0-9]*:[A-Za-z0-9_-]{20,}",
    "API_ID": r"[1-9][0-9]{0,9}",
    "API_HASH": r"[a-fA-F0-9]{32}",
    "OWNER_ID": r"[1-9][0-9]{0,15}",
}


class ConfigurationError(Exception):
    pass


def valid(key: str, value: str | None) -> bool:
    if not value or not re.fullmatch(PATTERNS[key], value):
        return False
    return key != "API_ID" or int(value) < 2**31


@dataclass(frozen=True)
class Config:
    bot_token: str = field(repr=False)
    api_id: int | None
    api_hash: str | None = field(repr=False)
    owner_id: int

    @classmethod
    def load(cls):
        import os

        saved = dotenv_values(ENV, interpolate=False)
        values = {key: os.environ.get(key, saved.get(key)) for key in PATTERNS}
        required = ["BOT_TOKEN", "OWNER_ID"]
        if values["API_ID"] or values["API_HASH"]:
            required.extend(("API_ID", "API_HASH"))
        invalid = [key for key in required if not valid(key, values[key])]
        if invalid:
            raise ConfigurationError("Заполните настройки: " + ", ".join(invalid))
        return cls(values["BOT_TOKEN"], int(values["API_ID"]) if values["API_ID"] else None,
                   values["API_HASH"], int(values["OWNER_ID"]))

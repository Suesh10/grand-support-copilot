"""База правил: загрузка, канонические идентификаторы пунктов и проверка цитат.

Номер пункта сам по себе неоднозначен («1.1» есть в десяти разделах), поэтому
каждый пункт получает канонический id «<номер> <раздел>», например «2.1 ОП».
Это главный барьер от галлюцинаций: процитировать можно только то, что есть здесь.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache

from . import config

# id раздела в rules.json → сокращение, как его пишут админы.
SECTION_CODES = {
    30: "ОП",    # Общие правила игры
    31: "ЖБ",    # Правила жалоб
    32: "GZ",    # Зелёная зона
    33: "ПЛ",    # Лидеры и заместители
    34: "ПГО",   # Государственные организации
    35: "ПГВ",   # Государственная волна и департамент
    36: "ПСМ",   # Семейные мероприятия
    40: "ОПГ",   # Правила для ОПГ
    41: "ПВБ",   # Война за бизнес
    42: "ПБФ",   # Битва за фургон
}

# Как игроки и админы пишут раздел → каноническое сокращение.
SECTION_ALIASES = {
    "ОП": "ОП", "OP": "ОП", "ОР": "ОП", "ОБЩИХ": "ОП",
    "ЖБ": "ЖБ", "JB": "ЖБ",
    "GZ": "GZ", "ГЗ": "GZ", "ЗЗ": "GZ",
    "ПГО": "ПГО", "PGO": "ПГО",
    "ОПГ": "ОПГ", "OPG": "ОПГ",
}

REF_RE = re.compile(
    r"(?<![\d.])(\d{1,2}(?:\.\d{1,2}){1,2})\s*(?:пункт[а-я]*\s*)?"
    r"(ОП|OP|ОР|ЖБ|JB|GZ|ГЗ|ЗЗ|ПГО|PGO|ОПГ|OPG)?(?![А-Яа-яA-Za-z])",
    re.I,
)


@dataclass(frozen=True)
class RulePoint:
    ref: str          # канонический id: «2.1 ОП»
    number: str       # «2.1»
    section: str      # «ОП»
    section_title: str
    text: str


@lru_cache(maxsize=1)
def load_points() -> dict[str, RulePoint]:
    data = json.loads(config.RULES_PATH.read_text(encoding="utf-8"))
    points: dict[str, RulePoint] = {}
    for rule in data["rules"]:
        code = SECTION_CODES.get(rule["id"])
        if not code:
            continue
        for p in rule.get("points", []):
            ref = f"{p['ref']} {code}"
            points[ref] = RulePoint(ref, p["ref"], code, rule["category"], p["text"])
    return points


def parse_refs(text: str, default_section: str = "ОП") -> list[str]:
    """Достать из свободного текста ссылки на пункты и привести к каноническому виду.

    Без указания раздела считаем, что это общие правила: так пишут почти все игроки.
    Возвращаются только существующие пункты.
    """
    points = load_points()
    found: list[str] = []
    for number, section in REF_RE.findall(text or ""):
        code = SECTION_ALIASES.get(section.upper(), default_section) if section else default_section
        ref = f"{number} {code}"
        if ref in points and ref not in found:
            found.append(ref)
    return found


def is_valid_ref(ref: str) -> bool:
    return ref in load_points()


def filter_valid(refs: list[str]) -> list[str]:
    """Оставить только существующие пункты, без повторов."""
    seen: list[str] = []
    for r in refs:
        r = r.strip()
        if is_valid_ref(r) and r not in seen:
            seen.append(r)
    return seen

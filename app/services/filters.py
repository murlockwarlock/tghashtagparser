import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Keyword
from app.utils.text import normalize_text

MATCH_BOUNDARY = r"(?<![\wа-яё]){}(?![\wа-яё])"




@dataclass(frozen=True)
class FilterResult:
    status: str
    reason: str
    priority: str | None = None
    label: str | None = None

    def __iter__(self):
        yield self.status
        yield self.reason
        yield self.priority
        yield self.label

    def __getitem__(self, index: int):
        return (self.status, self.reason, self.priority, self.label)[index]


def list_keywords(db: Session, kind: str) -> list[Keyword]:
    return db.query(Keyword).filter(Keyword.kind == kind).order_by(Keyword.word.asc()).all()


def add_keyword(db: Session, kind: str, word: str) -> Keyword:
    normalized = normalize_text(word)
    item = db.query(Keyword).filter(Keyword.kind == kind, Keyword.word == normalized).first()
    if item:
        item.is_active = True
        return item
    item = Keyword(kind=kind, word=normalized, is_active=True)
    db.add(item)
    db.flush()
    return item


def remove_keyword(db: Session, kind: str, word: str) -> bool:
    normalized = normalize_text(word)
    item = db.query(Keyword).filter(Keyword.kind == kind, Keyword.word == normalized).first()
    if not item:
        return False
    item.is_active = False
    return True


def keyword_matches(text: str, keyword: str) -> bool:
    escaped = re.escape(normalize_text(keyword))
    pattern = MATCH_BOUNDARY.format(escaped)
    return re.search(pattern, text) is not None


def first_match(text: str, words: tuple[str, ...]) -> str | None:
    for word in words:
        if keyword_matches(text, word):
            return normalize_text(word)
    return None


def has_match(text: str, words: tuple[str, ...]) -> bool:
    return first_match(text, words) is not None


def classify_text(db: Session, text: str) -> FilterResult:
    normalized = normalize_text(text)
    # Fetch all active keywords grouped by kind
    active_keywords = db.query(Keyword).filter(Keyword.is_active.is_(True)).all()
    keywords_by_kind = {}
    for kw in active_keywords:
        keywords_by_kind.setdefault(kw.kind, []).append(kw.word)

    custom_exclude = keywords_by_kind.get("exclude", [])
    custom_include = keywords_by_kind.get("include", [])
    hard_spam_words = keywords_by_kind.get("hard_spam", [])
    result_report_words = keywords_by_kind.get("result_report", [])
    direction_words = keywords_by_kind.get("direction", [])
    entry_words = keywords_by_kind.get("entry", [])
    target_words = keywords_by_kind.get("target", [])
    stop_words = keywords_by_kind.get("stop_loss", [])
    setup_words = keywords_by_kind.get("setup", [])

    spam_word = first_match(normalized, tuple(hard_spam_words))
    if spam_word:
        return FilterResult("filtered_out", f"hard_spam_{spam_word.replace(' ', '_')}")
    if any(keyword_matches(normalized, word) for word in custom_exclude):
        return FilterResult("filtered_out", "hard_spam_custom")

    report_word = first_match(normalized, tuple(result_report_words))
    if report_word:
        return FilterResult("filtered_out", f"result_report_{report_word.replace(' ', '_')}")



    has_direction = has_match(normalized, tuple(direction_words))
    has_entry = has_match(normalized, tuple(entry_words))
    has_target = has_match(normalized, tuple(target_words))
    has_stop = has_match(normalized, tuple(stop_words))
    has_setup = has_match(normalized, tuple(setup_words))

    if has_direction and has_entry and has_target and has_stop:
        return FilterResult("candidate", "has direction + entry + target + stop loss", "high")
    if has_direction and has_entry and has_target:
        return FilterResult("candidate", "has direction + entry + target", "medium")
    if has_direction and has_target:
        return FilterResult("candidate", "has direction + target, no clear entry", "low")
    if has_direction and has_entry and has_setup:
        return FilterResult("candidate", "has direction + entry + setup", "low")
    if not has_direction:
        return FilterResult("filtered_out", "no_direction")
    return FilterResult("filtered_out", "no_entry_no_target")

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class Page:
    items: list
    page: int
    total_pages: int
    total: int


def paginate(items: list, page: int = 1, per_page: int = 10) -> Page:
    total = len(items)
    total_pages = max(1, ceil(total / per_page))
    normalized = ((page - 1) % total_pages) + 1
    start = (normalized - 1) * per_page
    return Page(
        items=items[start:start + per_page],
        page=normalized,
        total_pages=total_pages,
        total=total,
    )

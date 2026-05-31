from app.utils.pagination import paginate


def test_pagination_wraps_pages() -> None:
    page = paginate(list(range(25)), page=4, per_page=10)
    assert page.page == 1
    assert page.items == list(range(10))

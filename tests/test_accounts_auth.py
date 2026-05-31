from app.bot.handlers.accounts import normalize_login_code


def test_normalize_login_code_removes_spaces_and_symbols() -> None:
    assert normalize_login_code("12 345") == "12345"
    assert normalize_login_code("1-2-3-4-5") == "12345"

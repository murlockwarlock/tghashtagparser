from pathlib import Path


def test_form_back_buttons_return_to_parent_sections() -> None:
    root = Path(__file__).resolve().parents[1]
    files = {
        "app/bot/handlers/accounts.py": [
            'back("menu:accounts")',
            'back("menu:proxies")',
        ],
        "app/bot/handlers/settings.py": [
            'back("menu:settings")',
            'back("menu:ai")',
            'back("menu:bingx")',
            'back("menu:channels")',
        ],
        "app/bot/handlers/tags.py": ['back("menu:tags")'],
        "app/bot/handlers/filters.py": ['rows.append([("Назад", "menu:filters")])'],
    }

    for relative_path, expected in files.items():
        source = (root / relative_path).read_text()
        for marker in expected:
            assert marker in source

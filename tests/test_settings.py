import pytest
from app.services.settings import get_setting, set_setting, get_int
from app.db.session import SessionLocal

@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session

def test_settings_crud(db):
    assert get_setting(db, "test_key", "default_val") == "default_val"
    assert get_int(db, "test_int", 42) == 42

    set_setting(db, "test_key", "new_val")
    assert get_setting(db, "test_key") == "new_val"

    set_setting(db, "test_int", "10")
    assert get_int(db, "test_int", 42) == 10

    set_setting(db, "test_int", "invalid")
    assert get_int(db, "test_int", 42) == 42

    # Test update
    set_setting(db, "test_key", "updated_val", is_secret=True)
    assert get_setting(db, "test_key") == "updated_val"

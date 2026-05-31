from app.services.crypto import PREFIX, decrypt_secret, encrypt_secret, mask_secret


def test_encrypt_decrypt_secret() -> None:
    encrypted = encrypt_secret("secret-value")

    assert encrypted.startswith(PREFIX)
    assert decrypt_secret(encrypted) == "secret-value"


def test_plaintext_secret_is_backward_compatible() -> None:
    assert decrypt_secret("plain") == "plain"


def test_mask_secret() -> None:
    assert mask_secret("1234567890") == "1234...7890"

"""Tests for admin authentication."""
import pytest
from app.services.admin_auth_service import (
    hash_password, verify_password, create_access_token,
    verify_token, authenticate_admin, seed_admin_user,
)
from app.core.errors import AuthenticationError


class TestPasswordHashing:
    def test_hash_not_equals_plaintext(self):
        password = "test_password_123"
        hashed = hash_password(password)
        assert hashed != password
        assert len(hashed) > 20

    def test_verify_correct_password(self):
        password = "my_secure_pass"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_different_hashes_for_same_password(self):
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2  # bcrypt uses random salt
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestJWTTokens:
    def test_create_and_verify_token(self):
        token, expires = create_access_token("admin")
        username = verify_token(token)
        assert username == "admin"

    def test_invalid_token_raises(self):
        with pytest.raises(AuthenticationError):
            verify_token("invalid.token.here")

    def test_empty_token_raises(self):
        with pytest.raises(AuthenticationError):
            verify_token("")


class TestAuthentication:
    def test_authenticate_valid_credentials(self):
        seed_admin_user()
        from app.core.config import settings
        token = authenticate_admin(settings.admin_username, settings.admin_password)
        assert token is not None
        assert len(token) > 20
        # Verify the token works
        username = verify_token(token)
        assert username == settings.admin_username

    def test_authenticate_wrong_password(self):
        seed_admin_user()
        from app.core.config import settings
        with pytest.raises(AuthenticationError):
            authenticate_admin(settings.admin_username, "wrong_password")

    def test_authenticate_unknown_user(self):
        seed_admin_user()
        with pytest.raises(AuthenticationError):
            authenticate_admin("unknown_user", "any_password")

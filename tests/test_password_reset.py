import os
import uuid
from urllib.parse import parse_qs, urlparse

from src.auth import get_password_hash, verify_password
from src.database import UserRepository
from src.password_reset import create_reset_token_for_email, reset_password_with_token

def test_password_reset_round_trip():
    username = f"reset_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    old_password = "old-pass-1"
    new_password = "new-pass-2"
    assert UserRepository.create(
        {
            "username": username,
            "email": email,
            "full_name": "",
            "hashed_password": get_password_hash(old_password),
            "role": "user",
            "plan_id": "free",
            "games_limit": 1,
            "api_quota": 1000,
            "is_active": 1,
            "is_trial": 0,
        }
    )

    found, payload = create_reset_token_for_email(email)
    assert found is True
    reset_url = payload.get("dev_reset_url") or payload.get("reset_url")
    assert reset_url
    token = parse_qs(urlparse(reset_url).query)["token"][0]

    ok, message = reset_password_with_token(token, new_password)
    assert ok is True
    assert "重置" in message

    user = UserRepository.get_by_username(username)
    assert verify_password(new_password, user["hashed_password"])
    assert not verify_password(old_password, user["hashed_password"])

    ok2, _ = reset_password_with_token(token, "another-pass")
    assert ok2 is False

    UserRepository.delete(username)

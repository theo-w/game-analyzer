import os
from src.services.mvp_storage import resolve_mvp_output_dir, safe_username, user_mvp_output_dir

def test_safe_username_normalizes_special_chars():
    assert safe_username("User.Name") == "user.name"
    assert safe_username("  ") == "anonymous"

def test_user_mvp_output_dir_is_scoped():
    path = user_mvp_output_dir("Alice")
    assert path.endswith(os.path.join("users", "alice"))

def test_resolve_mvp_output_dir_creates_user_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.services.mvp_storage.DEFAULT_OUTPUT_DIR",
        str(tmp_path / "mvp"),
    )
    out = resolve_mvp_output_dir("pilot_user")
    assert out.startswith(str(tmp_path))
    assert os.path.isdir(out)

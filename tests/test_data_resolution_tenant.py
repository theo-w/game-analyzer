import os
from src.data_resolution import get_user_comments_data

def test_user_comments_use_scoped_mvp_dir(tmp_path, monkeypatch):
    base = tmp_path / "mvp"
    user_dir = base / "users" / "alice"
    user_dir.mkdir(parents=True)
    dataset = {
        "source": "google_play_public",
        "comments": [
            {
                "product": "com.example.app",
                "product_name": "Example",
                "platform": "Google Play",
                "情绪": "positive",
                "内容": "Great game",
            }
        ],
        "metrics": [],
    }
    import json

    with open(user_dir / "steam_dataset.json", "w", encoding="utf-8") as handle:
        json.dump(dataset, handle)

    monkeypatch.setattr("src.services.mvp_storage.DEFAULT_OUTPUT_DIR", str(base))
    comments = get_user_comments_data("Alice")
    assert len(comments) == 1
    assert comments[0]["product"] == "com.example.app"

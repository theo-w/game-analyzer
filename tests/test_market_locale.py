import os
from src.services.market_locale import (
    default_market_for_channel,
    get_market_profile,
    list_markets_for_channel,
    normalize_market_country,
)

def test_normalize_market_country_defaults_by_channel():
    assert normalize_market_country("google_play", "") == "us"
    assert normalize_market_country("taptap", "") == "cn"
    assert normalize_market_country("steam", "uk") == "gb"

def test_google_play_profile_uses_country_locale():
    profile = get_market_profile("google_play", "jp")
    assert profile.country == "jp"
    assert profile.google_play_lang == "ja"
    assert profile.google_play_country == "jp"

def test_taptap_profile_switches_api_host_by_country():
    cn = get_market_profile("taptap", "cn")
    us = get_market_profile("taptap", "us")
    assert "taptap.cn" in cn.taptap_api_base
    assert "taptap.io" in us.taptap_api_base
    assert cn.taptap_xua_loc == "CN"
    assert us.taptap_xua_loc == "US"

def test_steam_profile_maps_country_to_review_language():
    profile = get_market_profile("steam", "cn")
    assert profile.steam_review_language == "schinese"

def test_list_markets_for_channel_marks_default():
    markets = list_markets_for_channel("google_play")
    assert any(item.get("default") for item in markets)
    assert default_market_for_channel("taptap") == "cn"

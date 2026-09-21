import os
import time
from unittest.mock import patch

from src.services.crawl_runner import crawl_products_parallel, throttle_page_fetch

def test_crawl_products_parallel_preserves_single_product_path():
    calls = []

    def worker(pid: str) -> str:
        calls.append(pid)
        return f"ok:{pid}"

    out = crawl_products_parallel(["730"], worker, max_workers=4)
    assert out == {"730": "ok:730"}
    assert calls == ["730"]

def test_crawl_products_parallel_runs_all_products():
    seen = []

    def worker(pid: str) -> str:
        seen.append(pid)
        return pid

    out = crawl_products_parallel(["a", "b", "c"], worker, max_workers=3)
    assert set(out.keys()) == {"a", "b", "c"}
    assert set(seen) == {"a", "b", "c"}

def test_throttle_page_fetch_sleeps_when_configured():
    with patch.dict(os.environ, {"GA_CRAWL_DELAY_SECONDS": "0.05"}, clear=False):
        start = time.monotonic()
        throttle_page_fetch()
        assert time.monotonic() - start >= 0.04

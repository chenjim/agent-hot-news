"""Regression tests for cookie loading in container layouts.

Background: in Docker, ./backend is mounted at /app, so PROJECT_ROOT
resolves to '/' and cookie.*.txt (kept at repo root on the host) was
invisible -> load_cookie() returned "" -> zhihu 401.
load_cookie() must search multiple candidate dirs.
"""
import app.utils.cookies as cookies


def test_load_cookie_finds_file_in_first_candidate(tmp_path, monkeypatch):
    (tmp_path / "cookie.zhihu.txt").write_text("  abc=123  ", encoding="utf-8")
    monkeypatch.setattr(cookies, "_candidate_dirs", lambda: [tmp_path])
    assert cookies.load_cookie("zhihu") == "abc=123"


def test_load_cookie_falls_through_to_later_candidate(tmp_path, monkeypatch):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    cookie_dir = tmp_path / "cookies"
    cookie_dir.mkdir()
    (cookie_dir / "cookie.weibo.txt").write_text("w=1", encoding="utf-8")
    monkeypatch.setattr(cookies, "_candidate_dirs", lambda: [empty_dir, cookie_dir])
    assert cookies.load_cookie("weibo") == "w=1"


def test_load_cookie_returns_empty_when_missing_everywhere(tmp_path, monkeypatch):
    monkeypatch.setattr(cookies, "_candidate_dirs", lambda: [tmp_path])
    assert cookies.load_cookie("not-exist") == ""


def test_cookie_dir_env_override_has_highest_priority(tmp_path, monkeypatch):
    override_dir = tmp_path / "override"
    override_dir.mkdir()
    (override_dir / "cookie.baidu.txt").write_text("from-env", encoding="utf-8")
    monkeypatch.setenv("COOKIE_DIR", str(override_dir))
    # _candidate_dirs must put COOKIE_DIR first even if PROJECT_ROOT exists
    assert cookies._candidate_dirs()[0] == override_dir
    assert cookies.load_cookie("baidu") == "from-env"

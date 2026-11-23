"""Tests for system-browser AnkiCollab device pairing inside AnkizinSetupWizard."""
from __future__ import annotations

import time

import requests
from aqt.qt import QScrollArea

from ankizin.onboarding import engine, wizard as wizard_mod
from ankizin.onboarding.wizard import AnkizinSetupWizard


def _new_user_info() -> dict:
    return {
        "scenario": "new",
        "settings": {"deck_key": "decke-schaufeln-reiche"},
        "deck_key": "decke-schaufeln-reiche",
        "collab_status": "missing",
        "collab_logged_in": False,
        "subscribed": False,
        "installed_did": 0,
        "collab_settings": {},
        "ankihub_decks": [],
        "tag_sources": {
            "has_collab": False,
            "has_ankihub": False,
            "has_legacy_apkg": False,
            "legacy_versions": [],
        },
        "has_content": False,
        "old_decks": [],
        "configured": False,
        "preset_ready": False,
        "ankiweb": False,
    }


def _pump_until(qapp, predicate, timeout_s: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        qapp.processEvents()
        if time.monotonic() >= deadline:
            raise AssertionError("Timed out waiting for Qt pairing worker/signal")
        time.sleep(0.01)
    qapp.processEvents()


def test_engine_pairing_http_helpers(monkeypatch):
    assert engine.collab_interpret_poll(200, {"status": "approved"}) == "approved"
    assert engine.collab_interpret_poll(200, {"status": "pending"}) == "pending"
    assert engine.collab_interpret_poll(200, {}) == "retry"
    assert engine.collab_interpret_poll(403, {}) == "rejected"
    assert engine.collab_interpret_poll(404, {}) == "expired"
    assert engine.collab_interpret_poll(410, {}) == "expired"
    assert engine.collab_interpret_poll(500, {}) == "retry"

    calls = []

    class _Resp:
        def __init__(self, status_code, data=None, json_err=False):
            self.status_code = status_code
            self._data = data
            self._json_err = json_err

        def json(self):
            if self._json_err:
                raise ValueError("bad json")
            return self._data

    def _fake_post(url, json=None, timeout=None, verify=None):
        calls.append((url, json, timeout, verify))
        if url.endswith("/pair/init"):
            return _Resp(200, {"code": "ABCD-1234", "poll_token": "tok-1", "expires_in": 180})
        return _Resp(200, {"status": "approved", "token": "jwt-ok", "refresh_token": "ref-ok"})

    monkeypatch.setattr(requests, "post", _fake_post)

    init_res = engine.collab_pair_init(device_id="dev-9")
    assert init_res == {"ok": True, "code": "ABCD-1234", "poll_token": "tok-1", "expires_in": 180}
    assert calls[0][0].endswith("/pair/init")
    assert calls[0][1] == {"device_id": "dev-9"}

    poll_res = engine.collab_pair_poll("tok-1")
    assert poll_res["outcome"] == "approved"
    assert poll_res["body"]["token"] == "jwt-ok"
    assert poll_res["token"] == "tok-1"

    monkeypatch.setattr(requests, "post", lambda *a, **kw: _Resp(502, {}))
    assert engine.collab_pair_init(device_id="dev-9")["ok"] is False
    assert engine.collab_pair_poll("tok-1")["outcome"] == "retry"

    monkeypatch.setattr(requests, "post", lambda *a, **kw: _Resp(410, json_err=True))
    assert engine.collab_pair_poll("tok-1") == {"outcome": "expired", "body": {}, "token": "tok-1"}

    def _raise_timeout(*a, **kw):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(requests, "post", _raise_timeout)
    timeout_res = engine.collab_pair_init(device_id="dev-9")
    assert timeout_res["ok"] is False
    assert "rechtzeitig" in timeout_res["error"]

    def _raise_conn(*a, **kw):
        raise RuntimeError("offline")

    monkeypatch.setattr(requests, "post", _raise_conn)
    assert engine.collab_pair_poll("tok-1") == {"outcome": "retry", "body": {}, "token": "tok-1"}


def test_wizard_system_browser_signup_pairing_and_auto_advance(qapp, mock_mw, monkeypatch):
    opened_urls: list[str] = []
    stored_tokens: list[dict] = []
    poll_outcomes = iter(
        [
            {"outcome": "pending", "body": {}, "token": "pt-1"},
            {"outcome": "approved", "body": {"token": "jwt-1", "refresh_token": "ref-1"}, "token": "pt-1"},
        ]
    )

    monkeypatch.setattr(wizard_mod.webbrowser, "open", lambda u: opened_urls.append(u) or True)
    monkeypatch.setattr(engine, "collab_signup_url", lambda: "https://ankicollab.com/signup")
    monkeypatch.setattr(engine, "collab_pairing_url", lambda c: f"https://ankicollab.com/pair?code={c}")
    monkeypatch.setattr(
        engine,
        "collab_pair_init",
        lambda: {"ok": True, "code": "PASS-7788", "poll_token": "pt-1", "expires_in": 120},
    )
    monkeypatch.setattr(engine, "collab_pair_poll", lambda tok: next(poll_outcomes))
    monkeypatch.setattr(engine, "collab_store_login_result", lambda body: stored_tokens.append(body) or True)

    wiz = AnkizinSetupWizard(info_override=_new_user_info())
    wiz.show()
    wiz.go("account")
    qapp.processEvents()
    assert wiz.current == "account"

    # Account page fits cleanly without horizontal overflow
    sa = wiz.findChild(QScrollArea)
    assert sa is not None and sa.widget() is not None
    assert sa.widget().width() <= sa.viewport().width()

    # Step 1 button opens system browser on /signup (for passkey / keychain / Bitwarden support)
    wiz._sign_up()
    assert opened_urls == ["https://ankicollab.com/signup"]

    # Step 2 starts /pair/init and opens /pair?code=... in system default browser
    wiz._sign_in()
    _pump_until(qapp, lambda: len(opened_urls) == 2)
    assert opened_urls[1] == "https://ankicollab.com/pair?code=PASS-7788"
    assert "PASS-7788" in wiz._status_lbl.text()
    assert wiz._pair_poll_timer.isActive()

    # First poll: pending
    wiz._pair_poll_once()
    _pump_until(qapp, lambda: wiz._pair_outstanding == "")
    assert wiz.current == "account"

    # Second poll: approved -> saves token, stops timers, and auto-advances past account
    wiz._pair_poll_once()
    _pump_until(qapp, lambda: wiz.current != "account")
    assert stored_tokens == [{"token": "jwt-1", "refresh_token": "ref-1"}]
    assert "Bei AnkiCollab angemeldet" in wiz.summary
    assert not wiz._pair_poll_timer.isActive()
    assert not wizard_mod._ACTIVE_PAIR_WORKERS
    wiz.close()


def test_wizard_pairing_expiry_rejection_cleanup_and_classic_fallback(qapp, mock_mw, monkeypatch):
    opened_urls: list[str] = []
    monkeypatch.setattr(wizard_mod.webbrowser, "open", lambda u: opened_urls.append(u) or True)
    monkeypatch.setattr(engine, "collab_pairing_url", lambda c: f"https://ankicollab.com/pair?code={c}")
    monkeypatch.setattr(
        engine,
        "collab_pair_init",
        lambda: {"ok": True, "code": "EXP-111", "poll_token": "pt-exp", "expires_in": 60},
    )

    wiz = AnkizinSetupWizard(info_override=_new_user_info())
    wiz.show()
    wiz.go("account")

    # Simulate expiry stops poll timer & notifies user
    wiz._sign_in()
    _pump_until(qapp, lambda: wiz._pair_token == "pt-exp")
    assert wiz._pair_poll_timer.isActive()
    wiz._on_pair_poll_result({"outcome": "expired", "body": {}, "token": "pt-exp"})
    assert not wiz._pair_poll_timer.isActive()
    assert "abgelaufen" in wiz._status_lbl.text()

    # Simulate rejection stops poll timer & notifies user
    wiz._sign_in()
    _pump_until(qapp, lambda: wiz._pair_token == "pt-exp")
    wiz._on_pair_poll_result({"outcome": "rejected", "body": {}, "token": "pt-exp"})
    assert not wiz._pair_poll_timer.isActive()
    assert "abgelehnt" in wiz._status_lbl.text()

    # Navigating back stops active pairing cleanly
    wiz._sign_in()
    _pump_until(qapp, lambda: wiz._pair_token == "pt-exp")
    assert wiz._pair_poll_timer.isActive()
    wiz.go("welcome")
    assert not wiz._pair_poll_timer.isActive()
    assert wiz._pair_token == ""

    # Classic password login fallback still works cleanly
    wiz.go("account")
    classic_calls = []
    logged_state = {"ok": False}
    monkeypatch.setattr(engine, "collab_is_logged_in", lambda: logged_state["ok"])

    def _fake_classic(parent):
        classic_calls.append(parent)
        logged_state["ok"] = True

    monkeypatch.setattr(engine, "collab_open_login", _fake_classic)
    wiz._sign_in_classic()
    assert len(classic_calls) == 1
    assert "Bei AnkiCollab angemeldet" in wiz.summary
    assert wiz.current != "account"
    wiz.close()
    assert not wizard_mod._ACTIVE_PAIR_WORKERS

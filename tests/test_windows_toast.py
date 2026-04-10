from __future__ import annotations

import pytest

from jobpipe.notifications.windows_toast import notify_job_match


class _Notifier:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def show_toast(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))


class _FailingNotifier:
    def show_toast(self, *args, **kwargs) -> None:
        raise RuntimeError("toast failed")


def test_notify_job_match_log_only_when_no_backend_and_fallback_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "jobpipe.notifications.windows_toast._load_toast_backend",
        lambda: (None, False, "none"),
    )

    result = notify_job_match(
        title="Backend Engineer",
        company="Acme",
        score=0.91,
        url="https://example.com/job/1",
        open_url_fallback=False,
    )

    assert result.delivery_status == "FallbackLogOnly"
    assert result.backend == "none"
    assert result.clickable is False
    assert result.url_opened is False


def test_notify_job_match_opens_url_when_no_backend(monkeypatch) -> None:
    opened_urls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "jobpipe.notifications.windows_toast._load_toast_backend",
        lambda: (None, False, "none"),
    )
    monkeypatch.setattr(
        "jobpipe.notifications.windows_toast.webbrowser.open",
        lambda url, new=0: opened_urls.append((url, new)) or True,
    )

    result = notify_job_match(
        title="Backend Engineer",
        company="Acme",
        score=0.91,
        url="https://example.com/job/1",
    )

    assert result.delivery_status == "UrlOpenedNoToast"
    assert result.backend == "webbrowser"
    assert result.clickable is False
    assert result.url_opened is True
    assert opened_urls == [("https://example.com/job/1", 2)]


def test_notify_job_match_opens_url_for_non_clickable_toast_backend(monkeypatch) -> None:
    notifier = _Notifier()
    opened_urls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "jobpipe.notifications.windows_toast._load_toast_backend",
        lambda: (notifier, False, "win10toast"),
    )
    monkeypatch.setattr(
        "jobpipe.notifications.windows_toast.webbrowser.open",
        lambda url, new=0: opened_urls.append((url, new)) or True,
    )

    result = notify_job_match(
        title="Backend Engineer",
        company="Acme",
        score=0.91,
        url="https://example.com/job/2",
    )

    assert len(notifier.calls) == 1
    _, kwargs = notifier.calls[0]
    assert "callback_on_click" not in kwargs

    assert result.delivery_status == "ToastAndUrlOpened"
    assert result.backend == "win10toast+webbrowser"
    assert result.clickable is False
    assert result.url_opened is True
    assert opened_urls == [("https://example.com/job/2", 2)]


def test_notify_job_match_clickable_backend_sets_callback(monkeypatch) -> None:
    notifier = _Notifier()
    opened_urls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "jobpipe.notifications.windows_toast._load_toast_backend",
        lambda: (notifier, True, "win10toast_click"),
    )
    monkeypatch.setattr(
        "jobpipe.notifications.windows_toast.webbrowser.open",
        lambda url, new=0: opened_urls.append((url, new)) or True,
    )

    result = notify_job_match(
        title="Backend Engineer",
        company="Acme",
        score=0.91,
        url="https://example.com/job/3",
    )

    assert len(notifier.calls) == 1
    _, kwargs = notifier.calls[0]
    assert "callback_on_click" in kwargs
    callback = kwargs["callback_on_click"]
    assert callable(callback)

    # Callback should open URL only when user clicks the toast.
    assert opened_urls == []
    callback()
    assert opened_urls == [("https://example.com/job/3", 2)]

    assert result.delivery_status == "ToastClickable"
    assert result.backend == "win10toast_click"
    assert result.clickable is True
    assert result.url_opened is False


def test_notify_job_match_returns_url_fallback_on_toast_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "jobpipe.notifications.windows_toast._load_toast_backend",
        lambda: (_FailingNotifier(), False, "win10toast"),
    )
    monkeypatch.setattr(
        "jobpipe.notifications.windows_toast.webbrowser.open",
        lambda url, new=0: True,
    )

    result = notify_job_match(
        title="Backend Engineer",
        company="Acme",
        score=0.91,
        url="https://example.com/job/4",
    )

    assert result.delivery_status == "UrlOpenedAfterToastFailure"
    assert result.backend == "webbrowser"
    assert result.clickable is False
    assert result.url_opened is True


def test_notify_job_match_raises_when_toast_fails_and_fallback_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "jobpipe.notifications.windows_toast._load_toast_backend",
        lambda: (_FailingNotifier(), False, "win10toast"),
    )

    with pytest.raises(RuntimeError):
        notify_job_match(
            title="Backend Engineer",
            company="Acme",
            score=0.91,
            url="https://example.com/job/5",
            open_url_fallback=False,
        )

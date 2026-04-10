from __future__ import annotations

from dataclasses import dataclass
import importlib
import logging
import webbrowser
from typing import Callable

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationDeliveryResult:
    delivery_status: str
    backend: str
    clickable: bool
    url_opened: bool = False


def _load_toast_backend() -> tuple[object | None, bool, str]:
    """Return notifier instance, click support flag, and backend name."""
    try:
        module = importlib.import_module("win10toast_click")
        notifier_cls = getattr(module, "ToastNotifier")
        return notifier_cls(), True, "win10toast_click"
    except (ImportError, ModuleNotFoundError, AttributeError):
        pass

    try:
        module = importlib.import_module("win10toast")
        notifier_cls = getattr(module, "ToastNotifier")
        return notifier_cls(), False, "win10toast"
    except (ImportError, ModuleNotFoundError, AttributeError):
        return None, False, "none"


def _open_url_callback(url: str) -> Callable[[], None]:
    def _callback() -> None:
        webbrowser.open(url, new=2)

    return _callback


def _open_url_fallback(url: str) -> bool:
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:  # pragma: no cover - platform/browser-specific behavior
        LOGGER.exception("Failed to open URL fallback for %s", url)
        return False


def notify_job_match(
    title: str,
    company: str,
    score: float,
    url: str,
    open_url_fallback: bool = True,
) -> NotificationDeliveryResult:
    """Send a Windows toast notification when dependencies are available."""
    notifier, supports_click_callback, backend = _load_toast_backend()
    heading = f"JobPipe Match: {title}"
    message = f"{company} | Score {score:.2f}\n{url}"

    if notifier is None:
        LOGGER.info(
            "Toast backend not installed; logging match only. score=%.3f title=%s company=%s url=%s",
            score,
            title,
            company,
            url,
        )

        url_opened = _open_url_fallback(url) if open_url_fallback else False
        if url_opened:
            return NotificationDeliveryResult(
                delivery_status="UrlOpenedNoToast",
                backend="webbrowser",
                clickable=False,
                url_opened=True,
            )

        return NotificationDeliveryResult(
            delivery_status="FallbackLogOnly",
            backend=backend,
            clickable=False,
            url_opened=False,
        )

    try:
        if supports_click_callback:
            notifier.show_toast(
                heading,
                message,
                duration=8,
                threaded=True,
                callback_on_click=_open_url_callback(url),
            )
        else:
            notifier.show_toast(
                heading,
                message,
                duration=8,
                threaded=True,
            )

        if not supports_click_callback and open_url_fallback:
            url_opened = _open_url_fallback(url)
            if url_opened:
                LOGGER.info("MATCH %.3f | %s | %s | %s", score, title, company, url)
                return NotificationDeliveryResult(
                    delivery_status="ToastAndUrlOpened",
                    backend=f"{backend}+webbrowser",
                    clickable=False,
                    url_opened=True,
                )

        LOGGER.info("MATCH %.3f | %s | %s | %s", score, title, company, url)
        return NotificationDeliveryResult(
            delivery_status="ToastClickable" if supports_click_callback else "ToastUrlFallback",
            backend=backend,
            clickable=supports_click_callback,
            url_opened=False,
        )
    except Exception:  # pragma: no cover - platform-specific runtime behavior
        if open_url_fallback:
            url_opened = _open_url_fallback(url)
            if url_opened:
                LOGGER.warning(
                    "Toast backend failed; URL fallback opened. title=%s company=%s url=%s",
                    title,
                    company,
                    url,
                )
                return NotificationDeliveryResult(
                    delivery_status="UrlOpenedAfterToastFailure",
                    backend="webbrowser",
                    clickable=False,
                    url_opened=True,
                )

        LOGGER.exception("Failed to send Windows toast notification for %s", title)
        raise

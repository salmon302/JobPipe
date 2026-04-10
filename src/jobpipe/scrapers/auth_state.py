from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
from urllib.parse import urlparse

try:
    _playwright_async_api = importlib.import_module("playwright.async_api")
    async_playwright = getattr(_playwright_async_api, "async_playwright")
except (ImportError, ModuleNotFoundError, AttributeError):
    async_playwright = None


@dataclass(frozen=True)
class StorageStateStatus:
    path: Path
    exists: bool
    valid_json: bool
    cookie_count: int
    unexpired_cookie_count: int
    session_cookie_count: int
    usable: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class AuthBootstrapResult:
    storage_state: Path
    status: StorageStateStatus


class UnusableStorageStateError(RuntimeError):
    pass


def _is_session_cookie(expires_value: object) -> bool:
    if expires_value is None:
        return True

    try:
        expires = float(expires_value)
    except (TypeError, ValueError):
        return False

    return expires in {-1.0, 0.0}


def _normalize_domain(value: str) -> str:
    return value.strip().lower().lstrip(".")


def _cookie_matches_expected_domains(cookie_domain: str, expected_domains: tuple[str, ...]) -> bool:
    normalized_cookie_domain = _normalize_domain(cookie_domain)
    if not normalized_cookie_domain:
        return False

    for expected in expected_domains:
        if normalized_cookie_domain == expected:
            return True
        if normalized_cookie_domain.endswith(f".{expected}"):
            return True

    return False


def expected_cookie_domains(base_url: str) -> tuple[str, ...]:
    candidate = base_url.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return ()

    domains: list[str] = [_normalize_domain(hostname)]
    if hostname.startswith("www."):
        domains.append(_normalize_domain(hostname[4:]))

    deduplicated: list[str] = []
    for domain in domains:
        if domain and domain not in deduplicated:
            deduplicated.append(domain)

    return tuple(deduplicated)


def evaluate_storage_state(
    storage_state: Path,
    now_utc: datetime | None = None,
    expected_domains: tuple[str, ...] | None = None,
) -> StorageStateStatus:
    now_ts = (now_utc or datetime.now(timezone.utc)).timestamp()
    errors: list[str] = []
    normalized_expected_domains = tuple(
        _normalize_domain(domain)
        for domain in (expected_domains or ())
        if _normalize_domain(domain)
    )

    if not storage_state.exists():
        errors.append("storage state file does not exist")
        return StorageStateStatus(
            path=storage_state,
            exists=False,
            valid_json=False,
            cookie_count=0,
            unexpired_cookie_count=0,
            session_cookie_count=0,
            usable=False,
            errors=tuple(errors),
        )

    try:
        payload = json.loads(storage_state.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(f"failed to read storage state JSON: {exc}")
        return StorageStateStatus(
            path=storage_state,
            exists=True,
            valid_json=False,
            cookie_count=0,
            unexpired_cookie_count=0,
            session_cookie_count=0,
            usable=False,
            errors=tuple(errors),
        )

    cookies = payload.get("cookies", []) if isinstance(payload, dict) else []
    if not isinstance(cookies, list):
        errors.append("cookies payload is not a list")
        cookies = []

    unexpired = 0
    session = 0
    usable_domain_cookie_count = 0
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue

        cookie_domain = str(cookie.get("domain") or "")
        if normalized_expected_domains and not _cookie_matches_expected_domains(
            cookie_domain,
            normalized_expected_domains,
        ):
            continue

        usable_domain_cookie_count += 1

        expires_value = cookie.get("expires")
        if _is_session_cookie(expires_value):
            session += 1
            continue

        try:
            expires = float(expires_value)
        except (TypeError, ValueError):
            continue

        if expires > now_ts:
            unexpired += 1

    usable = usable_domain_cookie_count > 0 and (unexpired > 0 or session > 0)
    if not cookies:
        errors.append("no cookies found in storage state")
    elif normalized_expected_domains and usable_domain_cookie_count == 0:
        expected_text = ", ".join(normalized_expected_domains)
        errors.append(f"no cookies matched expected domains: {expected_text}")
    elif not usable:
        errors.append("all persisted cookies appear expired")

    return StorageStateStatus(
        path=storage_state,
        exists=True,
        valid_json=True,
        cookie_count=len(cookies),
        unexpired_cookie_count=unexpired,
        session_cookie_count=session,
        usable=usable,
        errors=tuple(errors),
    )


def evaluate_platform_storage_state(
    storage_state: Path,
    base_url: str,
    now_utc: datetime | None = None,
) -> StorageStateStatus:
    return evaluate_storage_state(
        storage_state=storage_state,
        now_utc=now_utc,
        expected_domains=expected_cookie_domains(base_url),
    )


def _jobs_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/jobs"


async def bootstrap_storage_state(
    base_url: str,
    storage_state: Path,
    headless: bool,
    prompt_label: str = "platform",
) -> AuthBootstrapResult:
    if async_playwright is None:
        raise RuntimeError(
            "Playwright is not installed. Install dependencies and run `playwright install chromium`."
        )

    storage_state.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context()

        try:
            page = await context.new_page()
            await page.goto(_jobs_url(base_url), wait_until="domcontentloaded", timeout=60000)
            prompt = (
                f"\nComplete {prompt_label} sign-in in the browser window. "
                "Press Enter here to save the session (Ctrl+C to cancel): "
            )
            await asyncio.to_thread(input, prompt)
            await context.storage_state(path=str(storage_state))
        finally:
            await context.close()
            await browser.close()

    status = evaluate_storage_state(
        storage_state,
        expected_domains=expected_cookie_domains(base_url),
    )
    return AuthBootstrapResult(storage_state=storage_state, status=status)


async def bootstrap_hiringcafe_storage_state(
    base_url: str,
    storage_state: Path,
    headless: bool,
) -> AuthBootstrapResult:
    return await bootstrap_storage_state(
        base_url=base_url,
        storage_state=storage_state,
        headless=headless,
        prompt_label="HiringCafe",
    )

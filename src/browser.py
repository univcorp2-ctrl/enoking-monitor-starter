"""CloakBrowser-based fetcher for sites blocked by WAF or requiring JS.

Imported lazily by the monitor so cloakbrowser stays an optional dependency.
"""
from __future__ import annotations

import asyncio
import os


BROWSER_NAV_TIMEOUT_MS = int(os.getenv("BROWSER_NAV_TIMEOUT_MS", "45000"))
BROWSER_SETTLE_MS = int(os.getenv("BROWSER_SETTLE_MS", "3000"))


def fetch_many(urls: list[str]) -> dict[str, tuple[int | None, str, str]]:
    """Open one CloakBrowser session, load every URL, return (status, html, error)."""
    if not urls:
        return {}
    return asyncio.run(_fetch_many_async(urls))


async def _fetch_many_async(urls: list[str]) -> dict[str, tuple[int | None, str, str]]:
    from cloakbrowser import launch_async

    args: list[str] = []
    if os.getenv("BROWSER_IGNORE_CERT_ERRORS") == "1":
        args.append("--ignore-certificate-errors")
    browser = await launch_async(
        headless=True,
        humanize=True,
        locale="ja-JP",
        timezone="Asia/Tokyo",
        args=args or None,
    )
    out: dict[str, tuple[int | None, str, str]] = {}
    try:
        for url in urls:
            ctx = await browser.new_context(ignore_https_errors=True)
            page = await ctx.new_page()
            try:
                resp = await page.goto(
                    url,
                    timeout=BROWSER_NAV_TIMEOUT_MS,
                    wait_until="domcontentloaded",
                )
                await page.wait_for_timeout(BROWSER_SETTLE_MS)
                html = await page.content()
                out[url] = (resp.status if resp else None, html, "")
            except Exception as exc:
                out[url] = (None, "", f"BROWSER_FETCH_ERROR: {exc.__class__.__name__}: {exc}")
            finally:
                await ctx.close()
    finally:
        await browser.close()
    return out

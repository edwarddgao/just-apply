"""Job application pre-processing pipeline.

Resolves URLs, deduplicates against the tracker, and validates links.
All network I/O is async for parallel execution.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse, urlunparse

import httpx

_DEAD_URL_SIGNALS = {"error=true", "/404", "not-found", "page-not-found"}


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    """Strip query params, lowercase, remove trailing slash."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", "")).lower().rstrip("/")


async def resolve_simplify_redirect(
    client: httpx.AsyncClient,
    job_id: str,
) -> str | None:
    """Resolve a Simplify job ID to the direct career page URL."""
    try:
        resp = await client.get(
            f"https://simplify.jobs/jobs/click/{job_id}",
            follow_redirects=False,
            timeout=10.0,
        )
        if resp.status_code in (301, 302, 307, 308):
            return resp.headers.get("location")
    except (httpx.HTTPError, httpx.TimeoutException):
        pass
    return None


# ---------------------------------------------------------------------------
# Batch pipeline
# ---------------------------------------------------------------------------

async def filter_jobs(
    job_ids: list[str],
    tracked_urls: set[str],
    concurrency: int = 20,
) -> list[dict]:
    """Resolve Simplify job IDs and filter against tracker.

    Resolves redirects in parallel, then deduplicates.
    Returns: [{job_id, direct_url, normalized_url}, ...]
    """
    sem = asyncio.Semaphore(concurrency)

    async def _resolve(client: httpx.AsyncClient, job_id: str) -> dict | None:
        async with sem:
            direct_url = await resolve_simplify_redirect(client, job_id)
        if not direct_url:
            return None
        norm = normalize_url(direct_url)
        if norm in tracked_urls:
            return None
        return {"job_id": job_id, "direct_url": direct_url, "normalized_url": norm}

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_resolve(client, jid) for jid in job_ids])
    return [r for r in results if r is not None]


async def validate_urls(
    urls: list[str],
    concurrency: int = 20,
) -> dict[str, bool]:
    """HEAD-check URLs in parallel. Returns {url: is_live} map.

    Dead = 404/410, error-page redirect, or timeout.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _check(client: httpx.AsyncClient, url: str) -> tuple[str, bool]:
        try:
            async with sem:
                resp = await client.head(url, follow_redirects=True, timeout=10.0)
            if resp.status_code in (404, 410):
                return url, False
            final = str(resp.url).lower()
            if any(sig in final for sig in _DEAD_URL_SIGNALS):
                return url, False
            return url, True
        except (httpx.HTTPError, httpx.TimeoutException):
            return url, False

    async with httpx.AsyncClient() as client:
        pairs = await asyncio.gather(*[_check(client, u) for u in urls])
    return dict(pairs)


def filter_external_urls(
    urls: list[dict],
    tracked_urls: set[str],
) -> list[dict]:
    """Filter pre-resolved external URLs against tracker.

    Input: list of {url, ...any extra fields}
    Returns un-applied jobs with normalized_url added.
    """
    results = []
    for item in urls:
        norm = normalize_url(item["url"])
        if norm in tracked_urls:
            continue
        results.append({**item, "normalized_url": norm})
    return results

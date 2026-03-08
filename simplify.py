"""Simplify.jobs Typesense search client."""

from __future__ import annotations

import json as _json
from typing import Any

import httpx

TYPESENSE_SEARCH = "https://js-ha.simplify.jobs/multi_search"
TYPESENSE_API_KEY = "***REMOVED***=="
TYPESENSE_COLLECTION = "jobs"


def _typesense_post(
    payload: dict[str, Any], *, api_key: str = TYPESENSE_API_KEY
) -> dict[str, Any]:
    resp = httpx.post(
        TYPESENSE_SEARCH,
        params={"x-typesense-api-key": api_key},
        content=_json.dumps(payload),
        headers={"Content-Type": "text/plain"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()["results"][0]


def _build_filter_by(
    *,
    experience: str | None = None,
    category: str | None = None,
    job_type: str | None = None,
    min_salary: int | None = None,
) -> str:
    parts: list[str] = []
    if experience:
        parts.append(f"experience_level:=[`{experience}`]")
    if category:
        parts.append(f"functions:=[`{category}`]")
    if job_type:
        parts.append(f"type:=[`{job_type}`]")
    if min_salary is not None:
        parts.append(f"max_salary:>={min_salary}")
    return " && ".join(parts) if parts else ""


def search_jobs(
    *,
    query: str = "*",
    experience: str | None = None,
    category: str | None = None,
    job_type: str | None = None,
    min_salary: int | None = None,
    page: int = 1,
    per_page: int = 250,
) -> dict[str, Any]:
    filter_by = _build_filter_by(
        experience=experience,
        category=category,
        job_type=job_type,
        min_salary=min_salary,
    )

    search_params: dict[str, Any] = {
        "q": query,
        "query_by": "title,company_name,functions,locations",
        "sort_by": "_text_match:desc,shuffle_key:asc,posting_id:desc",
        "page": page,
        "per_page": per_page,
    }
    if filter_by:
        search_params["filter_by"] = filter_by

    return _typesense_post({"searches": [{"collection": TYPESENSE_COLLECTION, **search_params}]})

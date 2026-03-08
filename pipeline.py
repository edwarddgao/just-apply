#!/usr/bin/env python3
"""Automated job application orchestrator.

Usage:
    python pipeline.py                  # 4 concurrent, runs until DB exhausted
    python pipeline.py --concurrency 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from search import find_candidates, resolve_urls, mark_applied, mark_blocked

LOGS_DIR = Path(__file__).parent / "logs"
PIPELINE_LOG = LOGS_DIR / "pipeline.log"


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(PIPELINE_LOG, "a") as f:
        f.write(line + "\n")

ALLOWED_DOMAINS = [
    "lever.co",
    "greenhouse.io",
    "ashbyhq.com",
]

CHILD_ENV = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
CHILD_ENV["ENABLE_TOOL_SEARCH"] = "false"
CHILD_ENV["MAX_THINKING_TOKENS"] = "0"
JOB_TIMEOUT = 600


def is_blocked(url: str) -> str | None:
    if not any(domain in url for domain in ALLOWED_DOMAINS):
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        return f"Not an allowed ATS platform ({host})"
    return None


def parse_status(lines: list[str]) -> tuple[str, str]:
    """Extract STATUS from agent output (last match wins)."""
    status, reason = "error", "No STATUS line in output"
    for line in lines:
        line = line.strip()
        if not line.startswith("STATUS:"):
            continue
        if "SUBMITTED" in line:
            status, reason = "submitted", ""
        elif "ALREADY_APPLIED" in line:
            status, reason = "already_applied", ""
        elif "BLOCKED" in line:
            reason = line.split("—", 1)[-1].strip() if "—" in line else "unknown"
            status = "blocked"
        elif "ERROR" in line:
            reason = line.split("—", 1)[-1].strip() if "—" in line else "unknown"
            status = "error"
    return status, reason


def parse_stream_log(log_path: Path) -> tuple[str, str, float]:
    """Parse a stream-json log file. Returns (status, reason, cost)."""
    all_text = []
    cost = 0.0

    for line in log_path.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    all_text.append(block["text"])
        elif event.get("type") == "result":
            cost = event.get("total_cost_usd", 0)
            result_text = event.get("result", "")
            if result_text:
                all_text.append(result_text)

    status, reason = parse_status("\n".join(all_text).split("\n"))
    return status, reason, cost


def close_extra_tabs() -> None:
    """Close all Chrome tabs except one blank tab."""
    subprocess.run(
        ["osascript", "-e",
         'tell application "Google Chrome" to tell window 1 to close (tabs whose URL is not "chrome://newtab/")'],
        capture_output=True,
    )


def create_tabs(n: int) -> list[int]:
    """One-shot claude -p to create browser tabs."""
    prompt = (
        f"Call tabs_context_mcp with createIfEmpty=true. "
        f"Then call tabs_create_mcp {n - 1} more times (one at a time). "
        f"Return ONLY a JSON array of all {n} tab IDs. Example: [111, 222, 333]"
    )
    result = subprocess.run(
        ["claude", "-p", prompt,
         "--chrome", "--output-format", "json",
         "--max-turns", "15", "--dangerously-skip-permissions"],
        capture_output=True, text=True, env=CHILD_ENV, timeout=60,
    )
    try:
        data = json.loads(result.stdout)
        text = data.get("result", "") or ""
        match = re.search(r"\[[\d,\s]+\]", text)
        if match:
            tab_ids = json.loads(match.group())
            log(f"create_tabs: agent returned {tab_ids}")
            return tab_ids
    except (json.JSONDecodeError, TypeError):
        pass
    log(f"FATAL: Failed to create tabs.\nstdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}")
    sys.exit(1)


async def apply_to_job(job: dict, tab_id: int) -> tuple[str, str, float]:
    """Spawn claude -p to apply. Returns (status, reason, cost)."""
    log_path = LOGS_DIR / f"{job['posting_id']}.jsonl"
    prompt = (
        f"Navigate tab {tab_id} to {job['url']}. "
        f"Company: {job['company']} | Role: {job['title']}"
    )

    cmd = [
        "claude", "-p", prompt,
        "--chrome",
        "--system-prompt-file", str(Path(__file__).parent / "agent_prompt.txt"),
        "--tools", "Bash,Read",
        "--output-format", "stream-json",
        "--verbose",
        "--max-turns", "200",
        "--dangerously-skip-permissions",
        "--model", "haiku",
        "--no-session-persistence",
    ]

    with open(log_path, "w") as log_file:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=log_file,
                stderr=asyncio.subprocess.PIPE,
                env=CHILD_ENV,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=JOB_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "timeout", f"Timeout ({JOB_TIMEOUT}s)", 0.0

    if proc.returncode != 0 and not log_path.stat().st_size:
        err = stderr.decode("utf-8", errors="replace")[:200] if stderr else "unknown"
        return "error", f"Process failed: {err}", 0.0

    return parse_stream_log(log_path)


async def worker(
    worker_id: int,
    tab_id: int,
    job_queue: asyncio.Queue,
    results: dict,
    cost: list[float],
    recent_errors: list[float],
    stop_event: asyncio.Event,
):
    """Pull jobs from queue, apply, mark result, repeat."""
    while not stop_event.is_set():
        try:
            job = job_queue.get_nowait()
        except asyncio.QueueEmpty:
            return

        log(f"  [{worker_id}] -> {job['company']} - {job['title']}")

        try:
            status, reason, job_cost = await apply_to_job(job, tab_id)
        except Exception as e:
            status, reason, job_cost = "error", str(e), 0.0

        results[status] = results.get(status, 0) + 1
        cost[0] += job_cost

        if status in ("submitted", "already_applied"):
            mark_applied(job["posting_id"])
        elif status == "blocked":
            mark_blocked(job["posting_id"], reason, job["company"], job["title"], job["url"])
        elif status == "timeout":
            mark_blocked(job["posting_id"], reason, job["company"], job["title"], job["url"])
        elif status == "error":
            recent_errors.append(time.time())

        # 3+ errors within 60s = Chrome likely crashed
        cutoff = time.time() - 60
        recent_errors[:] = [t for t in recent_errors if t > cutoff]
        if len(recent_errors) >= 3:
            log(f"\n  !!! {len(recent_errors)} errors in last 60s — Chrome likely crashed.")
            stop_event.set()

        sym = {"submitted": "+", "already_applied": "=", "blocked": "x", "error": "!", "timeout": "T"}[status]
        log(
            f"  [{worker_id}] {sym} {status.upper()}: {job['company']} - {job['title']} "
            f"(${job_cost:.2f}) [{results['submitted']} submitted]"
        )
        if status in ("blocked", "error"):
            log(f"         Reason: {reason}")

        job_queue.task_done()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    LOGS_DIR.mkdir(exist_ok=True)

    log(f"Creating {args.concurrency} browser tabs...")
    close_extra_tabs()
    tab_ids = create_tabs(args.concurrency)
    log(f"Tabs: {tab_ids}")

    results: dict = {"submitted": 0, "already_applied": 0, "blocked": 0, "error": 0, "timeout": 0}
    cost = [0.0]
    recent_errors: list[float] = []
    stop_event = asyncio.Event()
    seen_urls: set[str] = set()

    def on_sigint(sig, frame):
        log(f"\n\nInterrupted. {json.dumps(results)}, cost=${cost[0]:.2f}")
        sys.exit(0)
    signal.signal(signal.SIGINT, on_sigint)

    while not stop_event.is_set():
        job_queue: asyncio.Queue = asyncio.Queue()
        fetched = 0

        no_more_candidates = False
        while job_queue.qsize() < args.concurrency * 5:
            candidates = find_candidates(limit=10)
            if not candidates:
                no_more_candidates = True
                log("No more candidates in database.")
                break

            resolved_batch = await resolve_urls(candidates)
            resolved_ids = {r["posting_id"] for r in resolved_batch}
            for c in candidates:
                if c["posting_id"] not in resolved_ids:
                    mark_blocked(c["posting_id"], "URL resolution failed",
                                 c["company"], c["title"], "")
                    results["blocked"] += 1

            for resolved in resolved_batch:
                if "_dead" in resolved:
                    mark_blocked(resolved["posting_id"], resolved["_dead"],
                                 resolved["company"], resolved["title"], resolved["url"])
                    results["blocked"] += 1
                    log(f"  x Dead posting: {resolved['company']} - {resolved['title']} ({resolved['_dead']})")
                    continue

                block_reason = is_blocked(resolved["url"])
                if block_reason:
                    mark_blocked(resolved["posting_id"], block_reason,
                                 resolved["company"], resolved["title"], resolved["url"])
                    results["blocked"] += 1
                    log(f"  x Pre-blocked: {resolved['company']} - {resolved['title']}")
                    continue

                url_base = resolved["url"].split("?")[0]
                if url_base in seen_urls:
                    mark_applied(resolved["posting_id"])
                    results["already_applied"] += 1
                    continue
                seen_urls.add(url_base)

                job_queue.put_nowait(resolved)
                fetched += 1

            if fetched >= args.concurrency * 3:
                break

        if job_queue.empty():
            if no_more_candidates:
                log("No jobs to process.")
                break
            log("Batch fully filtered, fetching more...")
            continue

        log(f"\nProcessing {job_queue.qsize()} jobs (concurrency={args.concurrency})")
        log(f"Progress: {results['submitted']} submitted, cost=${cost[0]:.2f}")

        workers = [
            asyncio.create_task(
                worker(i, tab_ids[i], job_queue, results, cost,
                       recent_errors, stop_event)
            )
            for i in range(min(args.concurrency, len(tab_ids)))
        ]
        await asyncio.gather(*workers)

        log(f"\n--- Progress: {json.dumps(results)}, cost=${cost[0]:.2f} ---")

        if stop_event.is_set():
            try:
                log("\nRestarting Chrome and creating new tabs...")
                subprocess.run(
                    ["osascript", "-e", 'quit app "Google Chrome"'],
                    capture_output=True,
                )
                await asyncio.sleep(3)
                subprocess.run(["open", "-a", "Google Chrome"], capture_output=True)
                await asyncio.sleep(25)
                close_extra_tabs()
                tab_ids = create_tabs(args.concurrency)
                log(f"New tabs: {tab_ids}")
                stop_event.clear()
                recent_errors.clear()
            except Exception as e:
                log(f"Chrome restart failed: {e}")
                break

    log(f"\n{'='*60}")
    log(f"FINAL: {json.dumps(results, indent=2)}")
    log(f"Total cost: ${cost[0]:.2f}")
    log(f"{'='*60}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        log(f"FATAL: {e}")
        import traceback
        log(traceback.format_exc())
        sys.exit(1)

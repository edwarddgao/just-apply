#!/usr/bin/env python3
"""Analyze per-turn tool usage in an agent log."""
import json, sys

path = sys.argv[1]
turns = []
for line in open(path):
    try:
        e = json.loads(line)
    except:
        continue
    if e.get("type") != "assistant":
        continue
    msg = e.get("message", {})
    usage = msg.get("usage", {})
    tool_calls = []
    text_len = 0
    for b in msg.get("content", []):
        if b.get("type") == "tool_use":
            name = b.get("name", "")
            inp = b.get("input", {})
            action = inp.get("action", "")
            short = name.split("__")[-1] if "__" in name else name
            if action:
                short = f"{short}:{action}"
                if action == "type":
                    short += f'("{inp.get("text","")[:20]}")'
                elif action == "key":
                    short += f'({inp.get("text","")})'
                elif action == "scroll":
                    short += f'({inp.get("scroll_direction","")})'
                elif action == "left_click":
                    short += f'({inp.get("coordinate","")})'
            tool_calls.append(short)
        if b.get("type") == "text":
            text_len += len(b.get("text", ""))
    cache = usage.get("cache_read_input_tokens", 0)
    cache_create = usage.get("cache_creation_input_tokens", 0)
    turns.append({
        "calls": tool_calls,
        "cache": cache,
        "cache_create": cache_create,
        "text_len": text_len,
    })

# Print all turns
for i, t in enumerate(turns):
    calls_str = ", ".join(t["calls"]) if t["calls"] else "(thinking)"
    print(f'{i+1:>3}. ctx={t["cache"]+t["cache_create"]:>6}  +{t["cache_create"]:>5}  text={t["text_len"]:>4}  {calls_str}')

# Summary
screenshots = sum(1 for t in turns for c in t["calls"] if "screenshot" in c)
zooms = sum(1 for t in turns for c in t["calls"] if "zoom" in c)
waits = sum(1 for t in turns for c in t["calls"] if "wait" in c)
thinking = sum(1 for t in turns if not t["calls"])
clicks = sum(1 for t in turns for c in t["calls"] if "left_click" in c)
scrolls = sum(1 for t in turns for c in t["calls"] if "scroll" in c)
print(f"\nTotal turns: {len(turns)}")
print(f"Screenshots: {screenshots}, Zooms: {zooms}, Waits: {waits}")
print(f"Clicks: {clicks}, Scrolls: {scrolls}")
print(f"Thinking (no tool): {thinking}")

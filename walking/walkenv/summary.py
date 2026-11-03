"""Facts about an agent session, read from its transcript: model, duration, turns, cost, tool use.

    python -m walkenv.summary runs/E02-curved-path

Writes run_summary.json into the experiment folder and prints it as a markdown table for the report.
"""
import argparse
import json
from collections import Counter
from pathlib import Path


def summarize(run):
    run = Path(run)
    events = []
    for line in (run / "transcript.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict):
            events.append(ev)
    init = next((e for e in events if e.get("subtype") == "init"), {})
    # A session interrupted from outside and resumed has one result per part; the facts add up.
    results = [e for e in events if e.get("type") == "result"]
    last = results[-1] if results else {}
    interruptions = [e.get("timestamp") for e in events if e.get("error") == "rate_limit"]
    tools, commands = Counter(), []
    for ev in events:
        content = (ev.get("message") or {}).get("content") if isinstance(ev.get("message"), dict) else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools[block["name"]] += 1
                if block["name"] == "Bash":
                    commands.append(str(block["input"].get("command", "")))
    def total(key, sub=None):
        return sum(((r.get(key) or {}).get(sub) if sub else r.get(key)) or 0 for r in results)

    previews = run / ".preview_count"
    summary = {
        "model": init.get("model"),
        "finished": last.get("subtype") == "success" and not last.get("is_error"),
        "parts": len(results),
        "usage_limit_interruptions": len(interruptions),
        "duration_min": round(total("duration_ms") / 60000, 1),
        "turns": total("num_turns"),
        "cost_usd": round(total("total_cost_usd"), 2),
        "output_tokens": total("usage", "output_tokens"),
        "thinking_tokens": sum(((r.get("usage") or {}).get("output_tokens_details") or {}).get("thinking_tokens") or 0
                               for r in results),
        "tool_calls": dict(tools),
        "evaluate_runs": sum("evaluate.py" in c for c in commands),
        "previews_used": int(previews.read_text()) if previews.exists() else 0,
    }
    (run / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def summary_table(s):
    tools = ", ".join(f"{n} × {k}" for k, n in sorted(s["tool_calls"].items(), key=lambda kv: -kv[1]))
    rows = [
        ("Model", s["model"]),
        ("Finished normally", "yes" if s["finished"] else "no"),
        ("Interrupted by usage limit", f"{s['usage_limit_interruptions']} time(s)" if s["usage_limit_interruptions"] else "no"),
        ("Duration (working time, all parts)", f"{s['duration_min']} min"),
        ("Turns (model ↔ tool round trips)", s["turns"]),
        ("Cost", f"${s['cost_usd']}"),
        ("Tool calls", tools),
        ("evaluate.py runs / previews used", f"{s['evaluate_runs']} / {s['previews_used']}"),
    ]
    return "\n".join(["| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    print(summary_table(summarize(ap.parse_args().run)))


if __name__ == "__main__":
    main()

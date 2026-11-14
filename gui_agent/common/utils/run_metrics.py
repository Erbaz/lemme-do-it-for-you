"""Run metrics collector for GUI agent runs."""

from __future__ import annotations

import html
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("gui_agent.run_metrics")
REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / ".logs" / "reports"


def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)[:500]


def _truncate(s: str, max_len: int = 120) -> str:
    s = str(s)
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


class RunMetricsCollector:
    def __init__(self, run_id: Optional[str] = None, task: str = "", timeout_seconds: int = 0):
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.task = task
        self.timeout_seconds = timeout_seconds
        self.platform = ""
        self.llm_model = ""
        self.llm_provider = ""
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.result_status = "unknown"
        self.completion_text = ""
        self.llm_calls: List[Dict[str, Any]] = []
        self._llm_call_index = 0
        self.tool_calls: List[Dict[str, Any]] = []
        self._tool_call_index = 0
        self._current_tool_call: Optional[Dict[str, Any]] = None
        self._last_tool_name: Optional[str] = None
        self._last_tool_params_key: Optional[str] = None
        self._consecutive_count = 0
        self._consecutive_start_index: Optional[int] = None
        self.consecutive_repetitions: List[Dict[str, Any]] = []
        self.desktop_snapshot: Optional[str] = None
        self.foreground_snapshots: List[str] = []
        self.final_focused_window: Optional[str] = None

    def record_run_start(self, platform: str = "", llm_model: str = "", llm_provider: str = "") -> None:
        self.start_time = time.time()
        self.platform = platform
        self.llm_model = llm_model
        self.llm_provider = llm_provider
        self.result_status = "running"

    def record_run_end(self, status: str, completion_text: str = "") -> None:
        self.end_time = time.time()
        self.result_status = status
        self.completion_text = completion_text
        self._finalize_consecutive_run()

    def record_llm_start(self, prompt_text: str = "", **kwargs: Any) -> None:
        self._llm_call_index += 1
        call = {
            "index": self._llm_call_index,
            "prompt_chars": len(prompt_text or ""),
            "prompt_preview": _truncate(prompt_text or "", 200),
            "start_time": time.time(),
        }
        self.llm_calls.append(call)

    def record_llm_end(self, completion_text: str = "", response_metadata: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        if not self.llm_calls:
            return
        call = self.llm_calls[-1]
        call["end_time"] = time.time()
        call["completion_chars"] = len(completion_text or "")
        call["completion_preview"] = _truncate(completion_text or "", 200)
        call["elapsed_ms"] = round((call["end_time"] - call["start_time"]) * 1000, 1)
        if response_metadata:
            token_usage = response_metadata.get("token_usage", {}) or {}
            call["prompt_tokens"] = token_usage.get("prompt_tokens")
            call["completion_tokens"] = token_usage.get("completion_tokens")
            call["total_tokens"] = token_usage.get("total_tokens")
            call["reasoning_tokens"] = token_usage.get("reasoning_tokens")
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if key in response_metadata and call.get(key) is None:
                    call[key] = response_metadata[key]

    def record_tool_start(self, tool_name: str, input_str: str = "", **kwargs: Any) -> None:
        self._tool_call_index += 1
        params_key = _safe_json(input_str) if input_str else ""
        call = {
            "index": self._tool_call_index,
            "tool_name": tool_name,
            "input_str": input_str,
            "params_key": params_key,
            "start_time": time.time(),
            "result": "pending",
            "error": None,
            "output_chars": 0,
            "elapsed_ms": None,
        }
        self.tool_calls.append(call)
        self._current_tool_call = call
        if tool_name == self._last_tool_name and params_key == self._last_tool_params_key:
            self._consecutive_count += 1
        else:
            self._finalize_consecutive_run()
            self._last_tool_name = tool_name
            self._last_tool_params_key = params_key
            self._consecutive_count = 1
            self._consecutive_start_index = self._tool_call_index

    def record_tool_end(self, output: Any = "", **kwargs: Any) -> None:
        call = self._current_tool_call
        if not call:
            return
        call["end_time"] = time.time()
        call["elapsed_ms"] = round((call["end_time"] - call["start_time"]) * 1000, 1)
        call["result"] = "success"
        call["output"] = _safe_json(output)
        call["output_chars"] = len(str(output or ""))
        self._current_tool_call = None

    def record_tool_error(self, error: Exception, **kwargs: Any) -> None:
        call = self._current_tool_call
        if not call:
            return
        call["end_time"] = time.time()
        call["elapsed_ms"] = round((call["end_time"] - call["start_time"]) * 1000, 1)
        call["result"] = "error"
        call["error"] = str(error)
        call["output_chars"] = 0
        self._current_tool_call = None

    def _finalize_consecutive_run(self) -> None:
        if self._consecutive_count > 0 and self._last_tool_name is not None:
            self.consecutive_repetitions.append(
                {
                    "tool_name": self._last_tool_name,
                    "params_key": self._last_tool_params_key,
                    "params_display": _truncate(self._last_tool_params_key or "", 160),
                    "consecutive_count": self._consecutive_count,
                    "first_index": self._consecutive_start_index,
                    "last_index": self._consecutive_start_index + self._consecutive_count - 1
                    if self._consecutive_start_index else None,
                }
            )
        self._consecutive_count = 0
        self._last_tool_name = None
        self._last_tool_params_key = None
        self._consecutive_start_index = None

    def record_desktop_snapshot(self, snapshot: str) -> None:
        self.desktop_snapshot = snapshot

    def record_foreground_snapshot(self, snapshot: str) -> None:
        self.foreground_snapshots.append(snapshot)

    def record_final_focused_window(self, window_info: str) -> None:
        self.final_focused_window = window_info

    @property
    def elapsed_seconds(self) -> Optional[float]:
        if self.start_time is None:
            return None
        end = self.end_time or time.time()
        return round(end - self.start_time, 2)

    @property
    def tool_frequency(self) -> Dict[str, Dict[str, int]]:
        freq: Dict[str, Dict[str, int]] = {}
        for call in self.tool_calls:
            name = call["tool_name"]
            if name not in freq:
                freq[name] = {"total": 0, "success": 0, "error": 0}
            freq[name]["total"] += 1
            if call["result"] == "success":
                freq[name]["success"] += 1
            elif call["result"] == "error":
                freq[name]["error"] += 1
        return freq

    @property
    def summary(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "platform": self.platform,
            "llm_model": self.llm_model,
            "llm_provider": self.llm_provider,
            "timeout_seconds": self.timeout_seconds,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None,
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "elapsed_seconds": self.elapsed_seconds,
            "result_status": self.result_status,
            "completion_text": self.completion_text,
            "total_tool_calls": len(self.tool_calls),
            "total_llm_calls": len(self.llm_calls),
            "tool_frequency": self.tool_frequency,
            "consecutive_repetitions": self.consecutive_repetitions,
        }
def _build_tool_freq_rows(collector: RunMetricsCollector) -> str:
    rows = ""
    for name, counts in collector.tool_frequency.items():
        total = counts["total"]
        success = counts["success"]
        error = counts["error"]
        success_rate = round(success / total * 100, 1) if total else 0.0
        times = [c["elapsed_ms"] for c in collector.tool_calls if c["tool_name"] == name and c["elapsed_ms"] is not None]
        avg_ms = f"{round(sum(times) / len(times), 1)} ms" if times else ""
        rows += (
            f"<tr><td>{html.escape(name)}</td>"
            f"<td>{total}</td><td>{success}</td><td>{error}</td>"
            f"<td>{success_rate}%</td><td>{avg_ms}</td></tr>"
        )
    return rows


def _build_consecutive_rows(collector: RunMetricsCollector) -> str:
    rows = ""
    for i, rep in enumerate(collector.consecutive_repetitions, 1):
        rows += (
            f"<tr><td>{i}</td>"
            f"<td>{html.escape(rep['tool_name'])}</td>"
            f"<td><code>{html.escape(rep['params_display'])}</code></td>"
            f"<td>{rep['consecutive_count']}</td>"
            f"<td>{rep['first_index']} – {rep['last_index']}</td>"
            f"<td>{'REPEATED' if rep['consecutive_count'] > 1 else 'single'}</td></tr>"
        )
    return rows


def _build_llm_rows(collector: RunMetricsCollector) -> str:
    rows = ""
    for call in collector.llm_calls:
        tokens = str(call.get("total_tokens", "-"))
        rows += (
            f"<tr><td>{call['index']}</td>"
            f"<td>{call['prompt_chars']}</td><td>{call['completion_chars']}</td>"
            f"<td>{tokens}</td><td>{call.get('elapsed_ms', '-')} ms</td></tr>"
        )
    return rows


def _build_tool_rows(collector: RunMetricsCollector) -> str:
    rows = ""
    for call in collector.tool_calls:
        status_class = "success" if call["result"] == "success" else ("error" if call["result"] == "error" else "pending")
        rows += (
            f"<tr><td>{call['index']}</td>"
            f"<td>{html.escape(call['tool_name'])}</td>"
            f"<td><code>{html.escape(_truncate(call['input_str'], 100))}</code></td>"
            f"<td class='{status_class}'>{html.escape(call['result'])}</td>"
            f"<td>{call['elapsed_ms'] if call['elapsed_ms'] is not None else '-'}</td></tr>"
        )
    return rows
def generate_html_report(collector: RunMetricsCollector, output_path: Path) -> None:
    """Render an HTML report from collected metrics and write it to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tool_freq_rows = _build_tool_freq_rows(collector)
    consecutive_rows = _build_consecutive_rows(collector)
    llm_rows = _build_llm_rows(collector)
    tool_rows = _build_tool_rows(collector)

    status_badge_class = {
        "completed": "badge-success",
        "timed_out": "badge-timeout",
        "errored": "badge-error",
        "running": "badge-running",
        "unknown": "badge-unknown",
    }.get(collector.result_status, "badge-unknown")

    success_count = sum(1 for c in collector.tool_calls if c["result"] == "success")
    total_count = len(collector.tool_calls)
    success_rate = round(success_count / total_count * 100, 1) if total_count else 0.0

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Agent Run Report — {html.escape(collector.run_id)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 24px; background: #f5f5f5; color: #333; }}
  h1 {{ font-size: 24px; margin-bottom: 8px; }}
  h2 {{ font-size: 18px; margin-top: 28px; border-bottom: 2px solid #ddd; padding-bottom: 4px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; background: #fff; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; font-size: 13px; }}
  th {{ background: #eef; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  code {{ background: #eee; padding: 1px 4px; border-radius: 3px; font-size: 12px; }}
  .summary {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 16px 0; }}
  .card {{ background: #fff; border: 1px solid #ccc; border-radius: 6px; padding: 12px 16px; min-width: 150px; }}
  .card h3 {{ margin: 0 0 6px 0; font-size: 13px; color: #666; text-transform: uppercase; }}
  .card .value {{ font-size: 20px; font-weight: bold; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; color: #fff; font-size: 12px; }}
  .badge-success {{ background: #28a745; }}
  .badge-timeout {{ background: #fd7e14; }}
  .badge-error {{ background: #dc3545; }}
  .badge-running {{ background: #17a2b8; }}
  .badge-unknown {{ background: #6c757d; }}
  td.success {{ color: #28a745; font-weight: bold; }}
  td.error {{ color: #dc3545; font-weight: bold; }}
  td.pending {{ color: #6c757d; }}
  .footer {{ margin-top: 24px; font-size: 12px; color: #666; border-top: 1px solid #ddd; padding-top: 8px; }}
</style>
</head>
<body>

<h1>Agent Run Report</h1>
<p><strong>Run ID:</strong> {html.escape(collector.run_id)} &nbsp;|&nbsp;
<strong>Task:</strong> {html.escape(collector.task)} &nbsp;|&nbsp;
<strong>Platform:</strong> {html.escape(collector.platform)} &nbsp;|&nbsp;
<strong>LLM:</strong> {html.escape(collector.llm_model)} ({html.escape(collector.llm_provider)}) &nbsp;|&nbsp;
<strong>Timeout:</strong> {collector.timeout_seconds}s</p>

<p><strong>Status:</strong> <span class="badge {status_badge_class}">{html.escape(collector.result_status)}</span>
&nbsp;&nbsp;<strong>Elapsed:</strong> {collector.elapsed_seconds}s</p>

<h2>Summary Metrics</h2>
<div class="summary">
  <div class="card"><h3>Total Tool Calls</h3><div class="value">{total_count}</div></div>
  <div class="card"><h3>Total LLM Calls</h3><div class="value">{len(collector.llm_calls)}</div></div>
  <div class="card"><h3>Elapsed Time</h3><div class="value">{collector.elapsed_seconds}s</div></div>
  <div class="card"><h3>Tool Success Rate</h3><div class="value">{success_rate}%</div></div>
  <div class="card"><h3>Completion</h3><div class="value">{html.escape(collector.completion_text or '-')[:80]}</div></div>
</div>

<h2>Tool Call Frequency</h2>
<table>
  <tr><th>Tool name</th><th>Call count</th><th>Success</th><th>Error</th><th>Success rate</th><th>Avg elapsed</th></tr>
  {tool_freq_rows or "<tr><td colspan='6'>No tool calls recorded</td></tr>"}
</table>

<h2>Consecutive Repetition Analysis</h2>
<p><em>Groups of identical (tool, parameters) calls made back-to-back.</em></p>
<table>
  <tr><th>#</th><th>Tool name</th><th>Parameters</th><th>Consecutive count</th><th>Call indices</th><th>Outcome</th></tr>
  {consecutive_rows or "<tr><td colspan='6'>No consecutive repetitions detected</td></tr>"}
</table>

<h2>LLM Call Timeline</h2>
<table>
  <tr><th>#</th><th>Prompt chars</th><th>Completion chars</th><th>Tokens</th><th>Elapsed</th></tr>
  {llm_rows or "<tr><td colspan='5'>No LLM calls recorded</td></tr>"}
</table>

<h2>Tool Call Timeline (chronological)</h2>
<table>
  <tr><th>#</th><th>Tool</th><th>Parameters</th><th>Result</th><th>Elapsed ms</th></tr>
  {tool_rows or "<tr><td colspan='5'>No tool calls recorded</td></tr>"}
</table>

<h2>GUI State</h2>
<p><strong>Desktop snapshot:</strong> {html.escape(collector.desktop_snapshot or 'Not captured')[:200]}...</p>
<p><strong>Foreground snapshots captured:</strong> {len(collector.foreground_snapshots)}</p>
<p><strong>Final focused window:</strong> {html.escape(collector.final_focused_window or 'Not captured')}</p>

<div class="footer">
  Report generated for run {html.escape(collector.run_id)}.
</div>

</body>
</html>"""

    output_path.write_text(html_content, encoding="utf-8")
    logger.info("HTML report written", path=str(output_path), run_id=collector.run_id)
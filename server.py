#!/usr/bin/env python3

import subprocess
import json
import os
from datetime import datetime, timedelta
from typing import Optional
from fastmcp import FastMCP

mcp = FastMCP("Adobe Analytics MCP Server")

# ---------------------------------------------------------------------------
# Guardrail constants
# ---------------------------------------------------------------------------
MAX_DATE_RANGE_DAYS = 365
MAX_METRICS = 10
MAX_DIMENSIONS = 5
MAX_TOP = 200

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rscript_path() -> str:
    return os.environ.get("RSCRIPT_PATH", "Rscript")


def _run_r(command: str, *args: str) -> dict | list:
    """Shell out to run_report.R and return parsed JSON."""
    r_script = os.path.join(os.path.dirname(__file__), "run_report.R")
    cmd = [_rscript_path(), r_script, command] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Surface the R stderr to the caller without leaking credentials
        stderr = result.stderr.strip()
        raise RuntimeError(f"R error: {stderr}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse R output as JSON: {e}\nOutput: {result.stdout[:500]}")


def _validate_date_range(date_range: str) -> tuple[str, str]:
    """Parse and validate date_range string, return (start, end)."""
    parts = date_range.split("--")
    if len(parts) != 2:
        raise ValueError("date_range must be in format YYYY-MM-DD--YYYY-MM-DD")
    start_str, end_str = parts[0].strip(), parts[1].strip()
    try:
        start = datetime.strptime(start_str, "%Y-%m-%d")
        end = datetime.strptime(end_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError("date_range dates must be valid calendar dates in YYYY-MM-DD format")
    if start > end:
        raise ValueError("Start date must be before end date")
    if (end - start).days > MAX_DATE_RANGE_DAYS:
        raise ValueError(f"Date range cannot exceed {MAX_DATE_RANGE_DAYS} days")
    return start_str, end_str


def _parse_csv(value: str, label: str, max_count: int) -> list[str]:
    """Split a comma-separated string, strip whitespace, enforce max count."""
    items = [v.strip() for v in value.split(",") if v.strip()]
    if not items:
        raise ValueError(f"At least one {label} must be provided")
    if len(items) > max_count:
        raise ValueError(f"Maximum {max_count} {label}s allowed, got {len(items)}")
    return items


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_report_suites() -> list:
    """List all available Adobe Analytics report suites.

    Returns:
        list: Report suite objects, each with rsid and name fields.
    """
    return _run_r("list_report_suites")


@mcp.tool()
def run_adobe_report(
    rsid: str,
    metrics: str,
    dimensions: str,
    date_range: str,
    top: int = 50,
    segment_id: Optional[str] = None,
) -> dict:
    """Run a freeform Adobe Analytics report and return structured data.

    Use this tool to pull metric data broken down by one or more dimensions
    for a given report suite and date range. The response is structured JSON
    ready for analysis, summarization, or visualization.

    Args:
        rsid:       Report suite ID (e.g., "mycompanyprod"). Use list_report_suites
                    first if you don't know the ID.
        metrics:    Comma-separated metric API names
                    (e.g., "pageviews,visits,bounceRate,revenue").
        dimensions: Comma-separated dimension API names — up to 5
                    (e.g., "page,lasttouchchannel,mobiledevicetype").
        date_range: Start and end dates as "YYYY-MM-DD--YYYY-MM-DD"
                    (e.g., "2024-01-01--2024-01-31"). Max 365 days.
        top:        Number of dimension rows to return per level (default 50, max 200).
        segment_id: Optional Adobe segment ID to filter the report
                    (e.g., "s1234_abc123"). Omit to run unsegmented.

    Returns:
        dict: Tabular report data as a list of row objects, one per
              dimension combination, with metric values as numeric fields.

    Examples:
        run_adobe_report("myrsid", "pageviews,visits", "page", "2024-01-01--2024-01-31")
        run_adobe_report("myrsid", "revenue", "lasttouchchannel,mobiledevicetype",
                         "2024-03-01--2024-03-31", top=25)
    """
    if not rsid or not isinstance(rsid, str):
        raise ValueError("rsid must be a non-empty string")

    _validate_date_range(date_range)
    _parse_csv(metrics, "metric", MAX_METRICS)
    _parse_csv(dimensions, "dimension", MAX_DIMENSIONS)

    if not (1 <= top <= MAX_TOP):
        raise ValueError(f"top must be between 1 and {MAX_TOP}")

    seg_arg = segment_id if segment_id else "NA"

    return _run_r("run_report", rsid, metrics, dimensions, date_range, str(top), seg_arg)


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

@mcp.prompt()
def traffic_trend_analysis(rsid: str, date_range: str) -> str:
    """Prompt template: analyze overall traffic trends for a report suite."""
    return f"""Pull a traffic overview for report suite '{rsid}' over {date_range}.

Steps:
1. Call run_adobe_report with rsid="{rsid}", metrics="pageviews,visits,visitors,bounceRate",
   dimensions="daterangeday", date_range="{date_range}", top=200
2. Identify week-over-week or month-over-month trends.
3. Call out the highest and lowest traffic days and any anomalies.
4. Summarize key takeaways in 3–5 bullet points."""


@mcp.prompt()
def top_content_report(rsid: str, date_range: str, metric: str = "pageviews") -> str:
    """Prompt template: surface top-performing pages by a given metric."""
    return f"""Find the top-performing content for report suite '{rsid}' over {date_range}.

Steps:
1. Call run_adobe_report with rsid="{rsid}", metrics="{metric},visits,bounceRate,timeSpentPerVisit",
   dimensions="page", date_range="{date_range}", top=25
2. Rank pages by {metric}.
3. Note any pages with high traffic but poor engagement (high bounce, low time spent).
4. Identify quick wins: high-engagement pages that could benefit from more promotion."""


@mcp.prompt()
def channel_performance(rsid: str, date_range: str) -> str:
    """Prompt template: compare marketing channel effectiveness."""
    return f"""Compare marketing channel performance for report suite '{rsid}' over {date_range}.

Steps:
1. Call run_adobe_report with rsid="{rsid}", metrics="visits,visitors,orders,revenue,bounceRate",
   dimensions="lasttouchchannel", date_range="{date_range}", top=20
2. Rank channels by revenue and visits separately — note where rankings differ.
3. Calculate an implied conversion proxy (orders / visits) per channel.
4. Highlight the highest-ROI channel and any underperforming channels worth investigating."""


@mcp.prompt()
def anomaly_investigation(rsid: str, metric: str, date_range: str) -> str:
    """Prompt template: investigate a spike or drop in a specific metric."""
    return f"""Investigate an anomaly in '{metric}' for report suite '{rsid}' over {date_range}.

Steps:
1. Run a day-by-day breakdown:
   run_adobe_report rsid="{rsid}", metrics="{metric}", dimensions="daterangeday",
   date_range="{date_range}", top=200
2. Identify the specific day(s) where the anomaly occurred.
3. Run a channel breakdown for the anomaly period:
   run_adobe_report rsid="{rsid}", metrics="{metric}", dimensions="lasttouchchannel",
   date_range="<anomaly_start>--<anomaly_end>"
4. Run a page breakdown for the same period:
   run_adobe_report rsid="{rsid}", metrics="{metric}", dimensions="page", top=25
5. Synthesize: which channel + page combination drove the change?"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")

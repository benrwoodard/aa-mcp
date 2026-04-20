#!/usr/bin/env python3

import subprocess
import json
import os
from datetime import datetime, timedelta
from typing import Optional
from fastmcp import FastMCP
import auth as _auth

mcp = FastMCP("Adobe Analytics MCP Server")

# ---------------------------------------------------------------------------
# Authentication — configure via env vars in settings.json
# ---------------------------------------------------------------------------
# OAuth (browser, one-time):
#   AW_CLIENT_ID, AW_CLIENT_SECRET, AW_COMPANY_ID
#   Call get_auth_url / complete_auth tools to authenticate.
#
# OAuth (pre-seeded, no browser):
#   AW_CLIENT_ID, AW_CLIENT_SECRET, AW_COMPANY_ID, AW_REFRESH_TOKEN
#
# Server-to-Server (S2S):
#   AW_AUTH_TYPE=s2s, AW_AUTH_FILE=/path/to/credentials.json, AW_COMPANY_ID
#   Download credentials JSON from Adobe Developer Console; aw_auth() reads it.
#
# ---------------------------------------------------------------------------
# Guardrail constants
# ---------------------------------------------------------------------------
MAX_DATE_RANGE_DAYS = 365
MAX_METRICS = 10
MAX_DIMENSIONS = 5
MAX_TOP = 200

VALID_SEGMENT_VERBS = [
    "eq", "not-eq", "contains", "not-contains", "starts-with", "ends-with",
    "exists", "not-exists", "gt", "lt", "ge", "le", "match", "not-match",
    "eq-any-of", "not-eq-any-of", "contains-any-of", "not-contains-any-of",
]
VALID_CONTEXTS = ["hits", "visits", "visitors"]
VALID_CONJUNCTIONS = ["and", "or"]
VALID_CM_OPERATORS = ["divide", "multiply", "subtract", "add"]
VALID_CM_TYPES = ["decimal", "percent", "currency", "time"]
VALID_CM_POLARITY = ["positive", "negative"]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rscript_path() -> str:
    return os.environ.get("RSCRIPT_PATH", "Rscript")


def _run_r(command: str, *args: str) -> dict | list:
    """Shell out to run_report.R and return parsed JSON.

    When AW_AUTH_TYPE is oauth (the default), fetches a valid access token
    from the Python auth layer and injects it as AW_ACCESS_TOKEN so the R
    script can authenticate without any browser interaction.
    """
    r_script = os.path.join(os.path.dirname(__file__), "run_report.R")
    cmd = [_rscript_path(), r_script, command] + list(args)

    env = os.environ.copy()
    if env.get("AW_AUTH_TYPE", "oauth") == "oauth":
        try:
            env["AW_ACCESS_TOKEN"] = _auth.get_valid_token()
        except RuntimeError as exc:
            raise RuntimeError(
                f"Adobe Analytics is not authenticated. {exc}"
            ) from exc

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
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
# Tools — Authentication
# ---------------------------------------------------------------------------

@mcp.tool()
def get_auth_url() -> str:
    """Get the Adobe OAuth login URL to authenticate with Adobe Analytics.

    Visit the returned URL in your browser, log in with your Adobe ID,
    and you will be redirected to a page showing an authorization code.
    Paste that code into complete_auth() to finish connecting.

    Returns:
        str: Adobe OAuth authorization URL.
    """
    return _auth.get_auth_url()


@mcp.tool()
def complete_auth(code: str) -> dict:
    """Complete OAuth authentication with the code from the Adobe login redirect.

    After visiting the URL from get_auth_url() and logging in, copy the
    authorization code shown on the page and pass it here.  The server
    stores the resulting tokens and auto-refreshes them on every request.

    Args:
        code: Authorization code from the adobeanalyticsr.com/token_result.html page.

    Returns:
        dict: Authentication status including token expiry.
    """
    tokens = _auth.exchange_code(code)
    expires_in = int(tokens["expires_at"] - __import__("time").time())
    return {
        "status": "authenticated",
        "expires_in_seconds": expires_in,
        "message": "Successfully authenticated. Token will auto-refresh before each request.",
    }


@mcp.tool()
def auth_status() -> dict:
    """Check whether the server is currently authenticated with Adobe Analytics.

    Returns:
        dict: Authentication state and token validity info.
    """
    return _auth.auth_status()


# ---------------------------------------------------------------------------
# Tools — Data discovery
# ---------------------------------------------------------------------------

@mcp.tool()
def list_users() -> list:
    """List all Adobe Analytics users in the company.

    Returns:
        list: User objects with login, firstName, lastName, email, and imsUserId fields.
    """
    return _run_r("list_users")


@mcp.tool()
def list_report_suites() -> list:
    """List all available Adobe Analytics report suites.

    Returns:
        list: Report suite objects, each with rsid and name fields.
    """
    return _run_r("list_report_suites")


@mcp.tool()
def list_dimensions(rsid: str) -> list:
    """List all available dimensions for a report suite.

    Args:
        rsid: Report suite ID (use list_report_suites if unknown).

    Returns:
        list: Dimension objects with id and name fields.
    """
    if not rsid:
        raise ValueError("rsid must be a non-empty string")
    return _run_r("list_dimensions", rsid)


@mcp.tool()
def list_metrics(rsid: str) -> list:
    """List all available standard (non-calculated) metrics for a report suite.

    Args:
        rsid: Report suite ID (use list_report_suites if unknown).

    Returns:
        list: Metric objects with id and name fields.
    """
    if not rsid:
        raise ValueError("rsid must be a non-empty string")
    return _run_r("list_metrics", rsid)


@mcp.tool()
def list_segments(rsid: Optional[str] = None) -> list:
    """List available segments, optionally filtered to a specific report suite.

    Args:
        rsid: Optional report suite ID to filter segments. Omit to list all.

    Returns:
        list: Segment objects with id, name, description, and rsid fields.
    """
    return _run_r("list_segments", rsid if rsid else "NA")


@mcp.tool()
def list_calculated_metrics(rsid: Optional[str] = None) -> list:
    """List available calculated metrics, optionally filtered to a report suite.

    Args:
        rsid: Optional report suite ID to filter. Omit to list all.

    Returns:
        list: Calculated metric objects with id, name, description, and rsid fields.
    """
    return _run_r("list_calculated_metrics", rsid if rsid else "NA")


@mcp.tool()
def list_projects(rsid: Optional[str] = None) -> list:
    """List available Analysis Workspace projects, optionally filtered to a report suite.

    Args:
        rsid: Optional report suite ID to filter projects. Omit to list all.

    Returns:
        list: Project objects with id, name, description, rsid, and owner fields.
    """
    return _run_r("list_projects", rsid if rsid else "NA")


@mcp.tool()
def get_cm_functions() -> list:
    """List all available functions that can be used in calculated metrics
    (e.g. col-sum, col-max, mean, variance, etc.).

    Returns:
        list: Function objects with id, name, description, and category fields.
    """
    return _run_r("get_cm_functions")


# ---------------------------------------------------------------------------
# Tools — Reporting
# ---------------------------------------------------------------------------

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
# Tools — Segment builder
# ---------------------------------------------------------------------------

@mcp.tool()
def build_segment(
    rsid: str,
    name: str,
    description: str,
    rules: list[dict],
    context: str = "hits",
    conjunction: str = "and",
    owner_id: Optional[int] = 201002385,
) -> dict:
    """Create a new segment in Adobe Analytics.

    Args:
        rsid:        Report suite ID the segment is built for.
        name:        Display name for the new segment.
        description: Brief description of what the segment captures.
        rules:       List of rule objects. Each rule must have:
                       - "dimension" OR "metric" (not both): the API id to filter on
                       - "verb": comparison operator. Common values:
                           eq, not-eq, contains, not-contains,
                           starts-with, ends-with, exists, not-exists,
                           gt, lt, ge, le, match, not-match,
                           eq-any-of, not-eq-any-of
                       - "object": the value to compare against
                     Optionally:
                       - "attribution": "repeating" (default), "instance", or "nonrepeating"
                     To group rules into a nested container, pass an object with key
                     "container" containing: context, conjunction, rules, exclude (bool).
        context:     Scope of the top-level container:
                       "hits" (default) — individual page views/events
                       "visits"         — entire visit sessions
                       "visitors"       — all sessions across visitor lifetime
        conjunction: How top-level rules are combined: "and" (default) or "or".
        owner_id:    Adobe Analytics user ID to assign as segment owner.
                     Defaults to DEFAULT_OWNER_ID. Pass None to omit.

    Returns:
        dict: Created segment metadata including id, name, and rsid.

    Examples:
        # Visitors who viewed the home page
        rules=[{"dimension": "page", "verb": "eq", "object": "home"}]

        # Mobile visitors from the US
        rules=[
            {"dimension": "mobiledevicetype", "verb": "eq", "object": "Mobile Phone"},
            {"dimension": "geocountry", "verb": "eq", "object": "United States"}
        ]

        # Visits with more than 3 page views (metric rule)
        rules=[{"metric": "pageviews", "verb": "gt", "object": "3"}], context="visits"
    """
    if not rsid:
        raise ValueError("rsid must be a non-empty string")
    if not name:
        raise ValueError("name must be a non-empty string")
    if not rules:
        raise ValueError("at least one rule must be provided")
    if context not in VALID_CONTEXTS:
        raise ValueError(f"context must be one of {VALID_CONTEXTS}")
    if conjunction not in VALID_CONJUNCTIONS:
        raise ValueError(f"conjunction must be one of {VALID_CONJUNCTIONS}")

    rules_json = json.dumps(rules)
    owner_arg = str(owner_id) if owner_id is not None else "NA"
    return _run_r("create_segment", rsid, name, description, rules_json, context, conjunction, owner_arg)


# ---------------------------------------------------------------------------
# Tools — Calculated metric builder
# ---------------------------------------------------------------------------

@mcp.tool()
def build_calculated_metric(
    rsid: str,
    name: str,
    description: str,
    operator: str,
    metric1: str,
    metric2: Optional[str] = None,
    polarity: str = "positive",
    precision: int = 0,
    type: str = "decimal",
) -> dict:
    """Create a new calculated metric in Adobe Analytics.

    Use get_cm_functions to see available advanced functions.
    Use list_metrics to look up valid metric API ids.

    Args:
        rsid:        Report suite ID the calculated metric is built for.
        name:        Display name for the new calculated metric.
        description: Brief description of what the metric measures.
        operator:    Math operation between metric1 and metric2:
                       "divide"   — metric1 / metric2 (e.g., conversion rate)
                       "multiply" — metric1 * metric2
                       "subtract" — metric1 - metric2
                       "add"      — metric1 + metric2
        metric1:     API id of the primary metric (e.g., "orders").
        metric2:     API id of the secondary metric (e.g., "visits").
                     Required for divide/multiply/subtract/add.
        polarity:    Trend direction that is considered good:
                       "positive" (default) — higher values are better (e.g., revenue)
                       "negative"           — lower values are better (e.g., bounce rate)
        precision:   Decimal places to display (0–10, default 0).
        type:        Display format:
                       "decimal"  (default), "percent", "currency", "time"

    Returns:
        dict: Created calculated metric metadata including id, name, and rsid.

    Examples:
        # Conversion rate (orders / visits)
        operator="divide", metric1="orders", metric2="visits",
        type="percent", precision=2, polarity="positive"

        # Revenue per visit
        operator="divide", metric1="revenue", metric2="visits",
        type="currency", precision=2
    """
    if not rsid:
        raise ValueError("rsid must be a non-empty string")
    if not name:
        raise ValueError("name must be a non-empty string")
    if operator not in VALID_CM_OPERATORS:
        raise ValueError(f"operator must be one of {VALID_CM_OPERATORS}")
    if polarity not in VALID_CM_POLARITY:
        raise ValueError(f"polarity must be one of {VALID_CM_POLARITY}")
    if type not in VALID_CM_TYPES:
        raise ValueError(f"type must be one of {VALID_CM_TYPES}")
    if not (0 <= precision <= 10):
        raise ValueError("precision must be between 0 and 10")

    return _run_r(
        "create_calculated_metric",
        rsid,
        name,
        description or "",
        operator,
        metric1,
        metric2 if metric2 else "NA",
        polarity,
        str(precision),
        type,
    )


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

def _warmup_r() -> None:
    """Spawn a throwaway Rscript to pre-load adobeanalyticsr + deps in the
    background.  R's first-time package load on Windows can take 30–60s,
    which exceeds the MCP client's default request timeout.  Running this
    once at boot warms the OS file cache and R's package namespace so the
    first real tool call responds in ~2s instead of timing out.
    """
    try:
        subprocess.Popen(
            [_rscript_path(), "-e",
             "suppressPackageStartupMessages({library(adobeanalyticsr); library(jsonlite); library(httr)})"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass  # Warm-up is best-effort; don't block startup on failure


if __name__ == "__main__":
    _warmup_r()
    mcp.run(transport="stdio")

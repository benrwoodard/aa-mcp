#!/usr/bin/env Rscript

# Thin wrapper around adobeanalyticsr for MCP server
# Accepts CLI args, authenticates via env vars, outputs JSON to stdout
#
# Required env vars:
#   AW_CLIENT_ID       - Adobe OAuth client ID
#   AW_CLIENT_SECRET   - Adobe OAuth client secret
#   AW_COMPANY_ID      - Adobe Analytics company ID
#
# Optional:
#   AW_REPORTSUITE_ID  - Default report suite (not used here; rsid passed explicitly)

suppressPackageStartupMessages({
  library(adobeanalyticsr)
  library(jsonlite)
})

# Authenticate once on startup using env vars
aw_auth(type = "oauth")

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 1) {
  stop("Usage: Rscript run_report.R <command> [args...]")
}

command <- args[1]

if (command == "list_report_suites") {
  suites <- aw_get_reportsuites(
    company_id = Sys.getenv("AW_COMPANY_ID"),
    limit      = 100,
    page       = 0
  )
  cat(toJSON(suites, auto_unbox = TRUE, dataframe = "rows"))

} else if (command == "run_report") {
  # Args: rsid metrics(csv) dimensions(csv) date_range top segment_id
  if (length(args) < 5) {
    stop("Usage: Rscript run_report.R run_report <rsid> <metrics> <dimensions> <date_range> [top] [segment_id]")
  }

  rsid       <- args[2]
  metrics    <- strsplit(args[3], ",")[[1]]
  dimensions <- strsplit(args[4], ",")[[1]]

  # date_range arrives as "YYYY-MM-DD--YYYY-MM-DD"
  dates      <- strsplit(args[5], "--")[[1]]
  date_range <- as.Date(dates)

  top        <- if (length(args) >= 6 && args[6] != "NA") as.integer(args[6]) else 50L
  segment_id <- if (length(args) >= 7 && args[7] != "NA") args[7] else NA

  report <- aw_freeform_table(
    company_id        = Sys.getenv("AW_COMPANY_ID"),
    rsid              = rsid,
    date_range        = date_range,
    dimensions        = dimensions,
    metrics           = metrics,
    top               = top,
    metricSort        = "desc",
    include_unspecified = FALSE,
    segmentId         = segment_id,
    prettynames       = FALSE,
    check_components  = TRUE,
    debug             = FALSE
  )

  cat(toJSON(report, auto_unbox = TRUE, dataframe = "rows"))

} else {
  stop(paste("Unknown command:", command))
}

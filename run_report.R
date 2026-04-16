#!/usr/bin/env Rscript

# Thin wrapper around adobeanalyticsr for MCP server
# Accepts CLI args, authenticates via env vars, outputs JSON to stdout
#
# Authentication (choose one):
#
#   OAuth (default):
#     AW_AUTH_TYPE     = "oauth"  (or omit — this is the default)
#     AW_CLIENT_ID     - Adobe OAuth client ID
#     AW_CLIENT_SECRET - Adobe OAuth client secret
#
#   Server-to-Server (S2S):
#     AW_AUTH_TYPE     = "s2s"
#     AW_AUTH_FILE     - Path to credentials JSON downloaded from Adobe Developer Console
#
# Required for all auth types:
#   AW_COMPANY_ID      - Adobe Analytics company ID
#
# Optional:
#   AW_REPORTSUITE_ID  - Default report suite (not used here; rsid passed explicitly)

suppressPackageStartupMessages({
  library(adobeanalyticsr)
  library(jsonlite)
})

# Authenticate once on startup using env vars
# Set AW_AUTH_TYPE=s2s to use Server-to-Server auth (requires AW_AUTH_FILE)
# Default is oauth (requires AW_CLIENT_ID + AW_CLIENT_SECRET)
auth_type <- Sys.getenv("AW_AUTH_TYPE", unset = "oauth")
if (auth_type == "s2s") {
  aw_auth_with("s2s")
  aw_auth()
} else {
  aw_auth(type = "oauth")
}

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 1) {
  stop("Usage: Rscript run_report.R <command> [args...]")
}

command <- args[1]

# ---------------------------------------------------------------------------
# list_report_suites
# ---------------------------------------------------------------------------
if (command == "list_report_suites") {
  suites <- aw_get_reportsuites(
    company_id = Sys.getenv("AW_COMPANY_ID"),
    limit      = 100,
    page       = 0
  )
  cat(toJSON(suites, auto_unbox = TRUE, dataframe = "rows"))

# ---------------------------------------------------------------------------
# list_dimensions  args: rsid
# ---------------------------------------------------------------------------
} else if (command == "list_dimensions") {
  rsid <- args[2]
  dims <- aw_get_dimensions(
    rsid       = rsid,
    company_id = Sys.getenv("AW_COMPANY_ID")
  )
  cat(toJSON(dims[, c("id", "name")], auto_unbox = TRUE, dataframe = "rows"))

# ---------------------------------------------------------------------------
# list_metrics  args: rsid
# ---------------------------------------------------------------------------
} else if (command == "list_metrics") {
  rsid    <- args[2]
  metrics <- aw_get_metrics(
    rsid       = rsid,
    company_id = Sys.getenv("AW_COMPANY_ID")
  )
  cat(toJSON(metrics[, c("id", "name")], auto_unbox = TRUE, dataframe = "rows"))

# ---------------------------------------------------------------------------
# list_segments  args: rsid (or NA)
# ---------------------------------------------------------------------------
} else if (command == "list_segments") {
  rsid_arg <- if (length(args) >= 2 && args[2] != "NA") args[2] else NULL
  segs <- aw_get_segments(
    company_id  = Sys.getenv("AW_COMPANY_ID"),
    rsids       = rsid_arg,
    limit       = 100,
    page        = 0,
    includeType = "all"
  )
  cols <- intersect(c("id", "name", "description", "rsid"), colnames(segs))
  cat(toJSON(segs[, cols], auto_unbox = TRUE, dataframe = "rows"))

# ---------------------------------------------------------------------------
# list_calculated_metrics  args: rsid (or NA)
# ---------------------------------------------------------------------------
} else if (command == "list_calculated_metrics") {
  rsid_arg <- if (length(args) >= 2 && args[2] != "NA") args[2] else NULL
  cms <- aw_get_calculatedmetrics(
    company_id  = Sys.getenv("AW_COMPANY_ID"),
    rsids       = rsid_arg,
    limit       = 1000,
    page        = 0,
    includeType = "all"
  )
  cols <- intersect(c("id", "name", "description", "rsid"), colnames(cms))
  cat(toJSON(cms[, cols], auto_unbox = TRUE, dataframe = "rows"))

# ---------------------------------------------------------------------------
# get_cm_functions  (no extra args)
# ---------------------------------------------------------------------------
} else if (command == "get_cm_functions") {
  fns <- get_cm_functions(company_id = Sys.getenv("AW_COMPANY_ID"))
  cols <- intersect(c("id", "name", "description", "category"), colnames(fns))
  cat(toJSON(fns[, cols], auto_unbox = TRUE, dataframe = "rows"))

# ---------------------------------------------------------------------------
# create_segment
#   args: rsid name description rules_json context conjunction
#   rules_json: JSON array of rule objects, each with keys:
#     dimension (or metric), verb, object, attribution (opt), exclude (opt)
#   Supports nested containers via key "container" with context/conjunction/rules.
# ---------------------------------------------------------------------------
} else if (command == "create_segment") {
  if (length(args) < 7) {
    stop("Usage: create_segment rsid name description rules_json context conjunction [owner_id]")
  }
  rsid        <- args[2]
  name        <- args[3]
  description <- args[4]
  rules_json  <- args[5]
  context     <- args[6]
  conjunction <- args[7]
  owner_id    <- if (length(args) >= 8 && args[8] != "NA") as.integer(args[8]) else NULL

  rules_data <- fromJSON(rules_json, simplifyDataFrame = FALSE)

  build_rule <- function(r) {
    seg_rule(
      dimension   = if (!is.null(r$dimension)) r$dimension else NULL,
      metric      = if (!is.null(r$metric))    r$metric    else NULL,
      verb        = r$verb,
      object      = r$object,
      attribution = if (!is.null(r$attribution)) r$attribution else "repeating",
      rsid        = rsid,
      company_id  = Sys.getenv("AW_COMPANY_ID")
    )
  }

  build_container <- function(c) {
    inner_rules <- lapply(c$rules, function(r) {
      if (!is.null(r$container)) build_container(r$container) else build_rule(r)
    })
    seg_con(
      context     = if (!is.null(c$context))     c$context     else "hits",
      conjunction = if (!is.null(c$conjunction)) c$conjunction else "and",
      rules       = inner_rules,
      exclude     = if (!is.null(c$exclude))     c$exclude     else FALSE
    )
  }

  # Top-level items can be rules or containers
  items <- lapply(rules_data, function(r) {
    if (!is.null(r$container)) build_container(r$container) else build_rule(r)
  })

  seg_args <- list(
    name        = name,
    description = description,
    rules       = items,
    context     = context,
    conjunction = conjunction,
    create_seg  = TRUE,
    rsid        = rsid,
    company_id  = Sys.getenv("AW_COMPANY_ID")
  )
  if (!is.null(owner_id)) seg_args$owner <- list(id = owner_id)
  result <- do.call(seg_build, seg_args)
  cat(toJSON(result, auto_unbox = TRUE, dataframe = "rows"))

# ---------------------------------------------------------------------------
# create_calculated_metric
#   args: rsid name description operator metric1 metric2 polarity precision type
#   metric2 may be "NA" for single-metric formulas
# ---------------------------------------------------------------------------
} else if (command == "create_calculated_metric") {
  if (length(args) < 10) {
    stop("Usage: create_calculated_metric rsid name description operator metric1 metric2 polarity precision type")
  }
  rsid        <- args[2]
  name        <- args[3]
  description <- args[4]
  operator    <- args[5]
  metric1     <- args[6]
  metric2     <- if (args[7] != "NA") args[7] else NULL
  polarity    <- args[8]
  precision   <- as.integer(args[9])
  type        <- args[10]

  metrics_vec <- if (!is.null(metric2)) c(metric1, metric2) else metric1

  formula <- cm_formula(
    operator   = operator,
    metrics    = metrics_vec,
    rsid       = rsid,
    company_id = Sys.getenv("AW_COMPANY_ID")
  )

  result <- cm_build(
    name        = name,
    description = description,
    formula     = formula,
    polarity    = polarity,
    precision   = precision,
    type        = type,
    create_cm   = TRUE,
    rsid        = rsid,
    company_id  = Sys.getenv("AW_COMPANY_ID")
  )
  cat(toJSON(result, auto_unbox = TRUE, dataframe = "rows"))

# ---------------------------------------------------------------------------
# run_report
#   args: rsid metrics(csv) dimensions(csv) date_range top segment_id
# ---------------------------------------------------------------------------
} else if (command == "run_report") {
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
    company_id          = Sys.getenv("AW_COMPANY_ID"),
    rsid                = rsid,
    date_range          = date_range,
    dimensions          = dimensions,
    metrics             = metrics,
    top                 = top,
    metricSort          = "desc",
    include_unspecified = FALSE,
    segmentId           = segment_id,
    prettynames         = FALSE,
    check_components    = TRUE,
    debug               = FALSE
  )

  cat(toJSON(report, auto_unbox = TRUE, dataframe = "rows"))

# ---------------------------------------------------------------------------
# list_projects  args: rsid (or NA)
# ---------------------------------------------------------------------------
} else if (command == "list_projects") {
  rsid_arg <- if (length(args) >= 2 && args[2] != "NA") args[2] else NULL
  projects <- aw_get_projects(
    company_id  = Sys.getenv("AW_COMPANY_ID"),
    limit       = 100,
    page        = 0,
    includeType = "all"
  )
  cols <- intersect(c("id", "name", "description", "rsid", "owner"), colnames(projects))
  cat(toJSON(projects[, cols], auto_unbox = TRUE, dataframe = "rows"))

# ---------------------------------------------------------------------------
# list_users  (no extra args)
# ---------------------------------------------------------------------------
} else if (command == "list_users") {
  users <- get_users(company_id = Sys.getenv("AW_COMPANY_ID"))
  cols <- intersect(c("login", "firstName", "lastName", "email", "imsUserId"), colnames(users))
  cat(toJSON(users[, cols], auto_unbox = TRUE, dataframe = "rows"))

} else {
  stop(paste("Unknown command:", command))
}

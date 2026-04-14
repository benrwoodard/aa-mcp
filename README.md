# Adobe Analytics MCP Server

An MCP server that gives Claude direct access to Adobe Analytics 2.0 — run reports, explore dimensions and metrics, and analyze data conversationally.

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- R 4.x and the [`adobeanalyticsr`](https://cran.r-project.org/package=adobeanalyticsr) package
- An Adobe Analytics OAuth client (Client ID + Secret) and your Company ID

### Install R dependencies

```r
install.packages(c("adobeanalyticsr", "jsonlite"))
```

## Setup

1. **Clone the repo**

   ```bash
   git clone <repo-url>
   cd aa_mcp
   ```

2. **Add to your Claude Code `settings.json`** — pick one auth method:

   **OAuth** (default — interactive browser login, good for personal use):
   ```json
   {
     "mcpServers": {
       "adobe-analytics": {
         "command": "uv",
         "args": ["--directory", "/path/to/aa_mcp", "run", "server.py"],
         "env": {
           "AW_CLIENT_ID": "your-client-id",
           "AW_CLIENT_SECRET": "your-client-secret",
           "AW_COMPANY_ID": "your-company-id"
         }
       }
     }
   }
   ```

   **Server-to-Server / S2S** (non-interactive, good for teams and automation):
   ```json
   {
     "mcpServers": {
       "adobe-analytics": {
         "command": "uv",
         "args": ["--directory", "/path/to/aa_mcp", "run", "server.py"],
         "env": {
           "AW_AUTH_TYPE": "s2s",
           "AW_AUTH_FILE": "/path/to/adobe-credentials.json",
           "AW_COMPANY_ID": "your-company-id"
         }
       }
     }
   }
   ```

   The S2S credentials JSON is downloaded from the Adobe Developer Console:
   **Console → your project → OAuth Server-to-Server → Download JSON**

   On Windows use backslash paths, e.g. `C:\\Users\\you\\aa_mcp`.

3. **Restart Claude Code** — the server will start automatically.

## Tools

| Tool | Description |
|------|-------------|
| `list_report_suites` | List all available report suites (rsid + name) |
| `run_adobe_report` | Run a freeform report by metrics, dimensions, and date range |

## Example prompts

- *"What are my report suites?"*
- *"Show me pageviews and visits by page for the last 30 days"*
- *"Compare last week's top 5 pages to the week before"*
- *"What marketing channels drove the most revenue this month?"*

## Docker alternative

```bash
docker build -t aa-mcp .
docker run --rm -i \
  -e AW_CLIENT_ID=your-id \
  -e AW_CLIENT_SECRET=your-secret \
  -e AW_COMPANY_ID=your-company-id \
  aa-mcp
```

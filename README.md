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

2. **Configure your settings file** — copy the appropriate example for your auth method:

   | Auth method | Copy this file |
   |-------------|---------------|
   | OAuth (browser login) | `settings.oauth.example.json` |
   | Server-to-Server / S2S | `settings.s2s.example.json` |

   Fill in the `REPLACE_*` placeholders, then place the file at:

   | Client | Settings file location |
   |--------|----------------------|
   | **Claude Code** | `~/.claude/settings.json` (Mac/Linux) · `C:\Users\<you>\.claude\settings.json` (Windows) |
   | **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac) · `%APPDATA%\Claude\claude_desktop_config.json` (Windows) |

   Both clients use the same JSON format — the only difference is the file location.

   > **S2S only:** the credentials JSON is downloaded from the Adobe Developer Console:
   > **Console → your project → OAuth Server-to-Server → Download JSON**
   >
   > On Windows use double-backslash paths, e.g. `C:\\Users\\you\\aa-mcp`.

3. **Restart Claude / Claude Code** — the MCP server starts automatically.

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

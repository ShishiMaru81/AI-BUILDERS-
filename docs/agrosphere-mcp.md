# AgroSphere MCP

Use this local stdio server with an MCP host on your computer. It sends read requests to the existing AgroSphere API. The host starts the MCP process when needed.

## Setup on Windows

Run from the project root after setting up the [local API](../README.md).

```powershell
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements-mcp.txt
```

In the MCP host, set the command to the absolute path of the project's `.venv\Scripts\python.exe` and give it one argument, the absolute path to `scripts\agrosphere_mcp.py`. The API URL defaults to `http://127.0.0.1:8000/api/v1`. Set `AGROSPHERE_MCP_API_URL` in the server process environment to point at another AgroSphere instance. Remote API URLs use HTTPS.

Private tools require an AgroSphere session token in `AGROSPHERE_MCP_TOKEN`. For a disposable demo, run the following against the local API in PowerShell, then launch the MCP host from that PowerShell session or pass the variable through the host's secret environment setting.

```powershell
$demo = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/v1/auth/demo' -ContentType 'application/json' -Body '{"name":"MCP demo"}'
$env:AGROSPHERE_MCP_TOKEN = $demo.token
```

The demo account starts with a sample plot. For private records, supply the token from the intended AgroSphere session through the host's secret environment setting. The API checks access on each request. Restart the MCP process after changing its session token.

## Tools

| Tool | What it returns |
|---|---|
| `list_plots` | The account's plot IDs, crop names and recorded stages. |
| `get_plot_brief` | The plot calendar, due reminders, alerts, saved rainfall outlook and screening summary. Weather includes its source, validity and expiry. |
| `get_district_prices` | Asking-price and seller-confirmed-order summaries with counts and observation dates. Supports English and Bangla names. Available without a token. |
| `get_storage_summary` | Stored batch weights, remaining quantities and logged losses. |

For example, ask the host to find the tomato plot and summarize its upcoming checks or to look up tomato prices in Gazipur. The adapter exposes read-only tools over local stdio. Sharing the MCP server over the network would require a separate deployment and authentication configuration.

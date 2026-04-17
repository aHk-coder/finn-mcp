# finn-mcp

MCP server that exposes [finn.no](https://www.finn.no) — Norway's largest
online classifieds marketplace — to Claude across four verticals:

- **BAP / Torget** — used goods
- **Real estate** — homes for sale and rentals
- **Cars** — used (new cars are only available via the official API)
- **Jobs** — full-time listings

## Tools

| Tool | Purpose |
|------|---------|
| `search_finn` | Search a vertical by keyword + optional filters. |
| `get_listing` | Fetch a full listing by `finnkode`. |
| `save_search` | Persist a named recurring search. |
| `list_saved_searches` | List all saved searches. |
| `delete_saved_search` | Remove a saved search. |
| `check_saved_search` | Run a saved search and return only hits that are new since the last check. |

## Install & run (recommended)

Requires [uv](https://docs.astral.sh/uv/). Then use `uvx` to run the server
without cloning or installing anything permanently:

```bash
uvx finn-mcp
```

## Register with Claude Code

```bash
claude mcp add finn-mcp -- uvx finn-mcp
```

Or add to your `.mcp.json` (or Claude Desktop's `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "finn-mcp": {
      "command": "uvx",
      "args": ["finn-mcp"]
    }
  }
}
```

## Data access

There is no self-serve public finn.no API. For v1 this server scrapes the
public web pages and parses JSON-LD on detail pages. A stable `FinnBackend`
interface separates the MCP surface from the data source, so the scraper can
be swapped for the official partner API (`cache.api.finn.no/iad/`) later.

Backend selection is controlled by the `FINN_BACKEND` environment variable:

- `FINN_BACKEND=scraper` (default) — the scraper implementation.
- `FINN_BACKEND=official` — stub; raises `NotImplementedError` until
  partner credentials are wired up.

Responses are cached for 24 hours in a local SQLite database at
`$XDG_DATA_HOME/finn-mcp/cache.sqlite` (defaults to
`~/.local/share/finn-mcp/cache.sqlite`).

## Develop from source

```bash
git clone https://github.com/aHk-coder/finn-mcp
cd finn-mcp
uv sync
uv run pytest
uv run finn-mcp   # stdio server
```

Tests run against saved HTML fixtures in `tests/fixtures/` and do not hit
finn.no over the network.

## License

MIT. See [LICENSE](./LICENSE).

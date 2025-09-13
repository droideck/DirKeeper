# DirKeeper

> A natural-language MCP server for 389 Directory Server

> **⚠️ Experimental**
> DirKeeper is an experimental project. It targets local development and testing, is read‑only for directory data, and is not intended for production use yet.

## What is DirKeeper?

DirKeeper lets you explore a 389 Directory Server using natural language through the Model Context Protocol (MCP). Instead of crafting LDAP filters, ask questions like “show me active users named Alice” and the MCP tools will run the appropriate directory queries.

### Current capabilities
- **User discovery**: enumerate users; search by name or attribute
- **Group discovery**: list groups
- **Account status**: compute active/locked/inactive using 389 DS `Accounts.status()` with safe fallbacks
- **User details**: fetch all attributes for a given `uid`
- **Advanced queries**: general-purpose LDAP search with custom base/scope/filter/attributes
- **Server monitor**: fetch main or backend monitor info
- **Config resources**: expose `cn=config` as MCP resources (all attributes or single attribute)

### Provided MCP prompts/tools/resources
- **Prompt**
  - `Tool Navigator` – guides tool selection for directory tasks
- **Tools**
  - `list_all_users(limit=50)`
  - `search_users_by_name(name, limit=50)`
  - `get_user_details(username)`
  - `list_active_users(limit=50)`
  - `list_locked_users(limit=50)`
  - `search_users_by_attribute(attribute, value, limit=50)`
  - `list_all_groups(limit=50)`
  - `ldap_search(base_dn, scope, filter, attributes=None, attrs_only=False, limit=100)`
  - `run_monitor(backend="", suffix="")`
- **Resources**
  - `config://config-all` – all attributes of `cn=config` (JSON)
  - `config://config-attribute/{attribute}` – value(s) for one attribute under `cn=config` (JSON)

## Requirements
- Python 3.13+
- `uv` package manager
- 389 Directory Server (local or container)
- Optional: Ollama + Qwen3, Gemini CLI, Cursor, or Claude Code (any MCP-capable client)

Python deps are defined in `pyproject.toml` / `requirements.txt`:
- `mcp[cli] >= 1.6.0`
- `lib389`

## Quick start

### 1) Set up a 389 DS for local testing (Docker)
You can use the provided scripts to create/start a container and seed example data.

- Create and initialize a DS container with base entries:
```bash
./scripts/ds-create.sh --password TestPassword123 --base-dn dc=test,dc=com ds-test
```
- Or use the all-in-one dev workflow that also seeds users/groups and runs tests:
```bash
./scripts/dev-test.sh
```
Flags for `dev-test.sh` (env overrides supported): `--image`, `--name`, `--hostname`, `--password`, `--base-dn`, `--skip-seed`, `--no-clean`.

To start an existing container only:
```bash
./scripts/ds-start.sh --password TestPassword123 ds-test
```

Note: When Docker maps container port 3389 dynamically, `dev-test.sh` resolves the host port and exports `LDAP_URL` accordingly.

### 2) Configure Python env
```bash
uv venv
uv pip install -r requirements.txt
```

### 3) Export LDAP environment variables
DirKeeper reads its LDAP config from env vars:
```bash
export LDAP_URL="ldap://localhost:3389"   # or your DS host/port
export LDAP_BASE_DN="dc=test,dc=com"
export LDAP_BIND_DN="cn=Directory Manager"
export LDAP_BIND_PASSWORD="TestPassword123"
```

### 4) Run the MCP server
```bash
uv run server.py
```

## Using DirKeeper

You can call the tools from any MCP client. Examples below.

### MCP CLI (example)
Assuming an MCP CLI that can launch servers via config, create a `server_config.json` like:
```json
{
  "mcpServers": {
    "dirkeeper": {
      "command": "/full/path/to/uv",
      "args": [
        "--directory",
        "/full/path/to/DirKeeper/",
        "run",
        "server.py"
      ],
      "env": {
        "LDAP_URL": "ldap://localhost:3389",
        "LDAP_BASE_DN": "dc=test,dc=com",
        "LDAP_BIND_DN": "cn=Directory Manager",
        "LDAP_BIND_PASSWORD": "TestPassword123"
      }
    }
  }
}
```
Run prompts with your provider/model of choice (example uses Ollama + Qwen3):
```bash
uv run mcp-cli cmd \
  --provider=ollama \
  --model=qwen3 \
  --server dirkeeper \
  --prompt "show me all users"
```
Other prompts you can try:
```bash
uv run mcp-cli cmd --provider=ollama --model=qwen3 --server dirkeeper --prompt "list all groups"
uv run mcp-cli cmd --provider=ollama --model=qwen3 --server dirkeeper --prompt "which accounts are locked?"
uv run mcp-cli cmd --provider=ollama --model=qwen3 --server dirkeeper --prompt "find users in the Engineering department"
```

### Gemini CLI (client config)
Create `~/.gemini/settings.json`:
```json
{
  "mcpServers": {
    "dirkeeper": {
      "command": "/full/path/to/uv",
      "args": ["run", "server.py"],
      "env": {
        "LDAP_URL": "ldap://localhost:389",
        "LDAP_BASE_DN": "dc=example,dc=com",
        "LDAP_BIND_DN": "cn=Directory Manager",
        "LDAP_BIND_PASSWORD": "Password"
      },
      "cwd": "/full/path/to/DirKeeper/"
    }
  }
}
```

### Cursor (client config)
Create `.cursor/mcp.json` in your project:
```json
{
  "mcpServers": {
    "dirkeeper": {
      "command": "/full/path/to/uv",
      "args": ["run", "/full/path/to/DirKeeper/server.py"],
      "env": {
        "LDAP_URL": "ldap://localhost:389",
        "LDAP_BASE_DN": "dc=example,dc=com",
        "LDAP_BIND_DN": "cn=Directory Manager",
        "LDAP_BIND_PASSWORD": "Password"
      }
    }
  }
}
```

### Claude Code (client config)
From the DirKeeper directory:
```bash
claude mcp add dirkeeper \
  --env LDAP_BIND_PASSWORD=Password \
  -- uv run server.py
```

## Roadmap (Q4 2025)
- **Community Tech Preview**: Package a usable preview focused on real admin pain points.
- **Troubleshooting focus**: assist with replication conflicts, performance degradation, and "why isn’t this working?" workflows.
- **Guided operations**: leverage prompt templates to steer tool usage and investigations.

## Running tests
The dev script can prepare DS and run pytest in one go:
```bash
./scripts/dev-test.sh
```
Or run them manually once DS and env are ready:
```bash
uv run pytest tests/ -v -s
```

## Project status and limitations
- Experimental; APIs and behavior may change
- Local DS and client required; MCP STDIO transport
- Read-only operations; no user modification yet
- Focused on discovery (users/groups/status/details/monitor/config resources)

## References
- [Model Context Protocol](https://modelcontextprotocol.io/introduction)
- [389 Directory Server docs](https://www.port389.org/docs/389ds/documentation.html)
- [MCP Python SDK on PyPI](https://pypi.org/project/mcp/)
- [mcp-cli (example CLI)](https://github.com/chrishayuk/mcp-cli)

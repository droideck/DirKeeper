# DirKeeper

> A natural language interface for 389 Directory Server powered by Model Context Protocol

> **⚠️ Experimental Status**
> DirKeeper is currently in the experimentation phase. This version is for testing and development purposes only. A public demo will be available soon. Stay tuned for updates!

## What is DirKeeper?

DirKeeper transforms how you interact with your LDAP directory. Instead of writing complex LDAP queries, you can now use natural language to manage and query your 389 Directory Server. Built on top of the Model Context Protocol (MCP), it provides a secure bridge between conversational AI and directory operations.

## Getting Started

### System Requirements

Before diving in, ensure you have these components installed:

1. **Directory Server**
   - 389 Directory Server instance
   - Access credentials (bind DN and password)

2. **AI Components**
   - Ollama for local LLM processing
   - Llama 3.2 model

3. **Development Tools**
   - Python 3.13 or higher
   - uv package manager

### Quick Setup

```bash
# 1. Set up your environment
pip install uv

# 2. Get the code
git clone https://github.com/droideck/DirKeeper.git
cd DirKeeper

# 3. Install dependencies (lib389 soon will be packaged on the official PyPI)
uv venv
uv pip install -r requirements.txt
uv add lib389

# 4. Set up Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama run llama3.2
```

## Configuration Guide

DirKeeper uses environment variables for configuration. You'll need to configure them in a  separate config later in the guide.

```bash
# Directory Server Connection
LDAP_URL="ldap://localhost:389"
LDAP_BASE_DN="dc=example,dc=com"
LDAP_BIND_DN="cn=directory manager"
LDAP_BIND_PASSWORD="your_password"
```

### MCP CLI Configuration

First, install mcp-cli:

```bash
git clone https://github.com/chrishayuk/mcp-cli.git
```

Create or edit `server_config.json` in your MCP CLI directory with the following configurations:

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
        "LDAP_URL": "ldap://localhost:389",
        "LDAP_BASE_DN": "dc=example,dc=com",
        "LDAP_BIND_DN": "cn=directory manager",
        "LDAP_BIND_PASSWORD": "your_password"
      }
    }
  }
}
```

Make sure to:
1. Replace `/full/path/to/uv` with your actual uv installation path
2. Replace `/full/path/to/DirKeeper/` with the actual path to your DirKeeper directory
3. Ensure all paths are absolute paths
4. Update the environment variables with your actual LDAP server configuration

## Using DirKeeper

### Starting the Service

Launch the MCP server with:

```bash
uv run server.py
```

### Example Interactions

Here's how you can interact with your directory:

```bash
# Find all users
uv run mcp-cli cmd \
    --provider=ollama \
    --model=llama3.2 \
    --server dirkeeper \
    --prompt "show me all users in the directory"

# Search for specific users
uv run mcp-cli cmd \
    --provider=ollama \
    --model=llama3.2 \
    --server dirkeeper \
    --prompt "find users with email containing @example.com"
```

### Alternative Usage (Claude Desktop)
> **Note:** While Claude Desktop is an alternative expiremental option, DirKeeper focuses on open-source solutions.

Create or edit `claude_desktop_config.json` in your Claude Desktop configuration directory with the following configuration:

```json
{
  "mcpServers": {
    "DirKeeper": {
      "command": "/full/path/to/uv",
      "args": [
        "run",
        "--index-url",
        "https://test.pypi.org/simple/",
        "--extra-index-url",
        "https://pypi.org/simple/",
        "--with",
        "mcp[cli]",
        "--with",
        "lib389",
        "mcp",
        "run",
        "/full/path/to/DirKeeper/server.py"
      ]
    }
  }
}
```

After that, restart your Claude Desktop tool and you'll be able to use the tool directly in the Claude Desktop UI.

## Technical Details

### Core Components

- **MCP Integration**: Implements Model Context Protocol for secure AI interactions
- **lib389 Integration**: Uses the official Python library for 389 Directory Server

## Project Status & Limitations

> **Note:** This is an experimental project exploring the potential of natural language interaction with 389 Directory Server.

* **Current State & Potential**: While currently in early experimentation, DirKeeper demonstrates the potential to revolutionize LDAP directory management by enabling natural language queries and operations. The project aims to bridge the gap between complex LDAP operations and intuitive human interaction, making directory management more accessible to users without deep LDAP expertise. Future versions may include advanced features like complex query building, managing directory configuration, audit, and ideally integration with other IdM projects.

* **Technical Limitations**: The current implementation requires local 389 Directory Server and Ollama instances, uses STDIO transport for MCP communication, and is limited to basic user operations. The lib389 package will be available on official PyPI soon, and the API/functionality may change between versions. Not recommended for production use at this stage. It's just an experiment as of now.

* **Development Focus**: The project is actively exploring the boundaries of what's possible with natural language processing in directory management, with a focus on reliability, security, and user experience.

## Additional Resources

- [Model Context Protocol Documentation](https://modelcontextprotocol.io/introduction)
- [389 Directory Server Documentation](https://www.port389.org/docs/389ds/documentation.html)
- [MCP Python SDK](https://pypi.org/project/mcp/)
- [MCP CLI Tool](https://github.com/chrishayuk/mcp-cli)

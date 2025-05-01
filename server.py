from typing import Optional, List, Dict, Any
import os
import json
from mcp.server.fastmcp import FastMCP
from lib389 import DirSrv
from lib389.idm.user import nsUserAccounts
from mcp.types import CallToolResult, TextContent

# Create an MCP server
mcp = FastMCP("DirKeeper")

def get_ldap_config():
    """Get LDAP configuration from environment variables."""
    return {
        'ldap_url': os.environ.get('LDAP_URL', 'ldap://localhost:389'),
        'base_dn': os.environ.get('LDAP_BASE_DN', 'dc=example,dc=com'),
        'bind_dn': os.environ.get('LDAP_BIND_DN', 'cn=directory manager'),
        'bind_password': os.environ.get('LDAP_BIND_PASSWORD', 'Password123')
    }

def get_ldap_connection():
    """Create and return a connection to the LDAP server."""
    config = get_ldap_config()

    # Create a DirSrv instance
    ds = DirSrv(verbose=True)

    # Connect to the remote LDAP server
    ds.remote_simple_allocate(
        config['ldap_url'],
        config['bind_dn'],
        config['bind_password']
    )

    # Open the connection
    ds.open()
    return ds

@mcp.tool()
def get_users(filter: Optional[str] = None, basedn: Optional[str] = None):
    """Fetch users from the 389 Directory Server.

    Args:
        ctx: The MCP context
        filter: Optional LDAP filter to apply (default: objectClass=person)
        basedn: Optional base DN to search from (default: from context)

    Returns:
        JSON string containing list of user entries
    """
    try:
        # Get configuration
        config = get_ldap_config()

        # Use provided basedn or default from config
        search_basedn = basedn or config['base_dn']

        # Default filter if not provided
        search_filter = filter or "(objectClass=person)"

        # Connect to LDAP
        ds = get_ldap_connection()

        # Get user accounts
        users = nsUserAccounts(ds, search_basedn)

        # Search for users with the given filter
        user_entries = users.filter(search_filter)

        # Get JSON for each user
        result = []
        for entry_dn in user_entries:
            # Get the user directly in JSON format
            user_json = users.get(entry_dn, json=True)
            result.append(json.loads(user_json))

        # Close the connection
        ds.unbind_s()

        # Convert result to JSON and return as TextContent
        json_result = json.dumps({"type": "users", "items": result}, indent=4)
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json_result
                )
            ]
        )

    except Exception as e:
        # Proper MCP error handling
        error_message = f"Error fetching users from LDAP: {str(e)}"
        print(error_message)

        # Return error information in the result
        return CallToolResult(
            isError=True,
            content=[
                TextContent(
                    type="text",
                    text=error_message
                )
            ]
        )

if __name__ == "__main__":
    mcp.run()
from typing import Optional, List, Dict, Any
from mcp.server.fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("DirKeeper")


@mcp.tool()
def get_users(filter: Optional[str] = None, basedn: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch users from the 389 Directory Server.

    Args:
        ctx: The MCP context
        filter: Optional LDAP filter to apply (default: objectClass=person)
        basedn: Optional base DN to search from (default: from context)

    Returns:
        List of user entries as dictionaries
    """
    return [
        {
            "dn": "uid=demo1,ou=people,dc=example,dc=com",
            "uid": ["demo1"],
            "cn": ["Demo User 1"],
            "objectClass": ["top", "person", "organizationalPerson", "inetOrgPerson"]
        },
        {
            "dn": "uid=demo2,ou=people,dc=example,dc=com",
            "uid": ["demo2"],
            "cn": ["Demo User 2"],
            "objectClass": ["top", "person", "organizationalPerson", "inetOrgPerson"]
        }
    ]


if __name__ == "__main__":
    mcp.run()
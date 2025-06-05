from typing import Optional, List, Dict, Any
import os
import json
from mcp.server.fastmcp import FastMCP
from lib389 import DirSrv
from lib389.idm.user import nsUserAccounts
from mcp.types import CallToolResult, TextContent
from lib389.idm.account import Accounts
from datetime import datetime

# Create an MCP server
mcp = FastMCP("DirKeeper")

def _convert_datetimes_to_strings(data):
    """Recursively convert datetime objects in dicts/lists to ISO strings."""
    if isinstance(data, dict):
        return {k: _convert_datetimes_to_strings(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_convert_datetimes_to_strings(i) for i in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    return data

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
def search_users_advanced(
    query: Optional[str] = None,
    search_type: str = "exact",
    filters: Optional[Dict[str, Any]] = None,
    return_attributes: Optional[List[str]] = None,
    limit: int = 50,
    basedn: Optional[str] = None
):
    """Advanced user search of the 389 Directory Server with complex filtering capabilities.

    Args:
        query: Search term to match against common user attributes (cn, uid, mail, givenName, sn)
        search_type: Type of search - "exact", "fuzzy", or "wildcard"
        filters: Advanced filtering options:
            - user_status: "active", "inactive", "locked"
            - last_login_days: Number of days since last login (uses lastLoginTime)
            - group_membership: List of groups the user must be a member of
            - attribute_contains: Dict of attribute:value pairs to match
            - has_attributes: List of attributes that must be present
        return_attributes: Specific attributes to return (default: common user attributes)
        limit: Maximum number of results to return
        basedn: Optional base DN to search from

    Returns:
        JSON containing filtered user entries with search metadata
    """
    try:
        # Get configuration
        config = get_ldap_config()
        search_basedn = basedn or config['base_dn']

        # Connect to LDAP
        ds = get_ldap_connection()

        # Build the LDAP filter
        ldap_filter_parts = []

        # Handle main query search
        if query:
            query_filter = _build_query_filter(query, search_type)
            ldap_filter_parts.append(query_filter)

        # Handle advanced filters
        if filters:
            advanced_filter = _build_advanced_filter(filters)
            if advanced_filter:
                ldap_filter_parts.append(advanced_filter)

        # Combine all filter parts
        if len(ldap_filter_parts) > 1:
            combined_filter = f"(&{' '.join(ldap_filter_parts)})"
        elif len(ldap_filter_parts) == 1:
            combined_filter = ldap_filter_parts[0]
        else:
            combined_filter = None # All users

        # Determine return attributes
        if return_attributes is None:
            return_attributes = [
                'uid', 'cn', 'sn', 'givenName', 'mail', 'telephoneNumber',
                'title', 'department', 'nsAccountLock', 'createTimestamp',
                'modifyTimestamp', 'lastLoginTime', 'memberOf'
            ]

        # Perform the search using lib389
        users = nsUserAccounts(ds, search_basedn)

        # Apply the filter and get results
        try:
            user_entries = users.filter(combined_filter)
        except Exception as search_error:
            # Fallback to basic search if complex filter fails
            print(f"Advanced filter failed, falling back to basic search: {search_error}")
            user_entries = users.list()

        # Convert to list and apply filters/limit
        results = []
        count = 0
        status_filter = filters.get('user_status') if filters else None

        for user in user_entries:
            if count >= limit:
                break

            try:
                # Get user attributes as JSON
                user_data_json = user.get_all_attrs_json()
                user_data = json.loads(user_data_json)
                user_dn = user_data.get('dn', '')

                # Convert datetime objects in attributes to strings
                if 'attrs' in user_data and isinstance(user_data['attrs'], dict):
                    user_data['attrs'] = _convert_datetimes_to_strings(user_data['attrs'])

                # Filter to only requested attributes if specified
                if return_attributes:
                    filtered_data = {}
                    for attr in return_attributes:
                        if attr in user_data.get('attrs', {}):
                            filtered_data[attr] = user_data['attrs'][attr]

                    # Always include DN
                    filtered_data['dn'] = user_dn
                    user_data = {'dn': user_dn, 'attrs': filtered_data}
                else: # Ensure attrs exist even if not filtering, and it was processed
                    user_data = {'dn': user_dn, 'attrs': user_data.get('attrs', {})}

                # Add computed fields using proper 389 DS API
                status_info = _get_user_status(ds, user_dn, search_basedn)
                user_data['attrs']['computed_status'] = status_info

                # Apply status filter if specified (post-processing since it requires individual account checks)
                if status_filter and status_info.get('simple_status') != status_filter:
                    continue

                results.append(user_data)
                count += 1

            except Exception as user_error:
                print(f"Error processing user {user_dn}: {user_error}")
                continue

        # Close the connection
        ds.unbind_s()

        # Build response with metadata
        response_data = {
            "type": "advanced_search_results",
            "query": query,
            "search_type": search_type,
            "filters_applied": filters or {},
            "total_returned": len(results),
            "limit_applied": limit,
            "ldap_filter_used": combined_filter,
            "return_attributes": return_attributes,
            "items": results
        }

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(response_data, indent=2)
                )
            ]
        )

    except Exception as e:
        error_message = f"Error performing advanced directory search: {str(e)}"
        print(error_message)

        return CallToolResult(
            isError=True,
            content=[
                TextContent(
                    type="text",
                    text=error_message
                )
            ]
        )


def _build_query_filter(query: str, search_type: str) -> str:
    """Build LDAP filter for main query search."""
    # Common searchable attributes
    search_attrs = ['uid', 'cn', 'sn', 'givenName', 'mail', 'displayName']

    if search_type == "exact":
        # Exact match on any of the common attributes
        attr_filters = [f"({attr}={query})" for attr in search_attrs]
        return f"(|{' '.join(attr_filters)})"

    elif search_type == "wildcard":
        # Wildcard search (contains)
        attr_filters = [f"({attr}=*{query}*)" for attr in search_attrs]
        return f"(|{' '.join(attr_filters)})"

    elif search_type == "fuzzy":
        # Fuzzy search - starts with or contains
        attr_filters = []
        for attr in search_attrs:
            attr_filters.extend([
                f"({attr}={query}*)",  # starts with
                f"({attr}=*{query}*)"  # contains
            ])
        return f"(|{' '.join(attr_filters)})"

    else:
        # Default to wildcard
        attr_filters = [f"({attr}=*{query}*)" for attr in search_attrs]
        return f"(|{' '.join(attr_filters)})"


def _build_advanced_filter(filters: Dict[str, Any]) -> str:
    """Build LDAP filter for advanced filtering options.

    Note: user_status filtering is handled in post-processing since it requires
    individual account status checks using the 389 DS Accounts API.
    """
    filter_parts = []

    # Last login filter (approximate - 389 DS uses lastLoginTime)
    if 'last_login_days' in filters:
        days = filters['last_login_days']
        # This is a simplified approach - in production you'd want more sophisticated date handling
        if days == 0:
            filter_parts.append("(lastLoginTime=*)")
        else:
            # For now, just check if lastLoginTime exists or not
            filter_parts.append("(lastLoginTime=*)")

    # Group membership filter
    if 'group_membership' in filters and filters['group_membership']:
        groups = filters['group_membership']
        if isinstance(groups, list):
            group_filters = []
            for group in groups:
                # Handle both DN and simple group names
                if group.startswith('cn='):
                    group_filters.append(f"(memberOf={group})")
                else:
                    group_filters.append(f"(memberOf=cn={group},*)")

            if len(group_filters) > 1:
                filter_parts.append(f"(&{' '.join(group_filters)})")
            else:
                filter_parts.extend(group_filters)

    # Attribute contains filter
    if 'attribute_contains' in filters and filters['attribute_contains']:
        attr_contains = filters['attribute_contains']
        for attr, value in attr_contains.items():
            filter_parts.append(f"({attr}=*{value}*)")

    # Has attributes filter
    if 'has_attributes' in filters and filters['has_attributes']:
        has_attrs = filters['has_attributes']
        for attr in has_attrs:
            filter_parts.append(f"({attr}=*)")

    # Combine all advanced filter parts
    if len(filter_parts) > 1:
        return f"(&{' '.join(filter_parts)})"
    elif len(filter_parts) == 1:
        return filter_parts[0]
    else:
        return ""


def _get_user_status(ds_instance, user_dn: str, basedn: str) -> Dict[str, Any]:
    """Get comprehensive user status using proper 389 DS API."""
    try:
        accounts = Accounts(ds_instance, basedn)
        acct = accounts.get(dn=user_dn)
        status_data = acct.status()

        # Extract status information
        account_state = status_data.get('state', 'unknown')
        params = status_data.get('params', {})
        calc_time = status_data.get('calc_time', None)

        # Convert calc_time to string if it's a datetime object
        if isinstance(calc_time, datetime):
            calc_time_str = calc_time.isoformat()
        else:
            calc_time_str = calc_time

        # Ensure params are serializable
        serializable_params = _convert_datetimes_to_strings(params)

        # Map 389 DS AccountState to our simplified status
        if hasattr(account_state, 'name'):
            state_name = account_state.name
        elif hasattr(account_state, 'value'):
            state_name = str(account_state.value)
        else:
            state_name = str(account_state)

        if state_name in ['DIRECTLY_LOCKED', 'INDIRECTLY_LOCKED']:
            simple_status = 'locked'
        elif state_name == 'INACTIVITY_LIMIT_EXCEEDED':
            simple_status = 'inactive'
        elif state_name == 'ACTIVATED':
            simple_status = 'active'
        else:
            simple_status = 'unknown'

        return {
            'simple_status': simple_status,
            'detailed_status': state_name,
            'status_params': serializable_params,
            'calc_time': calc_time_str
        }

    except Exception as e:
        # Fallback to basic status if the advanced API fails
        return {
            'simple_status': 'unknown',
            'detailed_status': f'error: {str(e)}',
            'status_params': {},
            'calc_time': None
        }


if __name__ == "__main__":
    mcp.run()
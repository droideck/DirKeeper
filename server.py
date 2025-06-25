from typing import Optional, List, Dict, Any
import os
import json
from datetime import datetime
import logging
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from lib389 import DirSrv
from lib389.utils import get_instance_list
from lib389.idm.user import nsUserAccounts
from lib389.idm.account import Accounts
# Healthcheck
from lib389.cli_ctl.health import _list_checks
from lib389.backend import Backends
from lib389.config import Encryption, Config
from lib389.monitor import MonitorDiskSpace
from lib389.replica import Replica
from lib389.nss_ssl import NssSsl
from lib389.dseldif import FSChecks, DSEldif
from lib389.dirsrv_log import DirsrvAccessLog
from lib389.tunables import Tunables
from lib389 import plugins

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        'bind_password': os.environ.get('LDAP_BIND_PASSWORD', 'Password123'),
        'instance': os.environ.get('LDAP_INSTANCE', None),
    }


def get_ldap_connection(local=False):
    """Create and return a connection to the LDAP server."""
    try:
        config = get_ldap_config()
        logger.info("Connecting to LDAP at %s", config['ldap_url'])

        # Create a DirSrv instance
        ds = DirSrv(verbose=False)

        if local:
            # We need this for things like healthCheck and dsctl functionality
            if config['instance'] is None:
                insts = get_instance_list()
                if len(insts) > 0:
                    ds.local_simple_allocate(insts[0],
                                             config['ldap_url'],
                                             config['bind_dn'],
                                             config['bind_password'])
                else:
                    # No local instance
                    return None
            else:
                ds.local_simple_allocate(config['instance'],
                                         config['ldap_url'],
                                         config['bind_dn'],
                                         config['bind_password'])
        else:
            # Connect to the remote LDAP server
            ds.remote_simple_allocate(
                config['ldap_url'],
                config['bind_dn'],
                config['bind_password']
            )

        # Open the connection
        ds.open()
        logger.info("LDAP connection established successfully")
        return ds
    except Exception as e:
        logger.error("Failed to connect to LDAP: %s", str(e))
        raise


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
        logger.warning(f"Error getting user status for {user_dn}: {str(e)}")
        # Fallback to basic status check
        try:
            accounts = Accounts(ds_instance, basedn)
            acct = accounts.get(dn=user_dn)
            # Check nsAccountLock attribute directly
            attrs = acct.get_all_attrs()
            if 'nsAccountLock' in attrs and attrs['nsAccountLock'] and attrs['nsAccountLock'][0].lower() == 'true':
                return {
                    'simple_status': 'locked',
                    'detailed_status': 'DIRECTLY_LOCKED',
                    'status_params': {},
                    'calc_time': None
                }
            else:
                return {
                    'simple_status': 'active',
                    'detailed_status': 'ACTIVATED',
                    'status_params': {},
                    'calc_time': None
                }
        except Exception as fallback_error:
            logger.error(f"Fallback status check failed for {user_dn}: {str(fallback_error)}")
            return {
                'simple_status': 'unknown',
                'detailed_status': f'error: {str(e)}',
                'status_params': {},
                'calc_time': None
            }


@mcp.tool()
def list_all_users(limit: int = 50) -> CallToolResult:
    """List all users in the directory.

    Args:
        limit: Maximum number of users to return (default: 50)

    Returns:
        JSON containing all user entries
    """
    try:
        logger.info(f"Listing all users with limit {limit}")
        config = get_ldap_config()
        ds = get_ldap_connection()

        users = nsUserAccounts(ds, config['base_dn'])
        user_entries = users.list()

        results = []
        count = 0

        for user in user_entries:
            if count >= limit:
                break

            try:
                user_data_json = user.get_all_attrs_json()
                user_data = json.loads(user_data_json)
                user_dn = user_data.get('dn', '')

                # Convert datetime objects
                if 'attrs' in user_data and isinstance(user_data['attrs'], dict):
                    user_data['attrs'] = _convert_datetimes_to_strings(user_data['attrs'])

                # Add status information
                status_info = _get_user_status(ds, user_dn, config['base_dn'])
                user_data['attrs']['computed_status'] = status_info

                results.append(user_data)
                count += 1

            except Exception as user_error:
                logger.error(f"Error processing user: {str(user_error)}")
                continue

        ds.unbind_s()

        response_data = {
            "type": "user_list",
            "total_returned": len(results),
            "limit_applied": limit,
            "items": results
        }

        logger.info(f"Successfully returned {len(results)} users")
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(response_data, indent=2)
                )
            ]
        )

    except Exception as e:
        error_message = f"Error listing users: {str(e)}"
        logger.error(error_message)
        return CallToolResult(
            isError=True,
            content=[
                TextContent(
                    type="text",
                    text=error_message
                )
            ]
        )


@mcp.tool()
def search_users_by_name(name: str, limit: int = 50) -> CallToolResult:
    """Search for users by name (uid, cn, givenName, sn, or displayName).

    Args:
        name: Name to search for (supports wildcards with *)
        limit: Maximum number of users to return (default: 50)

    Returns:
        JSON containing matching user entries
    """
    try:
        logger.info(f"Searching users by name: {name}")
        config = get_ldap_config()
        ds = get_ldap_connection()

        # Build search filter for name
        if '*' in name:
            # User provided wildcards
            search_filter = f"(|(uid={name})(cn={name})(givenName={name})(sn={name})(displayName={name})(mail={name}))"
        else:
            # Add wildcards for partial matching
            search_filter = f"(|(uid=*{name}*)(cn=*{name}*)(givenName=*{name}*)(sn=*{name}*)(displayName=*{name}*)(mail=*{name}*))"

        users = nsUserAccounts(ds, config['base_dn'])
        user_entries = users.filter(search_filter)

        results = []
        count = 0

        for user in user_entries:
            if count >= limit:
                break

            try:
                user_data_json = user.get_all_attrs_json()
                user_data = json.loads(user_data_json)
                user_dn = user_data.get('dn', '')

                # Convert datetime objects
                if 'attrs' in user_data and isinstance(user_data['attrs'], dict):
                    user_data['attrs'] = _convert_datetimes_to_strings(user_data['attrs'])

                # Add status information
                status_info = _get_user_status(ds, user_dn, config['base_dn'])
                user_data['attrs']['computed_status'] = status_info

                results.append(user_data)
                count += 1

            except Exception as user_error:
                logger.error(f"Error processing user: {str(user_error)}")
                continue

        ds.unbind_s()

        response_data = {
            "type": "user_search",
            "search_term": name,
            "filter_used": search_filter,
            "total_returned": len(results),
            "limit_applied": limit,
            "items": results
        }

        logger.info(f"Found {len(results)} users matching '{name}'")
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(response_data, indent=2)
                )
            ]
        )

    except Exception as e:
        error_message = f"Error searching users by name '{name}': {str(e)}"
        logger.error(error_message)
        return CallToolResult(
            isError=True,
            content=[
                TextContent(
                    type="text",
                    text=error_message
                )
            ]
        )


@mcp.tool()
def get_user_details(username: str) -> CallToolResult:
    """Get detailed information about a specific user.

    Args:
        username: Username (uid) to get details for

    Returns:
        JSON containing detailed user information
    """
    try:
        logger.info(f"Getting details for user: {username}")
        config = get_ldap_config()
        ds = get_ldap_connection()

        users = nsUserAccounts(ds, config['base_dn'])

        try:
            user = users.get(username)
            user_data_json = user.get_all_attrs_json()
            user_data = json.loads(user_data_json)
            user_dn = user_data.get('dn', '')

            # Convert datetime objects
            if 'attrs' in user_data and isinstance(user_data['attrs'], dict):
                user_data['attrs'] = _convert_datetimes_to_strings(user_data['attrs'])

            # Add status information
            status_info = _get_user_status(ds, user_dn, config['base_dn'])
            user_data['attrs']['computed_status'] = status_info

            ds.unbind_s()

            response_data = {
                "type": "user_details",
                "username": username,
                "user": user_data
            }

            logger.info(f"Successfully retrieved details for user: {username}")
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(response_data, indent=2)
                    )
                ]
            )

        except Exception as user_error:
            ds.unbind_s()
            error_message = f"User '{username}' not found: {str(user_error)}"
            logger.warning(error_message)
            return CallToolResult(
                isError=True,
                content=[
                    TextContent(
                        type="text",
                        text=error_message
                    )
                ]
            )

    except Exception as e:
        error_message = f"Error getting user details for '{username}': {str(e)}"
        logger.error(error_message)
        return CallToolResult(
            isError=True,
            content=[
                TextContent(
                    type="text",
                    text=error_message
                )
            ]
        )


@mcp.tool()
def list_active_users(limit: int = 50) -> CallToolResult:
    """List all active (unlocked) users in the directory.

    Args:
        limit: Maximum number of users to return (default: 50)

    Returns:
        JSON containing active user entries
    """
    try:
        logger.info(f"Listing active users with limit {limit}")
        config = get_ldap_config()
        ds = get_ldap_connection()

        users = nsUserAccounts(ds, config['base_dn'])
        user_entries = users.list()

        results = []
        count = 0
        processed = 0

        for user in user_entries:
            if count >= limit:
                break

            try:
                processed += 1
                user_data_json = user.get_all_attrs_json()
                user_data = json.loads(user_data_json)
                user_dn = user_data.get('dn', '')

                # Convert datetime objects
                if 'attrs' in user_data and isinstance(user_data['attrs'], dict):
                    user_data['attrs'] = _convert_datetimes_to_strings(user_data['attrs'])

                # Add status information
                status_info = _get_user_status(ds, user_dn, config['base_dn'])
                user_data['attrs']['computed_status'] = status_info

                # Only include active users
                if status_info.get('simple_status') == 'active':
                    results.append(user_data)
                    count += 1

            except Exception as user_error:
                logger.error(f"Error processing user: {str(user_error)}")
                continue

        ds.unbind_s()

        response_data = {
            "type": "active_users",
            "total_processed": processed,
            "active_users_found": len(results),
            "limit_applied": limit,
            "items": results
        }

        logger.info(f"Successfully returned {len(results)} active users out of {processed} processed")
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(response_data, indent=2)
                )
            ]
        )

    except Exception as e:
        error_message = f"Error listing active users: {str(e)}"
        logger.error(error_message)
        return CallToolResult(
            isError=True,
            content=[
                TextContent(
                    type="text",
                    text=error_message
                )
            ]
        )


@mcp.tool()
def list_locked_users(limit: int = 50) -> CallToolResult:
    """List all locked users in the directory.

    Args:
        limit: Maximum number of users to return (default: 50)

    Returns:
        JSON containing locked user entries
    """
    try:
        logger.info(f"Listing locked users with limit {limit}")
        config = get_ldap_config()
        ds = get_ldap_connection()

        users = nsUserAccounts(ds, config['base_dn'])
        user_entries = users.list()

        results = []
        count = 0
        processed = 0

        for user in user_entries:
            if count >= limit:
                break

            try:
                processed += 1
                user_data_json = user.get_all_attrs_json()
                user_data = json.loads(user_data_json)
                user_dn = user_data.get('dn', '')

                # Convert datetime objects
                if 'attrs' in user_data and isinstance(user_data['attrs'], dict):
                    user_data['attrs'] = _convert_datetimes_to_strings(user_data['attrs'])

                # Add status information
                status_info = _get_user_status(ds, user_dn, config['base_dn'])
                user_data['attrs']['computed_status'] = status_info

                # Only include locked users
                if status_info.get('simple_status') == 'locked':
                    results.append(user_data)
                    count += 1

            except Exception as user_error:
                logger.error(f"Error processing user: {str(user_error)}")
                continue

        ds.unbind_s()

        response_data = {
            "type": "locked_users",
            "total_processed": processed,
            "locked_users_found": len(results),
            "limit_applied": limit,
            "items": results
        }

        logger.info(f"Successfully returned {len(results)} locked users out of {processed} processed")
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(response_data, indent=2)
                )
            ]
        )

    except Exception as e:
        error_message = f"Error listing locked users: {str(e)}"
        logger.error(error_message)
        return CallToolResult(
            isError=True,
            content=[
                TextContent(
                    type="text",
                    text=error_message
                )
            ]
        )


@mcp.tool()
def search_users_by_attribute(attribute: str, value: str, limit: int = 50) -> CallToolResult:
    """Search for users by a specific attribute value.

    Args:
        attribute: LDAP attribute name to search (e.g., 'employeeType', 'department', 'title')
        value: Value to search for (supports wildcards with *)
        limit: Maximum number of users to return (default: 50)

    Returns:
        JSON containing matching user entries
    """
    try:
        logger.info(f"Searching users by attribute {attribute}={value}")
        config = get_ldap_config()
        ds = get_ldap_connection()

        # Build search filter
        if '*' in value:
            search_filter = f"({attribute}={value})"
        else:
            search_filter = f"({attribute}=*{value}*)"

        users = nsUserAccounts(ds, config['base_dn'])
        user_entries = users.filter(search_filter)

        results = []
        count = 0

        for user in user_entries:
            if count >= limit:
                break

            try:
                user_data_json = user.get_all_attrs_json()
                user_data = json.loads(user_data_json)
                user_dn = user_data.get('dn', '')

                # Convert datetime objects
                if 'attrs' in user_data and isinstance(user_data['attrs'], dict):
                    user_data['attrs'] = _convert_datetimes_to_strings(user_data['attrs'])

                # Add status information
                status_info = _get_user_status(ds, user_dn, config['base_dn'])
                user_data['attrs']['computed_status'] = status_info

                results.append(user_data)
                count += 1

            except Exception as user_error:
                logger.error(f"Error processing user: {str(user_error)}")
                continue

        ds.unbind_s()

        response_data = {
            "type": "attribute_search",
            "attribute": attribute,
            "value": value,
            "filter_used": search_filter,
            "total_returned": len(results),
            "limit_applied": limit,
            "items": results
        }

        logger.info(f"Found {len(results)} users with {attribute}={value}")
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(response_data, indent=2)
                )
            ]
        )

    except Exception as e:
        error_message = f"Error searching users by attribute {attribute}={value}: {str(e)}"
        logger.error(error_message)
        return CallToolResult(
            isError=True,
            content=[
                TextContent(
                    type="text",
                    text=error_message
                )
            ]
        )


@mcp.tool()
def run_list_healthchecks() -> CallToolResult:
    """List all the available directory server healthchecks

    Returns:
        JSON list containing all the healthchecks that can be performed
    """
    try:
        logger.info("List all the Directory Server health checks")
        ds = get_ldap_connection(local=True)

        if ds is None:
            return CallToolResult(
                isError=True,
                content=[
                    TextContent(
                        type="text",
                        text="There is no local instance"
                    )
                ]
            )

        check_objects = [
            Config,
            Backends,
            Encryption,
            FSChecks,
            plugins.ReferentialIntegrityPlugin,
            plugins.MemberOfPlugin,
            MonitorDiskSpace,
            Replica,
            DSEldif,
            NssSsl,
            DirsrvAccessLog,
            Tunables,
        ]

        def _list_targets(inst):
            for c in check_objects:
                o = c(inst)
                yield o.lint_uid(), o

        checks = dict(_list_targets(ds)).keys()
        results = []

        for o, s in _list_checks(ds, checks):
            results.append(f'{o.lint_uid()}:{s[0]}')

        ds.unbind_s()
        response_data = {
            "type": "healthchecks",
            "total_checks": len(results),
            "items": results
        }

        logger.info("Found %d checks", len(results))
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(response_data, indent=2)
                )
            ]
        )

    except Exception as e:
        error_message = f"Error listing healthchecks: {str(e)}"
        logger.error(error_message)
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

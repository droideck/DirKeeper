import json
import pytest
from server import run_monitor


def check_out(response_data, arg: str = ""):
    """Check the JSON repsnse for the expected values"""

    print("DEBUG response: " + str(response_data))
    assert response_data["type"] == "monitor"
    assert "item" in response_data
    assert "attrs" in response_data["item"]
    attrs = response_data["item"]['attrs']

    if arg == "":
        assert "version" in attrs
        assert attrs["version"][0].startswith("389-Directory")
        assert "threads" in attrs
        assert "nbackends" in attrs
        assert "totalconnections" in attrs
    elif arg == 'backend':
        assert "database" in attrs
        assert attrs["database"][0] == "ldbm database"
        assert "entrycachehits" in attrs
    else:
        print("Unknown arg: " + str(arg))
        assert False


def test_monitor(mock_env):
    """Test that list_all_users returns all users from the directory."""

    #
    # Call the tool (no backend/suffix)
    #
    result = run_monitor()

    # Verify the result is not an error
    assert not result.isError, f"Tool returned error: {
        result.content[0].text if result.content else 'No content'}"

    # Parse the JSON response
    response_text = result.content[0].text
    response_data = json.loads(response_text)

    # Verify response structure
    check_out(response_data)
    print("✓ Found expected monitor data")

    #
    # Call the tool (backend)
    #
    result = run_monitor(backend="userroot")

    # Verify the result is not an error
    assert not result.isError, f"Tool returned error: {
        result.content[0].text if result.content else 'No content'}"

    # Parse the JSON response
    response_text = result.content[0].text
    response_data = json.loads(response_text)

    # Verify response structure
    check_out(response_data, "backend")
    print("✓ Found expected monitor data for backend")

    #
    # Call the tool (no backend/suffix)
    #
    result = run_monitor(suffix="dc=test,dc=com")

    # Verify the result is not an error
    assert not result.isError, f"Tool returned error: {
        result.content[0].text if result.content else 'No content'}"

    # Parse the JSON response
    response_text = result.content[0].text
    response_data = json.loads(response_text)

    # Verify response structure
    check_out(response_data, "backend")
    print("✓ Found expected monitor data for suffix")

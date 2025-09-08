#!/bin/bash -e

set -euo pipefail

# Defaults (align with .github/workflows/pytest.yml)
DS_IMAGE=${DS_IMAGE:-quay.io/389ds/dirsrv}
DS_NAME=${DS_NAME:-ds-test}
DS_HOSTNAME=${DS_HOSTNAME:-localhost}
DS_PASSWORD=${DS_PASSWORD:-TestPassword123}
DS_BASE_DN=${DS_BASE_DN:-dc=test,dc=com}

print_usage() {
  cat <<EOF
Usage: scripts/dev-test.sh [options]

Options (env or flags):
  --image <image>          Directory Server image (default: \"$DS_IMAGE\")
  --name <name>            Container name (default: \"$DS_NAME\")
  --hostname <host>        LDAP host seen by client (default: \"$DS_HOSTNAME\")
  --password <password>    Directory Manager password (default: \"$DS_PASSWORD\")
  --base-dn <dn>           Base DN (default: \"$DS_BASE_DN\")
  --skip-seed              Skip adding example test data
  --no-clean               Skip removing existing container and volume
  -h, --help               Show this help

Environment overrides also supported: DS_IMAGE, DS_NAME, DS_HOSTNAME, DS_PASSWORD, DS_BASE_DN
EOF
}

SKIP_SEED=false
CLEAN=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      DS_IMAGE="$2"; shift 2 ;;
    --name)
      DS_NAME="$2"; shift 2 ;;
    --hostname)
      DS_HOSTNAME="$2"; shift 2 ;;
    --password)
      DS_PASSWORD="$2"; shift 2 ;;
    --base-dn)
      DS_BASE_DN="$2"; shift 2 ;;
    --skip-seed)
      SKIP_SEED=true; shift ;;
    --no-clean)
      CLEAN=false; shift ;;
    -h|--help)
      print_usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2; print_usage; exit 1 ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command not found: $1" >&2
    exit 1
  fi
}

require_cmd docker

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)

if [[ "$CLEAN" == true ]]; then
  echo "[1/7] Cleaning any existing container and data volume..."
  if docker inspect "$DS_NAME" >/dev/null 2>&1; then
    docker rm -f "$DS_NAME" >/dev/null 2>&1 || true
  fi
  VOL_NAME="${DS_NAME}-data"
  if docker volume ls -q --filter name=^${VOL_NAME}$ | grep -q "${VOL_NAME}"; then
    docker volume rm "$VOL_NAME" >/dev/null 2>&1 || true
  fi
else
  echo "[1/7] Skipping cleanup (--no-clean)"
fi

echo "[2/7] Ensuring container $DS_NAME exists and is running..."
if ! docker inspect "$DS_NAME" >/dev/null 2>&1; then
  "$SCRIPT_DIR/ds-create.sh" \
    --image="$DS_IMAGE" \
    --hostname="$DS_HOSTNAME" \
    --password="$DS_PASSWORD" \
    --base-dn="$DS_BASE_DN" \
    "$DS_NAME"
else
  "$SCRIPT_DIR/ds-start.sh" \
    --image="$DS_IMAGE" \
    --password="$DS_PASSWORD" \
    "$DS_NAME"
fi

echo "[3/7] Resolving mapped LDAP port (container 3389/tcp) ..."
DS_PORT=$(docker port "$DS_NAME" 3389/tcp | awk -F: '{print $2}' | tail -n1)
if [[ -z "${DS_PORT:-}" ]]; then
  echo "Failed to resolve mapped DS port" >&2
  docker port "$DS_NAME" || true
  exit 1
fi
echo "LDAP is mapped to localhost:$DS_PORT"

if [[ "$SKIP_SEED" != true ]]; then
  echo "[4/7] Seeding example test data into LDAP..."
  # slight delay to ensure service is ready
  sleep 5
  docker exec -i "$DS_NAME" ldapadd \
    -H ldap://localhost:3389 \
    -D "cn=Directory Manager" \
    -w "$DS_PASSWORD" \
    -x <<'EOF'
dn: uid=testuser1,ou=people,dc=test,dc=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: nsPerson
objectClass: nsAccount
objectClass: nsOrgPerson
objectClass: posixAccount
uid: testuser1
cn: Test User 1
sn: User
givenName: Test
displayName: Test User 1
mail: testuser1@test.com
uidNumber: 1001
gidNumber: 1001
homeDirectory: /home/testuser1

dn: uid=testuser2,ou=people,dc=test,dc=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: nsPerson
objectClass: nsAccount
objectClass: nsOrgPerson
objectClass: posixAccount
uid: testuser2
cn: Test User 2
sn: User
givenName: Test
displayName: Test User 2
mail: testuser2@test.com
uidNumber: 1002
gidNumber: 1002
homeDirectory: /home/testuser2
departmentNumber: Engineering

dn: uid=lockeduser,ou=people,dc=test,dc=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: nsPerson
objectClass: nsAccount
objectClass: nsOrgPerson
objectClass: posixAccount
uid: lockeduser
cn: Locked User
sn: User
givenName: Locked
displayName: Locked User
mail: lockeduser@test.com
uidNumber: 1003
gidNumber: 1003
homeDirectory: /home/lockeduser
nsAccountLock: true

dn: uid=contractor,ou=people,dc=test,dc=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: nsPerson
objectClass: nsAccount
objectClass: nsOrgPerson
objectClass: posixAccount
uid: contractor
cn: Contractor User
sn: User
givenName: Contractor
displayName: Contractor User
mail: contractor@test.com
uidNumber: 1004
gidNumber: 1004
homeDirectory: /home/contractor
employeeType: Contractor

dn: cn=testgroup1,ou=groups,dc=test,dc=com
objectClass: top
objectClass: groupOfNames
objectClass: posixGroup
objectClass: nsMemberOf
cn: testgroup1
gidNumber: 5000

dn: cn=testgroup2,ou=groups,dc=test,dc=com
objectClass: top
objectClass: groupOfNames
objectClass: posixGroup
objectClass: nsMemberOf
cn: testgroup2
gidNumber: 5001
EOF

  echo "[5/7] Verifying test entries..."
  docker exec "$DS_NAME" ldapsearch -H ldap://localhost:3389 -D "cn=Directory Manager" -w "$DS_PASSWORD" -x -b "ou=people,dc=test,dc=com" -s sub "(uid=testuser*)" dn uid cn mail | head -n 100 || true
  docker exec "$DS_NAME" ldapsearch -H ldap://localhost:3389 -D "cn=Directory Manager" -w "$DS_PASSWORD" -x -b "ou=groups,dc=test,dc=com" -s sub "(cn=testgroup*)" dn gidNumber | head -n 50 || true
fi

echo "[6/7] Preparing Python environment (uv preferred)..."
if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv (user-local)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.cargo/bin:$PATH"
fi

cd "$REPO_ROOT"

uv venv
uv pip install -r requirements.txt
uv pip install pytest pytest-asyncio

echo "[7/7] Running pytest..."
export LDAP_URL="ldap://localhost:${DS_PORT}"
export LDAP_BASE_DN="$DS_BASE_DN"
export LDAP_BIND_DN="cn=Directory Manager"
export LDAP_BIND_PASSWORD="$DS_PASSWORD"

uv run pytest tests/ -v -s

echo "Done. Container: $DS_NAME (LDAP localhost:${DS_PORT})"


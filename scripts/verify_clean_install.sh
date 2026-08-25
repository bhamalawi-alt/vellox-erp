#!/usr/bin/env bash
# Clean-install verification for the vellox_agency app.
#
# Proves that a clean Frappe v15 bench can:
#   1. bench get-app this repository,
#   2. install ERPNext + vellox_agency on a fresh site,
#   3. migrate,
#   4. uninstall and reinstall the app,
#   5. run the app test suite.
#
# Usage:
#   scripts/verify_clean_install.sh [repo_url] [branch]
#
# Environment:
#   MARIADB_ROOT_PASSWORD   required; MariaDB root password for site creation
#   VERIFY_FRESH            set to 1 to delete the scratch bench before running
#
# The scratch bench and sites created by this script live under
# /private/tmp/vellox-clean-install-bench and are safe to delete at any time.
set -euo pipefail

REPO_URL="${1:-https://github.com/bhamalawi-alt/vellox-erp}"
BRANCH="${2:-}"
BENCH_DIR="${VERIFY_BENCH:-/private/tmp/vellox-clean-install-bench}"
SITE="ci-clean-install.localhost"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"

if [[ -z "${MARIADB_ROOT_PASSWORD:-}" ]]; then
	echo "ERROR: export MARIADB_ROOT_PASSWORD before running this script." >&2
	exit 1
fi

BENCH_CLI="$(command -v bench || true)"
if [[ -z "$BENCH_CLI" ]]; then
	BENCH_CLI="$HOME/Library/Python/3.11/bin/bench"
fi
BENCH="$BENCH_CLI"
GET_APP_ARGS=()
if [[ -n "$BRANCH" ]]; then
	GET_APP_ARGS=(--branch "$BRANCH")
fi

echo "== 1/6 scratch bench at $BENCH_DIR =="
if [[ "${VERIFY_FRESH:-0}" == "1" && -d "$BENCH_DIR" ]]; then
	rm -rf "$BENCH_DIR"
fi
if [[ ! -d "$BENCH_DIR" ]]; then
	"$BENCH_CLI" init "$BENCH_DIR" --frappe-branch version-15 \
		--python /usr/local/opt/python@3.11/bin/python3.11 >/dev/null
fi
# Start the exact redis instances this bench's config expects (ports may
# differ from 11000/13000 when other benches are running).
for KEY in redis_cache redis_queue redis_socketio; do
	PORT="$(python3 -c "import json,sys;print(json.load(open('$BENCH_DIR/sites/common_site_config.json'))['$KEY'].rsplit(':',1)[1])")"
	redis-cli -p "$PORT" ping >/dev/null 2>&1 || { nohup redis-server --port "$PORT" &>/dev/null & }
done
sleep 2
cd "$BENCH_DIR"

echo "== 2/6 fetch erpnext, then bench get-app $REPO_URL ${BRANCH:+(branch $BRANCH)} =="
if [[ ! -d "$BENCH_DIR/apps/erpnext" ]]; then
	"$BENCH" get-app erpnext --branch version-15 >/dev/null
fi
REPO_NAME="$(basename "$REPO_URL")"
REPO_NAME="${REPO_NAME%.git}"
# bench renames the clone to the package name read from pyproject.toml;
# clear both so reruns never hit an existing-directory error.
rm -rf "$BENCH_DIR/apps/$REPO_NAME" "$BENCH_DIR/apps/vellox_agency"
"$BENCH" get-app "$REPO_URL" "${GET_APP_ARGS[@]+"${GET_APP_ARGS[@]}"}" >/dev/null

echo "== 3/6 fresh site $SITE with erpnext + vellox_agency =="
"$BENCH" drop-site "$SITE" --force --mariadb-root-password "$MARIADB_ROOT_PASSWORD" >/dev/null 2>&1 || true
"$BENCH" new-site "$SITE" \
	--mariadb-root-password "$MARIADB_ROOT_PASSWORD" \
	--admin-password "$ADMIN_PASSWORD" \
	--db-name vellox_ci_install \
	--install-app erpnext \
	--install-app vellox_agency | tail -1

echo "== 4/6 migrate =="
"$BENCH" --site "$SITE" migrate >/dev/null
echo "migrate OK"

echo "== 5/6 uninstall + reinstall vellox_agency =="
"$BENCH" --site "$SITE" uninstall-app vellox_agency --yes >/dev/null
"$BENCH" --site "$SITE" install-app vellox_agency >/dev/null
"$BENCH" --site "$SITE" migrate >/dev/null
"$BENCH" --site "$SITE" list-apps | grep -q vellox_agency
echo "uninstall/reinstall OK"

echo "== 6/6 app test suite =="
"$BENCH" --site "$SITE" set-config allow_tests true
"$BENCH" --site "$SITE" run-tests --app vellox_agency

echo ""
echo "CLEAN INSTALL VERIFICATION PASSED"

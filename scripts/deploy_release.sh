#!/usr/bin/env bash
# Deploy a release to a bench with prechecks, backup, migration, build,
# health checks and a documented rollback path.
#
# Usage:
#   scripts/deploy_release.sh <site> <app> <release_ref> [bench_dir]
#
#   release_ref   a git tag or commit of the app repository to deploy.
#
# Environment:
#   MARIADB_ROOT_PASSWORD  required (used only by the pre-deploy backup).
#
# Rollback: the script takes an encrypted pre-deploy backup and records the
# previous app ref in the deployment log; rollback = re-checkout previous
# ref, migrate, then restore that backup if the schema moved forward.
set -euo pipefail

SITE="${1:?usage: deploy_release.sh <site> <app> <release_ref> [bench_dir]}"
APP="${2:?}"
RELEASE_REF="${3:?}"
BENCH_DIR="${4:-/private/tmp/vellox-frappe-bench}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$HOME/vellox-backups/deployments"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$STAMP-$SITE.log"
exec > >(tee -a "$LOG") 2>&1

fail() { echo "DEPLOY FAILED: $*" >&2; exit 1; }

echo "== PRECHECKS =="
git -C "$BENCH_DIR/apps/$APP" fetch --tags --quiet
git -C "$BENCH_DIR/apps/$APP" rev-parse --verify "$RELEASE_REF" >/dev/null \
	|| fail "release ref $RELEASE_REF not found"
[[ -z "$(git -C "$BENCH_DIR/apps/$APP" status --porcelain)" ]] \
	|| fail "app worktree is dirty"

DISK_OK="$(df -P "$BENCH_DIR" | awk 'END{print int($5) < 90}')"
[[ "$DISK_OK" == "1" ]] || fail "less than 10% disk space available"

PREV_REF="$(git -C "$BENCH_DIR/apps/$APP" rev-parse --short HEAD)"
echo "deploying $APP@$RELEASE_REF over $PREV_REF on $SITE"

echo "== PRE-DEPLOY BACKUP =="
"$SCRIPT_DIR/backup_site.sh" "$SITE" "$BENCH_DIR"

echo "== CHECKOUT + DEPENDENCIES + MIGRATE + BUILD =="
git -C "$BENCH_DIR/apps/$APP" checkout -q "$RELEASE_REF"
(cd "$BENCH_DIR" && \
	bench --site "$SITE" migrate && \
	bench build --app "$APP" && \
	bench --site "$SITE" clear-cache)

echo "== HEALTH CHECKS =="
(cd "$BENCH_DIR" && bench --site "$SITE" list-apps | grep -q "$APP") \
	|| fail "app missing after deploy"
HTTP="$(curl -s http://127.0.0.1:8000/api/method/ping || true)"
[[ "$HTTP" == *"pong"* ]] || {
	echo "health check failed (web on :8000 answered: '$HTTP')" >&2
	echo "ROLLBACK: git -C apps/$APP checkout $PREV_REF && bench migrate; then restore pre-deploy backup if schema moved"
	fail "see above"
}

echo "DEPLOY OK: $APP@$RELEASE_REF live on $SITE (previous: $PREV_REF)"
echo "rollback procedure recorded in this log"

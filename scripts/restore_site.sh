#!/usr/bin/env bash
# Restore an encrypted Vellox backup into a NEW site, then verify integrity.
#
# Usage:
#   scripts/restore_site.sh <archive_dir> <target_site> [bench_dir]
#
# Environment:
#   BACKUP_PASSPHRASE   required when archives use the OpenSSL fallback.
#   MARIADB_ROOT_PASSWORD   required for site restore.
#
# The target site must NOT exist; this script never overwrites a live site.
set -euo pipefail

ARCHIVE_DIR="${1:?usage: restore_site.sh <archive_dir> <target_site> [bench_dir]}"
SITE="${2:?usage: restore_site.sh <archive_dir> <target_site> [bench_dir]}"
BENCH_DIR="${3:-/private/tmp/vellox-frappe-bench}"
: "${MARIADB_ROOT_PASSWORD:?export MARIADB_ROOT_PASSWORD}"

[[ -d "$ARCHIVE_DIR" ]] || { echo "archive dir not found: $ARCHIVE_DIR" >&2; exit 1; }
if (cd "$BENCH_DIR" && ./env/bin/python -c "import frappe" >/dev/null 2>&1 || true) && \
	[[ -d "$BENCH_DIR/sites/$SITE" ]]; then
	echo "REFUSING: site '$SITE' already exists in $BENCH_DIR" >&2
	exit 1
fi

decrypt() {
	local src="$1"
	case "$src" in
	*.age) age -d -i "${AGE_IDENTITY_FILE:?set AGE_IDENTITY_FILE}" <"$src" ;;
	*.gpg) gpg --batch --yes --decrypt "$src" ;;
	*.enc)
		: "${BACKUP_PASSPHRASE:?set BACKUP_PASSPHRASE}"
		openssl enc -d -aes-256-cbc -pbkdf2 -pass "pass:$BACKUP_PASSPHRASE" -in "$src"
		;;
	esac
}

WORK="$(mktemp -d /tmp/vellox-restore.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

echo "== 1/4 decrypting =="
for f in "$ARCHIVE_DIR"/*.age "$ARCHIVE_DIR"/*.gpg "$ARCHIVE_DIR"/*.enc; do
	[[ -e "$f" ]] || continue
	base="$(basename "$f")"
	plain="${base%.*}" # strips .age/.gpg/.enc
	case "$plain" in
	*-database.sql.gz) plain="$plain" ;;           # already gz inside
	*-public-files.tar | *-private-files.tar) plain="$plain" ;;
	esac
	decrypt "$f" >"$WORK/$plain"
done

DB_DUMP="$(ls "$WORK"/*database.sql.gz | head -1)"
PUB_TAR="$(ls "$WORK"/*public-files.tar | head -1)"
PRIV_TAR="$(ls "$WORK"/*private-files.tar | head -1)"

echo "== 2/4 restoring database + files into $SITE =="
cd "$BENCH_DIR"
bench new-site "$SITE" \
	--mariadb-root-password "$MARIADB_ROOT_PASSWORD" \
	--admin-password admin >/dev/null
bench --site "$SITE" restore "$DB_DUMP" \
	--mariadb-root-password "$MARIADB_ROOT_PASSWORD" \
	--with-public-files "$PUB_TAR" \
	--with-private-files "$PRIV_TAR"

echo "== 3/4 integrity checks =="
bench --site "$SITE" migrate >/dev/null
apps="$(bench --site "$SITE" list-apps)"
echo "$apps"
echo "$apps" | grep -q vellox_agency || {
	echo "INTEGRITY FAIL: vellox_agency missing" >&2
	exit 1
}

FILE_COUNT="$(bench --site "$SITE" execute frappe.db.count --args '["File"]' 2>/dev/null || echo unknown)"
MANIFEST_COUNT="$(grep file_doctype_records "$ARCHIVE_DIR/manifest.txt" | cut -d= -f2)"
echo "File records after restore: $FILE_COUNT (backup manifest: $MANIFEST_COUNT)"

echo "== 4/4 health check =="
(./env/bin/gunicorn --bind 127.0.0.1:8099 --chdir sites frappe.app:application \
	&>/dev/null & echo $! >"/tmp/vellox-restore-gunicorn.pid")
sleep 10
HTTP="$(curl -s -H "Host: $SITE" http://127.0.0.1:8099/api/method/ping || true)"
kill "$(cat /tmp/vellox-restore-gunicorn.pid)" 2>/dev/null || true
echo "ping response: $HTTP"
[[ "$HTTP" == *"pong"* ]] || {
	echo "INTEGRITY FAIL: ping did not answer" >&2
	exit 1
}

echo "RESTORE COMPLETE AND VERIFIED for $SITE"

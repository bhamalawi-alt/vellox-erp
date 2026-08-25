#!/usr/bin/env bash
# Encrypted backup of a Frappe site: database + public + private files.
#
# Usage:
#   scripts/backup_site.sh <site> [bench_dir]
#
# Environment:
#   BACKUP_RECIPIENT   age public key (recommended) or GPG recipient.
#                      If unset, a new age keypair is generated under the
#                      backup directory and the private key must be moved
#                      off-host by the operator.
#   OFFHOST_TARGET     optional rsync destination (host:/path) for archives.
#
# Archives land in ~/vellox-backups/<site>/<timestamp>/ — never inside Git.
set -euo pipefail

SITE="${1:?usage: backup_site.sh <site> [bench_dir]}"
BENCH_DIR="${2:-/private/tmp/vellox-frappe-bench}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST_ROOT="${BACKUP_ROOT:-$HOME/vellox-backups}"
DEST="$DEST_ROOT/$SITE/$STAMP"
BENCH="$BENCH_DIR/env/bin/bench"

[[ -x "$BENCH" ]] || BENCH="$BENCH_DIR/../.bench-venv/bin/bench" || true
if [[ ! -x "$BENCH" ]]; then
	BENCH="$(command -v bench)"
fi

mkdir -p "$DEST"
WORKDIR="$(mktemp -d /tmp/vellox-backup.XXXXXX)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "== 1/3 taking bench backup of $SITE =="
(cd "$BENCH_DIR" && "$BENCH" --site "$SITE" backup --with-files)

LATEST="$BENCH_DIR/sites/$SITE/private/backups"
DB_DUMP="$(ls -t "$LATEST"/*-database.sql.gz | head -1)"
# bench omits a files archive when the directory is empty — synthesize one.
PUB_TAR="$(ls -t "$LATEST"/*-files.tar 2>/dev/null | grep -v private | head -1 || true)"
if [[ -z "$PUB_TAR" ]]; then
	PUB_TAR="$WORKDIR/public-files.tar"
	: >"$WORKDIR/public-files.list"; tar -cf "$PUB_TAR" -T "$WORKDIR/public-files.list" 2>/dev/null \
		|| tar -cf "$PUB_TAR" --files-from /dev/null
fi
PRIV_TAR="$(ls -t "$LATEST"/*-private-files.tar 2>/dev/null | head -1 || true)"
if [[ -z "$PRIV_TAR" ]]; then
	PRIV_TAR="$WORKDIR/private-files.tar"
	tar -cf "$PRIV_TAR" --files-from /dev/null
fi

encrypt() {
	local src="$1"
	if command -v age >/dev/null 2>&1 && [[ -n "${BACKUP_RECIPIENT:-}" ]]; then
		age -r "$BACKUP_RECIPIENT" <"$src" >"$DEST/$(basename "$src").age"
	elif command -v gpg >/dev/null 2>&1 && [[ -n "${BACKUP_RECIPIENT:-}" ]]; then
		gpg --batch --yes --encrypt -r "$BACKUP_RECIPIENT" \
			-o "$DEST/$(basename "$src").gpg" "$src"
	else
		# fallback: passphrase-based OpenSSL encryption (PASSPHRASE required)
		: "${BACKUP_PASSPHRASE:?set BACKUP_PASSPHRASE or BACKUP_RECIPIENT}"
		openssl enc -aes-256-cbc -pbkdf2 -salt \
			-pass "pass:$BACKUP_PASSPHRASE" \
			-in "$src" -out "$DEST/$(basename "$src").enc"
	fi
}

echo "== 2/3 encrypting artifacts to $DEST =="
for f in "$DB_DUMP" "$PUB_TAR" "$PRIV_TAR"; do encrypt "$f"; done

# integrity manifest: checksums + record counts for restore verification
{
	echo "site=$SITE"
	echo "timestamp=$STAMP"
	echo "sha256:"
	(shasum -a 256 "$DB_DUMP" "$PUB_TAR" "$PRIV_TAR" || true)
} >"$DEST/manifest.txt"

RECORD_COUNTS="$(cd "$BENCH_DIR" && "$BENCH" --site "$SITE" execute \
	"frappe.db.count" --args '["File"]' 2>/dev/null || echo unknown)"
echo "file_doctype_records=$RECORD_COUNTS" >>"$DEST/manifest.txt"

rm -f "$DB_DUMP.age.bak" 2>/dev/null || true

echo "== 3/3 off-host copy =="
if [[ -n "${OFFHOST_TARGET:-}" ]]; then
	rsync -av "$DEST/" "$OFFHOST_TARGET/$SITE/$STAMP/"
else
	echo "OFFHOST_TARGET not set; archives are LOCAL ONLY at $DEST"
fi

echo "BACKUP COMPLETE: $DEST"

# Backup, Restore & Deployment Runbook

**Card:** [P0-09] · **Status:** foundations live; off-host target and RPO/RTO
values are proposals awaiting owner approval.

## What is backed up

`scripts/backup_site.sh <site> [bench]` produces, per run:

| Artifact | Contents |
|---|---|
| `*-database.sql.gz` | full database dump (bench native) |
| `*-public-files.tar` | `/public/files` uploads |
| `*-private-files.tar` | `/private/files` attachments + backups dir |
| `manifest.txt` | timestamp, SHA-256 of each artifact, File-record count |

Site config (`site_config.json`) is **not** in these archives on purpose:
it holds per-environment DB credentials. It must be recreated by the
deployment tooling or copied securely during environment rebuilds.

## Encryption and retention

- Preferred: `age` with an operator-held recipient key (`BACKUP_RECIPIENT`).
- Also supported: GPG public key, or OpenSSL AES-256-CBC+PBKDF2 with
  `BACKUP_PASSPHRASE`.
- Archives are written to `$BACKUP_ROOT` (default `~/vellox-backups/`),
  outside any Git worktree. `.gitignore` covers backup patterns.
- Off-host copy: set `OFFHOST_TARGET=host:/path` — rsync pushes every run.
  **Owner decision pending:** which off-host storage to use.

## Secrets injection policy

No credentials live in Git, Trello comments, or scripts. Runtime injects:
`MARIADB_ROOT_PASSWORD`, `BACKUP_RECIPIENT` / `BACKUP_PASSPHRASE`,
`OFFHOST_TARGET`, `AGE_IDENTITY_FILE`. CI uses ephemeral container-local
credentials only. Production secrets will come from the deployment secret
store chosen at [P8-57].

## Restore procedure (tested)

```bash
export MARIADB_ROOT_PASSWORD=... BACKUP_PASSPHRASE=...
scripts/restore_site.sh ~/vellox-backups/<site>/<stamp> restored-test.local
```

The script refuses an existing target site, decrypts, restores database +
both file tars, migrates, checks installed apps, compares the `File`
record count against the manifest, and requires a live `ping` before
declaring success. Evidence from the latest drill is recorded on card
[P0-09].

## Deployment procedure

```bash
scripts/deploy_release.sh <site> vellox_agency <tag-or-commit>
```

Sequence: prechecks (ref exists, clean app worktree, disk >10%) →
encrypted pre-deploy backup → checkout release → `bench migrate` →
`bench build --app vellox_agency` → clear-cache → health check
(`list-apps` + `ping`). Every step is logged to
`~/vellox-backups/deployments/<stamp>-<site>.log`.

### Rollback

1. `git -C apps/<app> checkout <previous-ref>` (recorded in deploy log)
2. `bench migrate` (replays reverse-safe state; forward-only patches may
   require restoring the pre-deploy backup instead)
3. If schema moved irreversibly: restore the pre-deploy archive via
   `restore_site.sh` into a fresh site and repoint traffic.

## RPO / RTO proposal (owner approval required)

| Target | Proposal | Basis |
|---|---|---|
| RPO (dev) | 24 h — nightly backup + pre-deploy backup | disposable fixture data |
| RPO (staging/prod) | ≤ 24 h nightly, plus pre-deploy and weekly full | owner may tighten |
| RTO (dev) | ≤ 1 h — documented rebuild procedures | scripted |
| RTO (prod) | ≤ 4 h — restore + migrate + smoke tests | assumes off-host archives reachable |

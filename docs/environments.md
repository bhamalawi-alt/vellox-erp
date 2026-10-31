# Vellox ERP — Environment Register

Established by [P0-05]. Every environment below is either **live today** or a
**template** with no credentials. Staging and production become real only at
their deployment cards ([P8-54]+), which must re-validate this document.

## Inventory

| Environment | Host / path | Site | Database | Purpose |
|---|---|---|---|---|
| Development | `~/vellox-bench` (app soft-linked from the repo checkout) | `vellox.localhost` | `vellox_erp_dev` | Day-to-day use and browser checks; `mute_emails` on |
| Local test | same bench | `vellox-test.localhost` | `vellox_test` | The only place tests run (`allow_tests`); tests change shared settings, so never the development site |
| Local clean-install test | `/private/tmp/vellox-clean-install-bench` | `ci-clean-install.localhost` | `vellox_ci_install` | Scratch proof by `scripts/verify_clean_install.sh`; script-owned, disposable |
| Automated CI test | GitHub Actions runner (ephemeral) | `ci.localhost` | `vellox_ci` (in throwaway MariaDB container) | `.github/workflows/ci.yml` per push/PR |
| Staging | — template only — | *unassigned* | *unassigned* | Release-candidate UAT ([P8-54]) |
| Production | — template only — | *unassigned* | *unassigned* | Go-live ([P8-58]) |

Legacy residue: older benches (a `/private/tmp/vellox-frappe-bench`, and a
Frappe v17-dev bench on SQLite that fails the compatibility gate) predate the
current setup and are **retired**. They serve nothing and are never
referenced by CI, scripts, or documentation. (Updated 2026-10-31, [P3-101].)

## Ports and processes (development machine)

| Port | Process | Owner |
|---|---|---|
| 3306 | MariaDB 10.6 in Docker (container `vellox-mariadb`) | shared by dev + scratch benches |
| 8000 | `bench start` web (when running) | development bench |
| 8080 | ad-hoc `bench serve` for quick checks | started manually per session |
| 11000 / 13000 | redis_queue / redis_cache of whichever bench was initialized first | see note |

> Both local benches default to ports 11000/13000. The one initialized
> second auto-increments (e.g. 11001/13001) via its own
> `sites/common_site_config.json`. Always confirm a bench's ports from its
> config before starting services.

## Database ownership

- `vellox_erp_dev` — development data; disposable fixtures only; recreated by
  documented rebuild procedure if corrupted.
- `vellox_ci_install` — owned by the verifier script; dropped/recreated each run.
- `vellox_ci` — lives only inside a CI container; destroyed with the runner.

## Environment-specific settings

| Setting | Development | CI | Staging (template) | Production (template) |
|---|---|---|---|---|
| `allow_tests` | false (true on the local test site) | true | false | false |
| `developer_mode`/`server_script_enabled` | off (set explicitly when needed) | off | off | off |
| `pause_scheduler` | acceptable | n/a | required until UAT says otherwise | required until go-live step |
| `mute_emails` | true (plus a placeholder outgoing Email Account) | n/a | decided at UAT | false |
| Demo/seed data | `DEMO`-prefixed sample records and one test login per job | none beyond fixtures | controlled demo/UAT set ([P7-48]) | migrated real data only |
| Credentials location | local shell env only | GitHub-managed, none committed | deployment secret store | deployment secret store |

Staging and production configuration MUST NOT contain development
credentials; each gets its own database user, passwords from the secret
store, and its own `site_config.json` created during deployment cards.

## Health checks and recovery

1. **Site up:** `curl -s http://<host>/api/method/ping` → `{"message":"pong"}`
2. **Apps correct:** `bench --site <site> list-apps` shows frappe, erpnext, vellox_agency
3. **DB reachable:** `bench --site <site> console` runs `frappe.db.get_value("System Settings","name")`
4. **Queue alive:** `redis-cli -p <queue-port> ping`
5. **Scheduler:** `bench --site <site> doctor` reports healthy workers

### Recovery: rebuild a development site

```bash
cd ~/vellox-bench
bench drop-site vellox.localhost --force --mariadb-root-password "$MARIADB_ROOT_PASSWORD"
bench new-site vellox.localhost --mariadb-root-password "$MARIADB_ROOT_PASSWORD" \
    --admin-password "$ADMIN_PASSWORD" --db-name vellox_erp_dev \
    --install-app erpnext --install-app vellox_agency
bench --site vellox.localhost migrate   # install skips most Vellox setup
bench --site vellox.localhost set-config mute_emails 1
```

The test site is rebuilt the same way with `vellox-test.localhost`,
`--db-name vellox_test`, then `set-config allow_tests true`.

### Recovery: after a host reboot

Start the MariaDB container (`docker start vellox-mariadb`), then
`bench start` in `~/vellox-bench`. The scratch bench used by
`scripts/verify_clean_install.sh` lives under `/private/tmp` and is rebuilt
by that script when needed.

## Failed-site policy

A `.failed` directory is created by Frappe when site operations crash. Policy:
never let a scheduler keep targeting it — immediately back it up (tarball into
`archived/`), inspect logs, then remove the directory once the cause is fixed.
No `.failed` directories exist anywhere as of this card's completion.

# Vellox ERP — Environment Register

Established by [P0-05]. Every environment below is either **live today** or a
**template** with no credentials. Staging and production become real only at
their deployment cards ([P8-54]+), which must re-validate this document.

## Inventory

| Environment | Host / path | Site | Database | Purpose |
|---|---|---|---|---|
| Development | `/private/tmp/vellox-frappe-bench` | `vellox.localhost` | `vellox_erp_dev` | Active delivery bench; TDD + browser checks |
| Local clean-install test | `/private/tmp/vellox-clean-install-bench` | `ci-clean-install.localhost` | `vellox_ci_install` | Scratch proof by `scripts/verify_clean_install.sh`; script-owned, disposable |
| Automated CI test | GitHub Actions runner (ephemeral) | `ci.localhost` | `vellox_ci` (in throwaway MariaDB container) | `.github/workflows/ci.yml` per push/PR |
| Staging | — template only — | *unassigned* | *unassigned* | Release-candidate UAT ([P8-54]) |
| Production | — template only — | *unassigned* | *unassigned* | Go-live ([P8-58]) |

Legacy residue: an older bench at `/Users/imac/Documents/frappe-bench`
(site `vellox.localhost`, db `_2319bfae6faf36b0`) predates the current
delivery setup and is **retired**: it serves nothing, hosts the obsolete
nested-layout app symlink, and may be deleted by its owner at any time.
It is never referenced by CI, scripts, or documentation.

## Ports and processes (development machine)

| Port | Process | Owner |
|---|---|---|
| 3306 | MariaDB 10.6 (`brew services`) | shared by dev + scratch benches |
| 6379 | Redis (`brew services`) | general; unused by benches |
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
| `allow_tests` | true | true | false | false |
| `developer_mode`/`server_script_enabled` | off (set explicitly when needed) | off | off | off |
| `pause_scheduler` | acceptable | n/a | required until UAT says otherwise | required until go-live step |
| Demo/seed data | deterministic test fixtures only | none beyond fixtures | controlled demo/UAT set ([P7-48]) | migrated real data only |
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
cd /private/tmp/vellox-frappe-bench
bench drop-site vellox.localhost --force --mariadb-root-password "$MARIADB_ROOT_PASSWORD"
bench new-site vellox.localhost --mariadb-root-password "$MARIADB_ROOT_PASSWORD" \
    --admin-password admin --db-name vellox_erp_dev \
    --install-app erpnext --install-app vellox_agency
bench --site vellox.localhost set-config allow_tests true
```

### Recovery: rebuild everything after a host reboot

`/private/tmp` is volatile by design. Re-run:

```bash
scripts/verify_clean_install.sh   # proves toolchain + rebuilds scratch bench
# then follow the development-bench init steps in README "Getting Started"
```

## Failed-site policy

A `.failed` directory is created by Frappe when site operations crash. Policy:
never let a scheduler keep targeting it — immediately back it up (tarball into
`archived/`), inspect logs, then remove the directory once the cause is fixed.
No `.failed` directories exist anywhere as of this card's completion.

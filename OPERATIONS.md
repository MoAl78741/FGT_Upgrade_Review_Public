# Installation operations and recovery

Choose the encrypted **GUI/API backup** in [System administration](docs/ADMINISTRATION.md) for ordinary recovery. The **offline private CLI archive** below covers the database and uploads only; it does not include the separate `/system` administration volume or proxy configuration/CA volumes. Back up those operator-controlled volumes and Compose configuration separately for full offline disaster recovery. Public backups must exclude visitor content.

Use the supported hardened Docker deployment for production. The default Compose installation binds only to localhost; LAN access requires TLS and authenticated access. See [team setup](TEAM_INSTALLATION.md) for individual accounts. The app's **Setup & support** page provides the checklist and a previewable diagnostic download.

## Backup

Back up before upgrading and regularly according to your recovery needs. The offline CLI described below supplies an on-demand ZIP tool. The separate GUI/API workflow creates encrypted archives; see [System administration](docs/ADMINISTRATION.md). Neither workflow schedules backups. Archives contain full source PDFs, reviewer notes, account password hashes and audit history. Keep them encrypted at rest using your organization's storage controls, restrict access, and test recovery. The ZIP format itself is not encryption.

1. Stop the application container, leaving the database and uploads volumes intact. Never run two application instances against the same volumes.
2. Mount an operator-controlled backup directory writable by container UID 10001. Do not expose it through the web proxy or commit it to source control. On Linux, provision that directory with ownership `10001:10001` and mode `0700`; on Docker Desktop, ensure the bind mount permits the container user to write.
3. Run the backup command with the same database and uploads mounts. For the repository's default Compose service:

```sh
docker compose stop fgt-upgrade
docker compose run --rm --no-deps -v "$PWD/backups:/backups" fgt-upgrade \
  python -m backend.maintenance backup /backups/installation.zip
docker compose start fgt-upgrade
```

The backup command holds the application's database lease and refuses to run while its API/dispatcher is active. It makes a consistent SQLite snapshot, checks database integrity, and includes upload files with SHA-256 checksums in an archive manifest. Output is owner-only and existing archives are never overwritten. Use a distinct archive name for each backup. A failed backup is not a recovery point; inspect the error and retain the current installation.

For a native development installation, set `DB_PATH` and `UPLOADS_DIR` to the intended installation and run `python -m backend.maintenance backup /path/to/archive.zip` while its API is stopped. The offline database/PDF archive commands are disabled in the public edition. Public operators can use encrypted GUI/API settings-and-certificate backups, which exclude visitor data.

## Restore drill and upgrade

Restore into **new, empty storage**. The tool refuses an existing database, SQLite sidecar files or nonempty uploads. It verifies checksums and integrity before publishing a restored database, rejects unsafe paths/links and compressed archives over the supported limit, and revokes all restored browser sessions. Existing reports, review decisions, named accounts and password hashes retain their identifiers and values. A restoration event is appended to audit history.

The format supports installations up to 4 GiB and 20,000 files. Archives from a future application major version are refused. Checksum validation detects damage; it does not authenticate an untrusted archive. Restore only backups you control. Custom SQLite views, triggers and virtual tables are rejected; the application uses ordinary tables and indexes.

For Docker, create two new volumes, prepare their ownership for UID 10001, and run the intended image with those mounts. The following assumes `NEW_IMAGE` is an exact locally available image tag or digest, `RESTORE_DATA` and `RESTORE_UPLOADS` name the newly prepared volumes, and the archive directory is mounted read-only:

```sh
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
  --user 10001:10001 --tmpfs /tmp:rw,size=192m \
  -e APP_EDITION=private \
  -v "$RESTORE_DATA:/app/data" -v "$RESTORE_UPLOADS:/app/uploads" \
  -v "$PWD/backups:/backups:ro" "$NEW_IMAGE" \
  python -m backend.maintenance restore /backups/installation.zip
```

Start that image against the restored volumes, retaining the old installation and image. Use a separate localhost port or isolated proxy hostname during validation. Confirm:

- Sign-in and workspace assignments work; old session cookies no longer authenticate.
- Report counts and source PDFs match the backup.
- Saved review decisions and checklists survive.
- Report export contains the original evidence and separate annotations.
- The app is healthy after a restart; interrupted jobs are explicitly marked for retry.

Only then switch the deployment to the validated image and volumes. Keep the original image, Compose configuration and original data together for rollback. To roll back, stop the replacement and restore the original configuration pointing at the original image and original volumes. Do not run old application code against a database changed by a newer release unless that combination has been explicitly tested. Additive migrations preserve existing data but do not constitute a general downgrade guarantee.

For native restore drills:

```sh
DB_PATH=/path/to/empty/data/restored.db UPLOADS_DIR=/path/to/empty/uploads \
  python -m backend.maintenance restore /path/to/archive.zip
```

## Safe diagnostics

Private installation administrators can open **Setup & support → Preview diagnostics**, review every field, then download the JSON. The tool includes the app/build revision, OS family, Python version, configured processing limits, known table availability and counts by known job status. It excludes filesystem paths, hostnames, customer/account identifiers, source text, filenames, uploaded configurations, extracted feature profiles and logs. There is no automatic submission to support.

Operators can also run `python -m backend.maintenance diagnostics`. Treat full database archives and application logs as confidential; they are not diagnostic files and must not be attached casually to support requests.

## System administration

See the [administration guide](docs/ADMINISTRATION.md) for GUI encrypted backup/restore, certificate management, public operator access, and private domain profiles, syslog, email notifications and scheduled summaries. These operations are also exposed in Swagger.

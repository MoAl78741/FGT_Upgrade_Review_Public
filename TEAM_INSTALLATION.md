# Private team installation

The private Docker edition enables named accounts by default. Public deployments continue to use temporary browser sessions and do not expose team administration. Native single-user development can explicitly use `TEAM_AUTH_ENABLED=false`.

## First administrator

On a new installation, start the private container and sign in with **admin / password**. The application immediately requires a new password of 14–256 characters before any reports, workspace data, administration or exports are accessible. This restriction is enforced by the API. After changing the password, use the new password for subsequent sign-ins.

The initial account is created only when no accounts exist. Restarting or upgrading never resets an existing account to the default password. Existing accounts, report identifiers, source content and reviews are retained. Legacy unowned imports are assigned to **Existing installation** during initial setup.

An operator upgrading an existing installation can explicitly add the initial `admin` account if it is absent:

```sh
python -m backend.manage_team initialize-admin
```

This private-only local command requires `TEAM_AUTH_ENABLED=true`. It leaves any existing `admin` account unchanged. The account it creates must change its initial password before access. There is no remotely accessible account-bootstrap endpoint.

For LAN access, configure `APP_ORIGIN` to the exact HTTPS address behind your TLS proxy. Keep application ports internal to Docker. The web login provides authentication without an additional proxy password prompt.

For an operator-selected first username/password before first startup, `python -m backend.manage_team bootstrap --username <name>` remains available. It prompts for a password or accepts an owner-only `--password-file`; it refuses installations that already have accounts.

## Customer access

Sign in and open **Account & administration**. Create customer workspaces, then create named accounts and assign workspace access:

| Role | Access |
|---|---|
| Installation administrator | All customers, account administration, full audit history |
| Reviewer | Read, import, edit, export and delete within assigned workspaces |
| Viewer | Read and export within assigned workspaces |

Administrators have access to every workspace. Assign ordinary reviewer or viewer accounts for customer-limited access. Account creation does not send email: share the initial password through your approved secure channel and ask the user to change it from Account. There is no public registration or email recovery.

The customer selector controls the active workspace. Switching customers reloads the page. Another tab with the former workspace cannot save against the changed selection; reload that tab before continuing. Removing membership takes effect on subsequent API requests. Disabling an account, changing administrator access or resetting its password ends all its sessions. A user changing their own password keeps the current session and ends the others. At least one active administrator must remain.

## Local recovery

An operator with access to the database can reset an existing account without email:

```sh
python -m backend.manage_team reset-password --username reviewer
```

This reactivates that account, resets its password and revokes its sessions. It does not turn a non-administrator into an administrator. Use the existing administrator username for administrative recovery. Run against the private database, never the public edition.

## Audit and privacy

Audit events attribute review changes, imports, account changes and workspace assignments to named users. Review decisions and exported annotations include the reviewer name. Audit metadata contains changed field names and revision numbers, not reviewer note bodies, source text, passwords or configuration profiles. Review pages show events for that review; Account shows workspace history, and administrators can view installation history.

Audit history is stored in the installation database. It is not an immutable or externally signed compliance ledger; a database operator can alter it. Existing decisions made before named accounts remain unattributed. Browser-only configuration analysis remains transient and is not included in account requests or audit events.

Sessions use random HttpOnly, SameSite=Strict cookies with an eight-hour expiry, Secure on HTTPS. Only session token hashes are stored. Passwords use salted PBKDF2-HMAC-SHA256 with 600,000 iterations. Sign-in throttling is process-local; the supported single-process deployment also needs appropriate proxy limits if exposed beyond the intended LAN. MFA, SSO and organization self-registration are not included.

## Older-build rollback

Older builds cannot enforce the initial-password flag. Before rolling back, disable any account still awaiting its initial password change and revoke its sessions, or restore the complete pre-upgrade database snapshot. Do not run an older image against an active `admin` / `password` account. The supplied deployment rollback procedure disables a pending initial administrator before selecting the older image.

## System administration

See the [administration guide](docs/ADMINISTRATION.md) for GUI encrypted backup/restore, certificate management, public operator access, and private domain profiles, syslog, email notifications and scheduled summaries. These operations are also exposed in Swagger.

# Changelog

## 0.8.0 (beta), 2026-11-27

First version prepared for `main`.

### Security
- 2FA is required on every page after login, not only under the admin path (before, `/users/`, `/clients/`, `/notifications/` and file downloads opened with just a password).
- django-axes locks the username+IP pair. The previous setting locked by IP alone, and behind Cloudflare every visitor shares one IP, so five wrong passwords from anyone locked everybody out. The real visitor IP is now taken from `CF-Connecting-IP`.
- Public request form: submissions per IP per hour are limited, and so are the number and size of attached files.
- Uploaded files are served in a CSP sandbox, so an uploaded HTML/SVG file can't run scripts in the CRM.
- One upload size limit for every place files are accepted.
- SMTP timeout, so a hanging mail server can't block a request.
- Django 5.2.15 → 5.2.19 (security releases), plus django-otp, requests, urllib3, idna and whitenoise patch updates.

### Data safety
- Two people editing the same request or document: a save no longer silently overwrites changes made after the page was opened. The user sees who changed what, and pressing Save again overwrites on purpose.
- Approving the same lead twice at once no longer overwrites the first approval.
- Concurrent department edits on one request are all kept (row lock).
- Uploaded files are kept in a Docker volume. Before, they lived inside the container and were lost on every redeploy.

### Performance
- Permission checks are cached per request: 60–125 fewer SQL queries per page for non-superusers (request card 171 → 50 queries).
- Request history, owner checks and department labels no longer run one query per row.
- Client list counts rewritten with subqueries: 300 ms → ~1 ms on the dev data, and the cost no longer multiplies as links grow.
- Persistent DB connections; gunicorn serves 12 requests at once (3 processes × 4 threads) instead of 3.

### Mobile
- Fixed horizontal overflow on phone screens (client list filters, company card header, text areas).

### Housekeeping
- `requirements.txt` holds runtime dependencies only; tools moved to `requirements-dev.txt`. Removed the unused `localflavor` package, which conflicted with `django-localflavor`, and the stale `poetry.lock`.
- Documentation consolidated into `docs/`. Internal notes, TODO lists and agent plans removed from the main branch; they remain in git history.
- Fixed Polish plural forms that made `msgfmt --check` fail.

# Cabin Scheduler

Cabin Scheduler is a Django app for managing reservation requests for a shared cabin. The first release targets a single-cabin workflow with invited-user sign-in, admin approval, blackout windows, and a calendar-centric interface.

## Stack

- Django 6
- Python 3.12 managed by `uv`
- SQLite for local development
- PostgreSQL for Oracle Cloud Infrastructure deployment
- Gunicorn + Nginx for production serving

## Local Development

1. Create a local environment file:

   ```bash
   cp .env.example .env
   ```

2. Run migrations:

   ```bash
   uv run python manage.py migrate
   ```

3. Create an admin user:

   ```bash
   uv run python manage.py createsuperuser
   ```

4. Start the development server:

   ```bash
   uv run python manage.py runserver
   ```

5. Sign in at `/accounts/login/` and use `/admin/` to manage invited users, reservation approvals, blackout ranges, and the single seeded cabin.

## Core Workflow

- Invited users authenticate with Django’s built-in auth.
- Authenticated users can browse the calendar and request stays.
- Requests start as `pending`.
- Staff approve or reject requests in `/admin/`.
- Approved reservations and blackout ranges block conflicting dates.

## Key Routes

- `/` home page and schedule summary
- `/calendar/` authenticated availability calendar
- `/reservations/new/` reservation request form
- `/reservations/` reservation list for the current user, or all reservations for staff
- `/admin/` admin moderation and data management

## Environment

Important settings are driven by `.env`:

- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DJANGO_DEBUG`
- `DJANGO_SETTINGS_MODULE`
- `DJANGO_USE_POSTGRES`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`

If `DJANGO_USE_POSTGRES=false`, the app uses local SQLite even if the `POSTGRES_*` values are present in `.env`. Set `DJANGO_USE_POSTGRES=true` when you want to point the app at PostgreSQL.

## OCI Deployment Notes

Target one always-free Ubuntu VM:

1. Bootstrap the host as root:

   ```bash
   export POSTGRES_PASSWORD='replace-with-a-strong-db-password'
   ./deploy/oci_bootstrap.sh
   ```

2. Place the repo at `/opt/cabin-scheduler`.
3. Copy `deploy/prod.env.example` to `/opt/cabin-scheduler/.env` and fill in the real values.
4. For initial IP-based deployment, use:

   - `DJANGO_SETTINGS_MODULE=config.settings_prod`
   - `DJANGO_USE_POSTGRES=true`
   - `DJANGO_ENABLE_HTTPS=false`
   - `DJANGO_SECURE_COOKIES=false`
   - `DJANGO_ALLOWED_HOSTS=<your public IP>`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=http://<your public IP>`

5. Deploy the app as root:

   ```bash
   ./deploy/oci_deploy.sh
   ```

6. If you later add a domain and TLS, update `.env`:

   - `DJANGO_ALLOWED_HOSTS=<your domain>`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://<your domain>`
   - `DJANGO_ENABLE_HTTPS=true`
   - `DJANGO_SECURE_COOKIES=true`
   - `DJANGO_HSTS_SECONDS=3600`

7. Update `PUBLIC_SERVER_NAME` in the deployment environment or the Nginx config, then use Certbot to enable HTTPS.

## Backups

The repo includes `scripts/backup_db.sh` for PostgreSQL backups on OCI. Run it from cron or a systemd timer with the database environment variables available in the shell.

## Tests

Run the baseline test suite with:

```bash
uv run python manage.py test
```

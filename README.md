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

- Admins create enrollment invitations from `/admin/` → **Invitations** → **Add invitation** by entering a guest's email address. **Copy a link to share yourself** is selected by default and needs no email configuration. Click **Create invitation**, then **Copy link**, and paste it into your own email or text message. If clipboard access is unavailable, select the link and copy it manually.
- The link is shown only on the creation page. Copy it before leaving; to get another link, create an invitation for the same email. This replaces the previous link. **Send by email** remains an optional delivery method when email is configured.
- Guests follow the shared link and choose their own username and password. Their account email is fixed to the invited address; enrollment does not grant staff privileges. Share the link directly with the intended guest: anyone holding it can enroll for that address.
- Links expire after seven days and work only once. Opening a link does not consume it. Delete a pending invitation to revoke it.
- Invited users authenticate with Django’s built-in auth.
- Authenticated users can browse the calendar and request stays.
- Requests start as `pending`.
- Authorized staff approve or reject requests through **Review requests** at `/reservations/` (also linked from Django Admin).
- Approved reservations and blackout ranges block conflicting dates.

### Reviewing reservation requests

Administrators with the **change reservation** permission open **Review requests** in the site navigation (`/reservations/`). Pending requests appear first. Click **Review request** to see the requester, guest, cabin, check-in/check-out dates, number of nights, and guest notes. Add an optional private admin note and choose **Approve request** or **Reject request**. Approval checks approved bookings and blackout dates before reserving the stay; conflicts appear on the review screen.

Completed requests show **View decision**, including who reviewed them and when. The review screen only decides pending requests, so repeated or stale submissions cannot overwrite an existing decision. Guests see their reservation status in **My Reservations**; private admin notes stay hidden and no automatic decision emails are sent. Django Admin also includes explicit **Review request** links in the reservation list and **Review and decide** on the edit screen.

## Key Routes

- `/` home page and schedule summary
- `/calendar/` authenticated availability calendar
- `/reservations/new/` reservation request form
- `/reservations/` reservation list for the current user, or all reservations for staff
- `/admin/` admin moderation and data management

## Environment

### Shared documents

Signed-in users can browse and search the shared library at `/documents/`. Staff with the appropriate Django document permissions can upload, edit, replace, publish/unpublish, and delete files directly from this page. Superusers have these permissions automatically. Deletion requires confirmation; unpublished documents are visible only to staff with document permissions. Existing documents remain published after upgrading.

Supported uploads: Word (`.doc`, `.docx`), Excel (`.xls`, `.xlsx`), PowerPoint (`.ppt`, `.pptx`), PDF, TXT, CSV, JPG/JPEG, PNG, GIF, and WebP. The configurable per-file limit defaults to 20 MB (`DOCUMENT_MAX_UPLOAD_BYTES=20971520`). Uploads are checked for allowed filename extensions, non-empty content, and file size. PDFs and supported images can open in a new browser tab; other files download for opening on the user's device.

Files are stored in `media/` and served through authenticated document URLs. Do not expose `/media/` directly through Nginx or a public storage bucket: that would bypass publication and login checks. Include `media/` in backups along with the database. Replaced/deleted files are removed after the database transaction commits, including deletions made through Django Admin. The original uploader is retained when editing a document. If file cleanup fails, Django logs the failure; retain server logs for troubleshooting.

Apply database changes with `uv run python manage.py migrate` when deploying. The bundled Nginx configuration allows 25 MB requests to accommodate a 20 MB file plus form data; if increasing the upload limit, increase Nginx's `client_max_body_size` accordingly.

### Invitation and password-reset email

Copyable invitation links require no email backend. Use the site's public address when creating links for other people, or configure `SITE_URL` to that address; localhost links are only usable on your own laptop. Password resets still require email delivery.

Local development defaults to the console email backend: if you choose **Send by email**, invitation messages appear in the server terminal, and no email reaches an inbox. Password-reset messages also appear there.

For actual delivery, configure your mail provider's SMTP credentials in `.env`:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DEFAULT_FROM_EMAIL=Daniel Dream <your-verified-sender@example.com>
EMAIL_HOST=your-provider-smtp-host
EMAIL_PORT=587
EMAIL_HOST_USER=your-smtp-username
EMAIL_HOST_PASSWORD=your-smtp-password
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
SITE_URL=https://your-public-site.example.com
```

Use your provider's required port/security settings (for implicit TLS on port 465, set `EMAIL_USE_TLS=false` and `EMAIL_USE_SSL=true`). `SITE_URL` is the address recipients can reach; localhost links work only on the machine running the site. If omitted, invitation links use the admin request's origin. Restart the server after changing settings. SMTP credentials stay in `.env`, never in Git.

Admins with permission to add invitations can send them. Delivery errors appear on the invitation form so admins can retry; failed resends preserve the previous link. SMTP acceptance confirms submission to the mail provider, not final inbox delivery.

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

After Certbot adds TLS to the live Nginx site, future runs of `deploy/oci_deploy.sh` will preserve that HTTPS-enabled site file automatically. If you intentionally want to replace the Nginx site from `deploy/nginx.conf`, run with:

```bash
sudo FORCE_NGINX_SITE_REFRESH=true APP_DIR=/opt/cabin-scheduler APP_USER=ubuntu APP_GROUP=www-data SERVICE_NAME=cabin-scheduler ENV_FILE=/opt/cabin-scheduler/.env PUBLIC_SERVER_NAME='your-domain.com www.your-domain.com' bash ./deploy/oci_deploy.sh
```

## Git-Based VM Deploys

For simpler updates, use a Git checkout on the VM instead of re-uploading tarballs.

### One-Time Conversion On The VM

1. Back up your existing environment file:

   ```bash
   sudo cp /opt/cabin-scheduler/.env /tmp/daniel-dream.env.backup
   ```

2. Move the current tarball-based app directory aside:

   ```bash
   sudo mv /opt/cabin-scheduler /opt/cabin-scheduler.pre-git.$(date +%Y%m%d-%H%M%S)
   ```

3. Clone the GitHub repo as `ubuntu`:

   ```bash
   sudo -u ubuntu git clone git@github.com:bigjimdaniel/cabin-scheduler.git /opt/cabin-scheduler
   ```

4. Restore the production environment file:

   ```bash
   sudo mv /tmp/daniel-dream.env.backup /opt/cabin-scheduler/.env
   sudo chown ubuntu:www-data /opt/cabin-scheduler/.env
   sudo chmod 600 /opt/cabin-scheduler/.env
   ```

5. Run a normal deployment once from the Git checkout:

   ```bash
   cd /opt/cabin-scheduler
   sudo APP_DIR=/opt/cabin-scheduler APP_USER=ubuntu APP_GROUP=www-data SERVICE_NAME=cabin-scheduler ENV_FILE=/opt/cabin-scheduler/.env PUBLIC_SERVER_NAME=_ bash ./deploy/oci_deploy.sh
   ```

### Future Updates

After you push changes to GitHub, update the VM with:

```bash
cd /opt/cabin-scheduler
sudo APP_DIR=/opt/cabin-scheduler APP_USER=ubuntu APP_GROUP=www-data SERVICE_NAME=cabin-scheduler ENV_FILE=/opt/cabin-scheduler/.env PUBLIC_SERVER_NAME=_ bash ./deploy/oci_git_update.sh
```

This script:

- pulls the latest code from `origin/main`
- runs `uv sync`
- runs Django migrations
- collects static assets
- restarts Gunicorn and Nginx
- preserves the live Certbot-managed Nginx site if HTTPS is already configured

## Backups

The repo includes `scripts/backup_db.sh` for PostgreSQL backups on OCI. Run it from cron or a systemd timer with the database environment variables available in the shell.

## Tests

Run the baseline test suite with:

```bash
uv run python manage.py test
```

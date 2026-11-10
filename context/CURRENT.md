# Current work

- Implement enrollment invitations: admin supplies email, creates a copyable link by default, and recipient chooses username/password. Email sending remains optional.
- Existing local SQLite database and Python environment are set up; all original 23 migrations applied. Do not reset data or recreate users.
- Preserve pre-existing user change in deploy/nginx.conf.
- Use expiring, single-use invitation links bound to the invited email, Django password validation, and configurable SMTP delivery. Console email remains useful locally.
- Completed: Invitation model and migration 0006 (applied locally), admin email entry and resend/revoke support, hashed random tokens, seven-day expiry, atomic single-use enrollment, username/password creation, fixed invited email, SMTP configuration and README instructions.
- Added copyable links to existing admin invite form: default link delivery, one-time display with clipboard button/manual fallback, optional email delivery retained. Link creation never calls the email backend; regeneration invalidates old links. Raw links are not stored in sessions or admin logs, and admin responses disable caching/referrers. README updated.
- Verification: all 44 Django tests passed; system check, makemigrations --check, and git diff --check clean. Existing users/data retained. Copy-link change needs no new migration.
- Fixed browser-only 403 on invite POST: no-referrer caused Origin: null, rejected by Django CSRF. Changed admin invitation and enrollment responses to Referrer-Policy: same-origin (cross-site referrers still suppressed). Verified browser POST reaches existing-account validation. All 46 tests pass, including new CSRF-enforced admin/enrollment round trips and null-origin rejection.
- Delivery limitation: existing local email configuration defaults to console output. Real inbox delivery needs provider SMTP host/credentials, verified sender, and reachable SITE_URL in .env; no real invitations sent during implementation.
- Next: user can create/copy links at /admin/scheduler/invitation/add/ without SMTP. Use a public site origin or SITE_URL for remote guests; localhost links only work on the host laptop. Production requires applying migration 0006 on deployment. SMTP remains optional for invite sending and needed for automated password-reset delivery.

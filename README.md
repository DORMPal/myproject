# myproject

## Google OAuth (KU accounts only)

1. Install backend deps: `pip install -r backend/requirements.txt`
2. Create Google OAuth client creds and set env vars before running Django:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
3. Run migrations (django-allauth tables): `python manage.py migrate`
4. Start server and visit `/auth/google/login/` to sign in with a `@ku.th` account.

## Daily expiration notifications

- Run `python manage.py migrate` after pulling to create the new `notification` table.
- Schedule the daily job (example cron): `0 3 * * * /bin/bash /path/to/backend/run_daily_notifications.sh >> /var/log/expiration_notifications.log 2>&1`
- The script calls `manage.py generate_expiration_notifications` to insert unread notifications for stocks expiring in 4 days.

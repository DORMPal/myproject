# myproject

## Google OAuth (KU accounts only)

1. Install backend deps: `pip install -r backend/requirements.txt`
2. Create Google OAuth client creds and set env vars before running Django:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
3. Run migrations (django-allauth tables): `python manage.py migrate`
4. Start server and visit `/auth/google/login/` to sign in with a `@ku.th` account.

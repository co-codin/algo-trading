# Auth Admin Ops Skill

## When To Use

Use this when changing registration, login, activation, expiration, profile, or admin user-management behavior.

## Checklist

- Treat `is_active` as feature access and `is_admin` as admin access.
- Keep the default admin seeder idempotent.
- Never show the Admin tab unless `is_admin` is true.
- Keep inactive users able to view and edit profile data only.
- Update profile fields and public user payloads together.
- Make admin updates explicit and auditable through tests.

## Verification

- Run `python3 -m unittest tests.test_auth tests.test_web_app`.
- Confirm inactive users cannot access protected trading APIs.
- Confirm admin-only endpoints reject non-admin users.

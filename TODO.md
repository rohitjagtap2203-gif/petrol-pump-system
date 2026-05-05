# Live Server Fix - Complete Database Schema & Deployment
Current Status: Diagnosed missing tables causing 500 errors on prod Postgres.

## Approved Plan Steps:
- [x] 1. Update app.py: Fix DATABASE_URL parsing + Complete ensure_database_schema() (all tables: users, fuel, sales, customers, login_attempts + defaults data: admin/fuel).
- [x] 2. Ensure schema runs in app context on startup.
- [x] 3. Create render.yaml for auto Postgres provisioning.
- [x] 4. Update requirements_production.txt: Pin compatible deps (psycopg2-binary, gunicorn).
- [ ] 5. Verify no breaking changes (SQLite local compat).
- [ ] 6. Test locally with fake DATABASE_URL.
- [ ] 7. Deploy and check server logs.
- [ ] 8. Test prod: Login admin/admin123, dashboard, sales.
- [ ] 9. Update TODO.md complete + attempt_completion.

**Admin creds**: admin / admin123
**Changes preserve**: Local SQLite, all features, raw SQL (no ORM).


# Petrol Pump System - Fix Default Admin Creation ✅

## Task: Add idempotent default admin user creation in ensure_database_schema()

### Steps:
- [x] 1. Create this TODO.md
- [x] 2. Edit app.py: Add admin creation logic in ensure_database_schema() PostgreSQL branch
- [x] 3. Verify edit with read_file
- [ ] 4. Test: Run app.py with DATABASE_URL, check admin created
- [ ] 5. Test login with admin/admin123
- [x] 6. Update TODO.md with completion
- [ ] 7. attempt_completion

**Admin credentials**: username=admin, password=admin123, role=admin

**Updated ensure_database_schema() function:**

```python
def ensure_database_schema():
    """
    Create DB schema on startup (idempotent).
    - SQLite: original schema
    - Postgres: compatible schema
    """
    conn = get_db()
    if conn is None:
        return

    cursor = conn.cursor()

    if DATABASE_URL:
        # PostgreSQL schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users(
                id SERIAL PRIMARY KEY,
                name TEXT,
                username TEXT NOT NULL UNIQUE,
                email TEXT,
                phone TEXT,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Employee',
                status TEXT NOT NULL DEFAULT 'Active',
                failed_login_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                last_login_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create default admin user if not exists
        cursor.execute("SELECT id FROM users WHERE username=%s", ("admin",))
        admin = cursor.fetchone()
        if not admin:
            password = generate_password_hash("admin123")
            cursor.execute(
                "INSERT INTO users (name, username, password, role) VALUES (%s, %s, %s, %s)",
                ("Admin", "admin", password, "admin")
            )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts(
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                success INTEGER NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        # SQLite schema (existing)
        cursor.execute("CREATE TABLE IF NOT EXISTS users("
                       "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                       "name TEXT,"
                       "username TEXT NOT NULL UNIQUE,"
                       "email TEXT,"
                       "phone TEXT,"
                       "password TEXT NOT NULL,"
                       "role TEXT NOT NULL DEFAULT 'Employee',"
                       "status TEXT NOT NULL DEFAULT 'Active',"
                       "failed_login_attempts INTEGER NOT NULL DEFAULT 0,"
                       "locked_until TEXT,"
                       "last_login_at TEXT,"
                       "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                       ")")

        cursor.execute("CREATE TABLE IF NOT EXISTS login_attempts("
                       "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                       "username TEXT NOT NULL,"
                       "success INTEGER NOT NULL,"
                       "ip_address TEXT,"
                       "user_agent TEXT,"
                       "message TEXT,"
                       "timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                       ")")

    conn.commit()
    conn.close()
```



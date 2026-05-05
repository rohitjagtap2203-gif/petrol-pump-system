import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect("petrol_pump.db")
cursor = conn.cursor()

# ==================== USERS TABLE ====================
cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    username TEXT NOT NULL UNIQUE,
    email TEXT,
    phone TEXT,
    password TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('Admin','Manager','Employee')),
    status TEXT NOT NULL CHECK(status IN ('Active','Inactive')) DEFAULT 'Active',
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    last_login_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ==================== FUEL TABLE ====================
cursor.execute("""
CREATE TABLE IF NOT EXISTS fuel(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL UNIQUE,
    price REAL NOT NULL DEFAULT 0,
    stock REAL NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ==================== SALES TABLE ====================
cursor.execute("""
CREATE TABLE IF NOT EXISTS sales(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id TEXT NOT NULL UNIQUE,
    customer TEXT NOT NULL,
    phone TEXT,
    fuel_type TEXT NOT NULL,
    liters REAL NOT NULL,
    price REAL NOT NULL,
    total REAL NOT NULL,
    date TEXT NOT NULL,
    employee_id INTEGER,
    FOREIGN KEY(fuel_type) REFERENCES fuel(type),
    FOREIGN KEY(employee_id) REFERENCES users(id)
)
""")

# ==================== CUSTOMERS TABLE ====================
cursor.execute("""
CREATE TABLE IF NOT EXISTS customers(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT UNIQUE,
    total_visits INTEGER DEFAULT 0,
    total_fuel REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ==================== ADD PAYMENT_MODE TO SALES (BACKWARD COMPATIBLE) ====================
cursor.execute("PRAGMA table_info(sales)")
sales_columns = [col[1] for col in cursor.fetchall()]
if 'payment_mode' not in sales_columns:
    cursor.execute("ALTER TABLE sales ADD COLUMN payment_mode TEXT DEFAULT 'Cash'")

# ==================== LOGIN ATTEMPTS TABLE ====================
cursor.execute("""
CREATE TABLE IF NOT EXISTS login_attempts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    success INTEGER NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    message TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ==================== CREATE INDEXES ====================
cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(date)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_fuel_type ON sales(fuel_type)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales(customer)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_bill_id ON sales(bill_id)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_payment_mode ON sales(payment_mode)")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone)")

# ==================== INSERT DEFAULT DATA ====================
cursor.execute("SELECT COUNT(*) FROM fuel")
if cursor.fetchone()[0] == 0:
    cursor.execute("""
        INSERT INTO fuel (type, price, stock) 
        VALUES ('Petrol', 100, 500)
    """)
    cursor.execute("""
        INSERT INTO fuel (type, price, stock) 
        VALUES ('Diesel', 90, 600)
    """)

cursor.execute("SELECT COUNT(*) FROM users")
if cursor.fetchone()[0] == 0:
    cursor.execute("""\n        INSERT INTO users (name, username, password, role) \n        VALUES (%s, %s, %s, %s)\n    """, ('Admin', 'admin', generate_password_hash('admin123'), 'Admin'))

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

conn.commit()
conn.close()

logger.info("✓ Database initialized successfully")
logger.info("✓ Default credentials: username=admin, password=admin123")
logger.info("✓ Fuel types: Petrol (₹100), Diesel (₹90)")
logger.info("✓ Initial stock: 500L Petrol, 600L Diesel")

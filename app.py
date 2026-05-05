import pkgutil
import importlib.util

# Compatibility shim for Python 3.14+ where pkgutil.get_loader was removed
if not hasattr(pkgutil, 'get_loader'):
    def get_loader(name):
        # Flask internal `find_package` may call this with __main__.
        if name == '__main__':
            return None
        spec = importlib.util.find_spec(name)
        return spec.loader if spec is not None else None
    pkgutil.get_loader = get_loader

from flask import Flask, render_template, request, redirect, session, jsonify, flash
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
import os
import logging
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, PasswordField, SelectField, FloatField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, NumberRange, Regexp, Email
from whatsapp_integration import send_formatted_bill_to_whatsapp, validate_whatsapp_phone
from config import SECRET_KEY

# ==================== FORM CLASSES ====================
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=1, max=50)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=1, max=100)])
    remember_me = BooleanField('Remember Me')

class CustomerForm(FlaskForm):
    name = StringField('Customer Name', validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField('Phone', validators=[Regexp(r'^\d{10}$|', message='10 digits or empty')])

class SalesForm(FlaskForm):
    customer = StringField('Customer Name', validators=[DataRequired(), Length(min=1, max=100)])
    phone = StringField('Phone Number', validators=[
        DataRequired(),
        Regexp(r'^\d{10}$', message='Phone number must be exactly 10 digits')
    ])
    payment_mode = SelectField('Payment Mode', choices=[
        ('Cash', 'Cash'),
        ('UPI', 'UPI'),
        ('Card', 'Card')
    ], validators=[DataRequired()], default='Cash')
    fuel_type = SelectField('Fuel Type', choices=[
        ('Petrol', 'Petrol'),
        ('Diesel', 'Diesel')
    ], validators=[DataRequired()])
    liters = FloatField('Liters', validators=[
        DataRequired(),
        NumberRange(min=0.01, max=1000, message='Liters must be between 0.01 and 1000')
    ])

class EmployeeForm(FlaskForm):
    name = StringField('Employee Name', validators=[DataRequired(), Length(min=2, max=100)])
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    email = StringField('Email', validators=[DataRequired(), Length(min=5, max=100)])
    phone = StringField('Phone', validators=[DataRequired(), Regexp(r'^\d{10}$', message='Phone number must be exactly 10 digits')])
    role = SelectField('Role', choices=[('Admin', 'Admin'), ('Manager', 'Manager'), ('Employee', 'Employee')], validators=[DataRequired()])
    status = SelectField('Status', choices=[('Active', 'Active'), ('Inactive', 'Inactive')], validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6, max=100)])

class EmployeeUpdateForm(FlaskForm):
    name = StringField('Employee Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Length(min=5, max=100)])
    phone = StringField('Phone', validators=[DataRequired(), Regexp(r'^\d{10}$', message='Phone number must be exactly 10 digits')])
    role = SelectField('Role', choices=[('Admin', 'Admin'), ('Manager', 'Manager'), ('Employee', 'Employee')], validators=[DataRequired()])
    status = SelectField('Status', choices=[('Active', 'Active'), ('Inactive', 'Inactive')], validators=[DataRequired()])

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = None
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production over HTTPS
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=7)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

# Security and session settings
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15
SESSION_TIMEOUT_MINUTES = 30
REMEMBER_ME_DAYS = 7
csrf = CSRFProtect(app)

# ==================== DATABASE CONNECTION ====================
# Production-ready DB handling:
# - Render provides `DATABASE_URL` for Postgres.
# - For local development, we keep the existing SQLite file fallback.
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[10:]  # Fix for psycopg2
# set by Render Postgres service

def get_db():
    """
    Return a DB connection depending on environment.
    - If DATABASE_URL is set -> Postgres via psycopg2
    - Else -> SQLite (existing behavior) using petrol_pump.db
    """
    if DATABASE_URL:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        # psycopg2 supports autocommit control; we keep it manual where needed
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    else:
        conn = sqlite3.connect("petrol_pump.db")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def get_user_by_username(username):
    """Fetch a user by username."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        return cursor.fetchone()


def is_account_locked(user):
    """Check whether the account is currently locked."""
    if not user:
        return False, None

    locked_until = user['locked_until']
    if locked_until:
        try:
            locked_until_dt = datetime.fromisoformat(locked_until)
            if locked_until_dt > datetime.now():
                return True, locked_until_dt
        except ValueError:
            pass

    return False, None


def set_user_field(username, field, value):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE users SET {field}=%s WHERE username=%s", (value, username))
        conn.commit()
    return True


def reset_failed_logins(username):
    set_user_field(username, 'failed_login_attempts', 0)
    set_user_field(username, 'locked_until', None)


def increment_failed_login(username):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT failed_login_attempts FROM users WHERE username=%s", (username,))
        row = cursor.fetchone()
        failed_attempts = row['failed_login_attempts'] if row else 0
        failed_attempts += 1

        lock_message = ''
        if failed_attempts >= MAX_LOGIN_ATTEMPTS:
            lock_until = datetime.now() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            cursor.execute("UPDATE users SET failed_login_attempts=%s, locked_until=%s WHERE username=%s", (failed_attempts, lock_until.isoformat(), username))
            lock_message = f' Account locked for {LOCKOUT_DURATION_MINUTES} minutes.'
        else:
            cursor.execute("UPDATE users SET failed_login_attempts=%s WHERE username=%s", (failed_attempts, username))

        conn.commit()
    return lock_message


def record_login_attempt(username, success, message=''):
    conn = get_db()
    if conn is None:
        return
    cursor = conn.cursor()
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent', '')
    cursor.execute(
        "INSERT INTO login_attempts (username, success, ip_address, user_agent, message) VALUES (%s, %s, %s, %s, %s)",
        (username, int(success), ip_address, user_agent, message)
    )

    conn.commit()
    
    if DATABASE_URL:
        # Create default admin user if doesn't exist
        cursor.execute("SELECT 1 FROM users WHERE username=%s LIMIT 1", ('admin',))
        if not cursor.fetchone():
            hashed_password = generate_password_hash('admin123')
            cursor.execute(
                "INSERT INTO users (name, username, password, role) VALUES (%s, %s, %s, %s)",
                ('Admin', 'admin', hashed_password, 'admin')
            )
            conn.commit()
            logger.info("Default admin user created (username: admin, password: admin123)")
    
    conn.close()



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
        # PostgreSQL schema - COMPLETE
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fuel(
                id SERIAL PRIMARY KEY,
                type TEXT NOT NULL UNIQUE,
                price NUMERIC NOT NULL DEFAULT 0,
                stock NUMERIC NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sales(
                id SERIAL PRIMARY KEY,
                bill_id TEXT NOT NULL UNIQUE,
                customer TEXT NOT NULL,
                phone TEXT,
                payment_mode TEXT DEFAULT 'Cash',
                fuel_type TEXT NOT NULL,
                liters NUMERIC NOT NULL,
                price NUMERIC NOT NULL,
                total NUMERIC NOT NULL,
                date TIMESTAMP NOT NULL,
                employee_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers(
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT UNIQUE,
                total_visits INTEGER DEFAULT 0,
                total_fuel NUMERIC DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

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

        # Default admin user (idempotent)
        cursor.execute("SELECT id FROM users WHERE username=%s", ("admin",))
        if not cursor.fetchone():
            password = generate_password_hash("admin123")
            cursor.execute(
                "INSERT INTO users (name, username, password, role) VALUES (%s, %s, %s, %s)",
                ("Admin", "admin", password, "admin")
            )
            logger.info("Default admin created on startup")

        # Default fuel data (idempotent)
        cursor.execute("SELECT COUNT(*) FROM fuel")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO fuel (type, price, stock) VALUES ('Petrol', 100.0, 500.0)")
            cursor.execute("INSERT INTO fuel (type, price, stock) VALUES ('Diesel', 90.0, 600.0)")
            logger.info("Default fuel data initialized")
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

ensure_database_schema()


def validate_credentials(username, password):
    """Validate login credentials with secure password checking."""
    try:
        user = get_user_by_username(username)
        if not user:
            record_login_attempt(username, False, 'User not found')
            return False, None, None, None, 'Invalid username or password'

        if user['status'] != 'Active':
            record_login_attempt(username, False, 'Account inactive')
            return False, None, None, None, 'Account is inactive. Contact admin.'

        locked, locked_until_dt = is_account_locked(user)
        if locked:
            message = f'Account is locked until {locked_until_dt.strftime("%Y-%m-%d %H:%M:%S")}'
            record_login_attempt(username, False, message)
            return False, None, None, None, message

        if check_password_hash(user['password'], password):
            reset_failed_logins(username)
            set_user_field(username, 'last_login_at', datetime.now().isoformat())
            record_login_attempt(username, True, 'Login successful')
            return True, user['id'], user['role'], user['name'] or username, 'Login successful'

        lock_message = increment_failed_login(username)
        message = 'Invalid username or password.' + (lock_message or '')
        record_login_attempt(username, False, message)
        return False, None, None, None, message
    except Exception as e:
        logger.error(f"Credential validation error: {e}")
        record_login_attempt(username, False, f'Validation error: {e}')
        return False, None, None, None, 'Authentication failed due to server error'


@app.before_request
def enforce_session_timeout():
    if 'user_id' in session:
        last_active = session.get('last_active')
        if last_active:
            try:
                last_active_dt = datetime.fromisoformat(last_active)
                if datetime.now() - last_active_dt > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                    session.clear()
                    flash('Session timed out due to inactivity. Please log in again.', 'error')
                    return redirect('/login')
            except ValueError:
                pass
        session['last_active'] = datetime.now().isoformat()
        session.modified = True

# ==================== UTILITY FUNCTIONS ====================
def login_required(f):
    """Decorator to check if user is logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """Decorator to verify role-based access control."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect('/login')
            if session.get('role') not in allowed_roles:
                return render_template('error.html', message=f'Access denied: {" or ".join(allowed_roles)} only')
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    return role_required('Admin')(f)


def validate_customer_name(name):
    """Validate customer name"""
    if not name or not isinstance(name, str):
        return False, "Invalid customer name"
    if len(name.strip()) < 2:
        return False, "Customer name must be at least 2 characters"
    if len(name) > 100:
        return False, "Customer name too long"
    return True, ""

def validate_liters(liters):
    """Validate liters input"""
    try:
        liters = float(liters)
        if liters <= 0:
            return False, "Liters must be greater than 0"
        if liters > 10000:
            return False, "Invalid quantity"
        return True, liters
    except ValueError:
        return False, "Invalid liters input"

def validate_fuel_type(fuel_type):
    """Validate fuel type"""
    valid_fuels = ['Petrol', 'Diesel']
    if fuel_type not in valid_fuels:
        return False, "Invalid fuel type"
    return True, ""

def validate_stock(stock):
    """Validate stock input"""
    try:
        stock = float(stock)
        if stock < 0:
            return False, "Stock cannot be negative"
        if stock > 100000:
            return False, "Invalid stock quantity"
        return True, stock
    except ValueError:
        return False, "Invalid stock input"
def validate_mobile_number(phone):
    """
    Validate customer mobile number
    Accepts only 10-digit Indian mobile numbers
    
    Args:
        phone (str): Mobile number input
        
    Returns:
        tuple: (is_valid, error_message, formatted_number)
    """
    if not phone or not isinstance(phone, str):
        return False, "Mobile number is required", None
    
    # Remove spaces and dashes
    phone = phone.strip().replace(" ", "").replace("-", "")
    
    # Check if it contains only digits
    if not phone.isdigit():
        return False, "Mobile number must contain only digits", None
    
    # Check if it's exactly 10 digits
    if len(phone) != 10:
        return False, "Mobile number must be exactly 10 digits", None
    
    # Format for WhatsApp: +91XXXXXXXXXX
    formatted_phone = f"+91{phone}"
    return True, "", formatted_phone

def process_login(login_type=None):
    """Shared login handler for generic and role-specific sign-in."""
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        remember_me = form.remember_me.data

        is_valid, user_id, role, name, message = validate_credentials(username, password)
        if is_valid:
            if login_type == 'Admin' and role != 'Admin':
                flash('Admin login only. Please use the correct admin account.', 'error')
            elif login_type == 'Employee' and role == 'Admin':
                flash('Please use the admin login page for admin accounts.', 'error')
            else:
                session.permanent = bool(remember_me)
                session['user_id'] = user_id
                session['username'] = username
                session['role'] = role
                session['name'] = name
                session['last_active'] = datetime.now().isoformat()
                flash('Login successful!', 'success')
                logger.info(f"Login successful for {username} [{role}]")
                return redirect('/')
        else:
            flash(message, 'error')

    return render_template("login.html", form=form, login_type=login_type)


@app.route("/login", methods=["GET", "POST"])
def login():
    return process_login()


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    return process_login('Admin')


@app.route("/employee-login", methods=["GET", "POST"])
def employee_login():
    return process_login('Employee')

@app.route("/logout")
def logout():
    """User logout"""
    session.clear()
    return redirect('/login')


@app.route('/reset-admin', methods=['GET', 'POST'])
def reset_admin():
    """Reset admin credentials (convenience endpoint)"""
    message = ''
    if request.method == 'POST':
        new_user = request.form.get('username', 'admin').strip() or 'admin'
        new_password = request.form.get('password', 'admin123').strip() or 'admin123'

        try:
            conn = get_db()
            cursor = conn.cursor()
            hashed_password = generate_password_hash(new_password)

            # Upsert admin account
            cursor.execute('SELECT id FROM users WHERE username=%s', (new_user,))
            row = cursor.fetchone()
            if row:
                cursor.execute('UPDATE users SET password=%s, role=%s WHERE id=%s', (hashed_password, 'Admin', row['id']))
            else:
                cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)', (new_user, hashed_password, 'Admin'))

            conn.commit()
            conn.close()
            message = 'Admin credentials reset successfully. Login with new values.'
        except Exception as e:
            message = f'Error resetting admin: {e}'

    return render_template('reset_admin.html', message=message)


# ==================== DASHBOARD ====================
@app.route("/")
@login_required
@role_required('Admin', 'Manager', 'Employee')
def dashboard():
    """Main dashboard with analytics"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Total revenue
        cursor.execute("SELECT SUM(total) FROM sales")
        total_revenue = cursor.fetchone()[0] or 0

        # Total transactions
        cursor.execute("SELECT COUNT(*) FROM sales")
        total_transactions = cursor.fetchone()[0]

        # Fuel inventory
        cursor.execute("SELECT * FROM fuel ORDER BY type")
        fuels = cursor.fetchall()

        # Fuel-wise sales summary
        cursor.execute("""
            SELECT fuel_type, COUNT(*) as transactions, SUM(total) as revenue, SUM(liters) as total_liters
            FROM sales
            GROUP BY fuel_type
            ORDER BY revenue DESC
        """)
        fuel_summary = cursor.fetchall()

        # Recent sales - convert numerics to float for Jinja round()
        cursor.execute("""
            SELECT customer, fuel_type, liters, total, date
            FROM sales
            ORDER BY date DESC
            LIMIT 10
        """)
        recent_sales_raw = cursor.fetchall()
        recent_sales = []
        for sale in recent_sales_raw:
            recent_sales.append({
                'customer': sale['customer'],
                'fuel_type': sale['fuel_type'],
                'liters': float(sale['liters']) if sale['liters'] is not None else 0.0,
                'total': float(sale['total']) if sale['total'] is not None else 0.0,
                'date': sale['date']
            })

        # Fuel summary - convert numerics
        fuel_summary_converted = []
        for summary in fuel_summary:
            fuel_summary_converted.append({
                'fuel_type': summary['fuel_type'],
                'transactions': int(summary['transactions']),
                'revenue': float(summary['revenue']) if summary['revenue'] is not None else 0.0,
                'total_liters': float(summary['total_liters']) if summary['total_liters'] is not None else 0.0
            })
        fuel_summary = fuel_summary_converted

        conn.close()

        return render_template("dashboard.html",
                             total_revenue=round(total_revenue, 2),
                             total_transactions=total_transactions,
                             fuels=fuels,
                             fuel_summary=fuel_summary,
                             recent_sales=recent_sales,
                             username=session.get('username'))

    except (sqlite3.Error, ValueError, Exception) as e:
        logger.error(f"Dashboard error: {e}", exc_info=True)
        return render_template("error.html", message="Error loading dashboard")

# ==================== SALES & BILLING ====================
@app.route("/sales", methods=["GET", "POST"])
@login_required
def sales():
    """Sales and billing management"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        form = SalesForm()
        bill = None

        if form.validate_on_submit():
            customer = form.customer.data.strip()
            phone = form.phone.data
            fuel_type = form.fuel_type.data
            liters = float(form.liters.data)  # Ensure it's a float
            phone = str(form.phone.data)  # Ensure phone is string

            try:
                cursor.execute("SELECT price, stock FROM fuel WHERE type=%s", (fuel_type,))
                fuel_data = cursor.fetchone()

                if not fuel_data:
                    flash('Fuel type not found', 'error')
                else:
                    price = float(fuel_data[0])
                    stock = float(fuel_data[1])

                    if liters > stock:
                        flash(f'Not enough stock! Available: {stock} L', 'error')
                    else:
                        # Generate unique bill ID
                        user_id = session.get('user_id', 0)
                        bill_id = f"BILL-{int(datetime.now().timestamp())}-{user_id}"

                        # Atomic transaction
                        total = float(liters * price)  # Ensure total is float
                        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        employee_id = session.get('user_id')
                        formatted_phone = f"+91{phone}"

                        conn.execute("BEGIN TRANSACTION")
                        # Customer upsert logic (Phase 5.2)
                        cursor.execute("""
                            INSERT OR IGNORE INTO customers (name, phone)
                            VALUES (%s, %s)
                        """, (customer, formatted_phone))
                        
                        cursor.execute("""
                            UPDATE customers 
                            SET total_visits = total_visits + 1,
                                total_fuel = total_fuel + %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE phone = %s OR id = (SELECT id FROM customers WHERE name = %s LIMIT 1)
                        """, (liters, formatted_phone, customer))
                        
                        # Insert sale
                        cursor.execute("""
                            INSERT INTO sales (bill_id, customer, phone, payment_mode, fuel_type, liters, price, total, date, employee_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (bill_id, customer, formatted_phone, form.payment_mode.data, fuel_type, liters, price, total, date, employee_id))

                        cursor.execute("UPDATE fuel SET stock = stock - %s WHERE type=%s",
                                     (liters, fuel_type))
                        conn.commit()

                        bill = {
                            "bill_id": bill_id,
                            "customer": customer,
                            "phone": formatted_phone,
                            "fuel": fuel_type,
                            "liters": round(liters, 2),
                            "price": round(price, 2),
                            "total": round(total, 2),
                            "date": date
                        }
                        flash('Sale completed successfully!', 'success')

                        # Send WhatsApp bill after successful transaction
                        try:
                            employee_name = session.get('name', 'Staff')
                            logger.debug(f"DEBUG: Types - phone: {type(phone)}, liters: {type(liters)}, price: {type(price)}, total: {type(total)}")
                            success, whatsapp_msg = send_formatted_bill_to_whatsapp(
                                phone, customer, fuel_type, liters, price, total, date, bill_id, employee_name
                            )
                            if success:
                                logger.info(f"WhatsApp bill sent to {formatted_phone}")
                            else:
                                logger.warning(f"WhatsApp sending failed: {whatsapp_msg}")
                        except Exception as whatsapp_error:
                            logger.error(f"WhatsApp integration error: {str(whatsapp_error)}")

            except Exception as e:
                print("DB error:", e)
                flash("Database error", "error")

            except sqlite3.Error as db_error:
                conn.rollback()
                logger.error(f"Database transaction error: {db_error}")
                flash('Transaction failed. Please try again.', 'error')

        # Get all sales - convert numerics to float for Jinja round()
        cursor.execute("""
            SELECT id, bill_id, customer, phone, fuel_type, liters, price, total, date
            FROM sales
            ORDER BY id DESC
        """)
        sales_list_raw = cursor.fetchall()
        sales_list = []
        for sale in sales_list_raw:
            sales_list.append({
                'id': sale['id'],
                'bill_id': sale['bill_id'],
                'customer': sale['customer'],
                'phone': sale['phone'],
                'fuel_type': sale['fuel_type'],
                'liters': float(sale['liters']) if sale['liters'] is not None else 0.0,
                'price': float(sale['price']) if sale['price'] is not None else 0.0,
                'total': float(sale['total']) if sale['total'] is not None else 0.0,
                'date': sale['date']
            })

        conn.close()

        return render_template("sales.html",
                             sales=sales_list,
                             bill=bill,
                             form=form,
                             username=session.get('username'))

    except Exception as e:
        logger.error(f"Sales error: {e}")
        return render_template("error.html", message="Error processing billing")

# ==================== INVENTORY MANAGEMENT ====================
@app.route("/inventory", methods=["GET", "POST"])
@login_required
@admin_required
def inventory():
    """Inventory management"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        message = ""

        if request.method == "POST":
            fuel = request.form.get("fuel", "").strip()
            stock_input = request.form.get("stock", "")

            is_valid_fuel, fuel_error = validate_fuel_type(fuel)
            is_valid_stock, stock_or_error = validate_stock(stock_input)

            if not is_valid_fuel:
                message = fuel_error
            elif not is_valid_stock:
                message = stock_or_error
            else:
                stock = stock_or_error
                try:
                    cursor.execute("UPDATE fuel SET stock = stock + %s WHERE type=%s", (stock, fuel))
                    conn.commit()
                    message = f"success"
                except sqlite3.Error as e:
                    logger.error(f"Inventory update error: {e}", exc_info=True)
                    message = "Error updating stock"

        cursor.execute("SELECT id, type, price, stock FROM fuel ORDER BY type")
        fuels = cursor.fetchall()

        conn.close()

        return render_template("inventory.html",
                             fuels=fuels,
                             message=message,
                             username=session.get('username'))

    except (sqlite3.Error, ValueError, Exception) as e:
        logger.error(f"Inventory error: {e}", exc_info=True)
        return render_template("error.html", message="Error loading inventory")

# ==================== EMPLOYEES MANAGEMENT ====================
@app.route("/employees", methods=["GET", "POST"])
@login_required
@admin_required
def employees():
    """Employees management (stored in users table)"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        add_form = EmployeeForm()
        update_form = EmployeeUpdateForm()

        if request.method == "POST":
            action = request.form.get('action', 'add')

            if action == 'add':
                if add_form.validate_on_submit():
                    name = add_form.name.data.strip()
                    username = add_form.username.data
                    email = add_form.email.data.strip()
                    phone = add_form.phone.data.strip()
                    role = add_form.role.data
                    status = add_form.status.data
                    password = add_form.password.data

                    try:
                        hashed_password = generate_password_hash(password)
                        cursor.execute(
                            "INSERT INTO users (name, username, email, phone, password, role, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (name, username, email, phone, hashed_password, role, status)
                        )
                        conn.commit()
                        flash('Employee account added successfully!', 'success')
                        add_form = EmployeeForm()  # Reset form
                    except sqlite3.IntegrityError:
                        flash('Username already exists', 'error')
                    except sqlite3.Error as e:
                        logger.error(f"Employee insert error: {e}")
                        flash('Error adding employee', 'error')
                else:
                    # Show validation errors
                    for field, errors in add_form.errors.items():
                        for error in errors:
                            flash(f'{field}: {error}', 'error')

            elif action == 'update':
                if update_form.validate_on_submit():
                    user_id = request.form.get('user_id')
                    name = update_form.name.data.strip()
                    email = update_form.email.data.strip()
                    phone = update_form.phone.data.strip()
                    role = update_form.role.data
                    status = update_form.status.data
                    if user_id and user_id.isdigit():
                        try:
                            cursor.execute(
                                "UPDATE users SET name=?, email=?, phone=?, role=?, status=? WHERE id=? AND role!='Admin'",
                                (name, email, phone, role, status, int(user_id))
                            )
                            conn.commit()
                            flash('Employee updated successfully!', 'success')
                        except sqlite3.Error as e:
                            logger.error(f"Employee update error: {e}")
                            flash('Error updating employee', 'error')
                    else:
                        flash('Invalid employee ID', 'error')

            elif action == 'delete':
                user_id = request.form.get('user_id')
                if user_id and user_id.isdigit():
                    try:
                        cursor.execute("DELETE FROM users WHERE id=%s AND role=%s", (int(user_id), 'Employee'))
                        conn.commit()
                        flash('Employee deleted successfully!', 'success')
                    except sqlite3.Error as e:
                        logger.error(f"Employee delete error: {e}")
                        flash('Error deleting employee', 'error')
                else:
                    flash('Invalid employee ID', 'error')

        cursor.execute("SELECT id, name, username, email, phone, role, status, created_at FROM users WHERE role!='Admin' ORDER BY id DESC")
        employees_list = cursor.fetchall()

        conn.close()

        return render_template('employees.html',
                               employees=employees_list,
                               add_form=add_form,
                               update_form=update_form,
                               username=session.get('username'))

    except Exception as e:
        logger.error(f"Employees error: {e}")
        return render_template('error.html', message='Error loading employees')

@app.route("/reports")
@login_required
def reports():
    """Billing history with filters and pagination (Phase 4.3)"""
    page = int(request.args.get('page', 1))
    per_page = 20
    offset = (page - 1) * per_page
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Build query with filters
    query = """
        SELECT * FROM sales 
        WHERE 1=1
    """
    params = []
    
    date_filter = request.args.get('date_filter', '30days')
    if date_filter == 'today':
        query += " AND date(date) = date('now')"
    elif date_filter == '7days':
        query += " AND date >= date('now', '-7 days')"
    elif date_filter == '30days':
        query += " AND date >= date('now', '-30 days')"
    
    payment_mode = request.args.get('payment_mode')
    if payment_mode:
        query += " AND payment_mode = ?"
        params.append(payment_mode)
    
    fuel_type = request.args.get('fuel_type')
    if fuel_type:
        query += " AND fuel_type = ?"
        params.append(fuel_type)
    
    query += " ORDER BY date DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    
    cursor.execute(query, params)
    bills = cursor.fetchall()
    
    # Pagination info
    # Create a separate count query (DO NOT reuse main query)
    count_query = """
        SELECT COUNT(*) FROM sales
        WHERE 1=1
    """

    count_params = []

    # Apply same filters
    if date_filter == 'today':
        count_query += " AND date(date) = date('now')"
    elif date_filter == '7days':
        count_query += " AND date >= date('now', '-7 days')"
    elif date_filter == '30days':
        count_query += " AND date >= date('now', '-30 days')"

    if payment_mode:
        count_query += " AND payment_mode = ?"
        count_params.append(payment_mode)

    if fuel_type:
        count_query += " AND fuel_type = ?"
        count_params.append(fuel_type)

    cursor.execute(count_query, count_params)
    total = cursor.fetchone()[0]
    total_pages = (total + per_page - 1) // per_page

    conn.close()

    # Query params for pagination
    query_params = '&'.join([k+'='+v for k, v in request.args.items() if k != 'page'])

    return render_template('reports.html',
                         bills=bills,
                         current_page=page,
                         total_pages=total_pages,
                         prev_page=page-1 if page > 1 else None,
                         next_page=page+1 if page < total_pages else None,
                         query_params=query_params,
                         date_filter=date_filter,
                         payment_mode=payment_mode,
                         fuel_type=fuel_type,
                         username=session.get('username'))

@app.route("/bill/pdf/<bill_id>")
@login_required
def bill_pdf(bill_id):
    """Download PDF bill (Phase 4.3)"""
    try:
        from services.pdf_service import generate_bill_pdf_from_id
        
        pdf_buffer = generate_bill_pdf_from_id(bill_id)
        
        if pdf_buffer:
            response = app.response_class(
                response=pdf_buffer.getvalue(),
                status=200,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'attachment; filename=bill_{bill_id}.pdf'}
            )
            pdf_buffer.close()
            return response
        else:
            flash('Bill not found', 'error')
            return redirect('/reports')
            
    except Exception as e:
        logger.error(f"PDF generation error for {bill_id}: {e}")
        flash('Error generating PDF', 'error')
        return redirect('/reports')

# ==================== API ENDPOINTS ====================
@app.route("/api/fuel-status")
@login_required
def fuel_status():
    """API endpoint for fuel status"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT type, stock FROM fuel")
        fuels = cursor.fetchall()
        conn.close()

        fuel_data = [{"type": f['type'], "stock": float(f['stock'])} for f in fuels]
        return jsonify({"status": "success", "data": fuel_data})

    except Exception as e:
        logger.error(f"Fuel status API error: {e}")
        return jsonify({"status": "error", "message": "Error fetching fuel status"}), 500

@app.route("/api/print-bill", methods=["POST"])
@login_required
def print_bill():
    """API endpoint for bill printing"""
    try:
        data = request.get_json()
        return jsonify({
            "status": "success",
            "message": "Bill formatted for printing",
            "bill": data
        })
    except Exception as e:
        logger.error(f"Print bill API error: {e}")
        return jsonify({"status": "error", "message": "Error printing bill"}), 500

@app.route("/api/dashboard/charts")
@login_required
def dashboard_charts():
    """API for dashboard charts data (PHASE 2.1)"""
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 1. Daily revenue (last 7 days line chart)
        # IMPORTANT: Use DATE(date) + DATE('now', ...) for correct filtering in SQLite.
        cursor.execute("""
            SELECT
                DATE(date) as date,
                COALESCE(SUM(total), 0) as revenue
            FROM sales
            WHERE DATE(date) >= DATE('now', '-7 days')
            GROUP BY DATE(date)
            ORDER BY date
        """)
        daily_data = cursor.fetchall()
        daily_labels = [row['date'] for row in daily_data]
        daily_revenue = [float(row['revenue'] or 0) for row in daily_data]

        # 2. Fuel sales pie chart (fuel distribution)
        # Ensure fuel_type is not null and return valid liters totals.
        cursor.execute("""
            SELECT
                fuel_type,
                COALESCE(SUM(liters), 0) as liters_sold,
                COUNT(*) as transactions
            FROM sales
            WHERE fuel_type IS NOT NULL
            GROUP BY fuel_type
            ORDER BY fuel_type
        """)
        fuel_pie = cursor.fetchall()
        fuel_labels = [row['fuel_type'] for row in fuel_pie]
        fuel_data = [float(row['liters_sold'] or 0) for row in fuel_pie]

        # 3. Monthly sales bar (last 6 months)
        cursor.execute("""
            SELECT
                strftime('%Y-%m', date) as month,
                COALESCE(SUM(total), 0) as revenue
            FROM sales
            WHERE DATE(date) >= DATE('now', '-6 months')
            GROUP BY month
            ORDER BY month
        """)
        monthly_data = cursor.fetchall()
        monthly_labels = [row['month'] for row in monthly_data]
        monthly_revenue = [float(row['revenue'] or 0) for row in monthly_data]

        # Low stock check (kept for existing dashboard UX)
        cursor.execute("SELECT type, stock FROM fuel WHERE stock < 100")
        low_stock = [{"type": row['type'], "stock": float(row['stock'])} for row in cursor.fetchall()]

        conn.close()

        return jsonify({
            "status": "success",
            "daily": {"labels": daily_labels, "data": daily_revenue},
            "fuel_pie": {"labels": fuel_labels, "data": fuel_data},
            "monthly": {"labels": monthly_labels, "data": monthly_revenue},
            "low_stock": low_stock
        })

    except Exception as e:
        logger.error(f"Dashboard charts API error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Error fetching chart data"}), 500

# ==================== CUSTOMER MANAGEMENT APIs ====================
@app.route("/api/customers/<int:customer_id>")
@login_required
def get_customer(customer_id):
    """Get single customer for edit modal"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers WHERE id = %s", (customer_id,))
    customer = cursor.fetchone()
    conn.close()
    
    if customer:
        return jsonify({"status": "success", "customer": dict(customer)})
    return jsonify({"status": "error", "message": "Customer not found"}), 404

@app.route("/customers")
@login_required
def customers():
    """Customer management page (Phase 5.1)"""
    conn = get_db()
    cursor = conn.cursor()
    
    # All customers with stats
    cursor.execute("""
        SELECT 
            c.*, 
            COUNT(s.id) as total_visits,
            COALESCE(SUM(s.liters), 0) as total_fuel,
            MIN(s.date) as first_visit,
            MAX(s.date) as last_visit
        FROM customers c
        LEFT JOIN sales s ON c.phone = s.phone OR c.name = s.customer
        GROUP BY c.id
        ORDER BY total_fuel DESC, total_visits DESC
    """)
    customers = cursor.fetchall()
    
    # Top 10 customers
    cursor.execute("""
        SELECT 
            c.*, 
            COUNT(s.id) as total_visits,
            COALESCE(SUM(s.liters), 0) as total_fuel,
            MAX(s.date) as last_visit
        FROM customers c
        LEFT JOIN sales s ON c.phone = s.phone OR c.name = s.customer
        GROUP BY c.id
        ORDER BY total_fuel DESC
        LIMIT 10
    """)
    top_customers = cursor.fetchall()
    
    conn.close()
    
    form = CustomerForm()  # Define form for adding
    
    return render_template('customers.html',
                         customers=customers,
                         top_customers=top_customers,
                         form=form,
                         username=session.get('username'))

@app.route("/customers", methods=['POST'])
@login_required
@admin_required
def add_customer():
    """Add new customer (Phase 5.1)"""
    form = CustomerForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        phone = form.phone.data.strip() if form.phone.data else None
        
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO customers (name, phone) VALUES (?, ?)",
                (name, phone)
            )
            conn.commit()
            flash('Customer added successfully!', 'success')
        except sqlite3.IntegrityError:
            flash('Customer with this phone already exists', 'error')
        finally:
            conn.close()
    
    return redirect('/customers')

@app.route("/customers", methods=['POST'])
@login_required
@admin_required
def update_customer():
    """Update customer"""
    customer_id = request.form.get('customer_id')
    name = request.form.get('name').strip()
    phone = request.form.get('phone').strip() or None
    
    if customer_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE customers SET name = ?, phone = ? WHERE id = ?",
            (name, phone, customer_id)
        )
        conn.commit()
        conn.close()
        flash('Customer updated!', 'success')
    
    return redirect('/customers')

# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template("error.html", message="Internal server error"), 500

if __name__ == "__main__":
    # Local development only.
    # Render/production runs this app via Gunicorn using `app:app`.
    app.run(debug=False, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))

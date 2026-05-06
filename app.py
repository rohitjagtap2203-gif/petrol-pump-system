"""Petrol Pump Management System - Flask + MongoDB (MongoDB-only backend)

Routes are kept compatible with existing templates/static.

Collections:
- users
- fuel
- sales
- customers
- login_attempts

Auth:
- session-based
- role-based access

Important:
- MongoDB-only data access
- no SQL/SQLite/psycopg2
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import CSRFProtect, FlaskForm
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import BooleanField, FloatField, PasswordField, SelectField, StringField
from wtforms.validators import DataRequired, Length, NumberRange, Regexp

from config import (
    DEFAULT_ADMIN,
    DEFAULT_FUEL,
    LOCKOUT_DURATION_MINUTES,
    LOG_LEVEL,
    MAX_LOGIN_ATTEMPTS,
    PERMANENT_SESSION_LIFETIME_DAYS,
    SECRET_KEY,
    SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_SECURE,
    SESSION_TIMEOUT_MINUTES,
)
from mongo.db import get_db
from mongo.helpers import (
    create_default_fuel,
    ensure_indexes,
    generate_bill_id,
    increment_failed_login,
    record_login_attempt,
    reset_failed_logins,
    user_auth_lock_state,
    stringify_object_ids,
)

# ReportLab PDF generation
from services.pdf_service import generate_bill_pdf_from_id


logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


app = Flask(__name__)
app.secret_key = SECRET_KEY or os.getenv("FLASK_SECRET_KEY", "")

app.config.update(
    WTF_CSRF_ENABLED=True,
    WTF_CSRF_TIME_LIMIT=None,
    PERMANENT_SESSION_LIFETIME=timedelta(days=PERMANENT_SESSION_LIFETIME_DAYS),
    SESSION_COOKIE_HTTPONLY=SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
    SESSION_REFRESH_EACH_REQUEST=True,
)

csrf = CSRFProtect(app)


# ==================== Helpers: Auth decorators & session timeout ====================

def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapper


def role_required(*allowed_roles: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if session.get("role") not in allowed_roles:
                return render_template(
                    "error.html",
                    message=f"Access denied: {' or '.join(allowed_roles)} only",
                )
            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def admin_required(view_func):
    return role_required("Admin")(view_func)


@app.before_request
def enforce_session_timeout():
    if "user_id" not in session:
        return

    last_active = session.get("last_active")
    if last_active:
        try:
            last_active_dt = datetime.fromisoformat(last_active)
            if datetime.now(timezone.utc).replace(tzinfo=None) - last_active_dt > timedelta(
                minutes=SESSION_TIMEOUT_MINUTES
            ):
                session.clear()
                flash("Session timed out due to inactivity. Please log in again.", "error")
                return redirect(url_for("login"))
        except Exception:
            # If parsing fails, don't block request.
            pass

    session["last_active"] = datetime.now().isoformat()
    session.modified = True


# ==================== Forms ====================


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=1, max=50)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=1, max=100)])
    remember_me = BooleanField("Remember Me")


class CustomerForm(FlaskForm):
    name = StringField("Customer Name", validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField(
        "Phone",
        validators=[Regexp(r"^\d{10}$", message="Phone must be exactly 10 digits")],
    )


class SalesForm(FlaskForm):
    customer = StringField("Customer Name", validators=[DataRequired(), Length(min=1, max=100)])
    phone = StringField(
        "Phone Number",
        validators=[DataRequired(), Regexp(r"^\d{10}$", message="Phone must be exactly 10 digits")],
    )
    payment_mode = SelectField(
        "Payment Mode",
        choices=[("Cash", "Cash"), ("UPI", "UPI"), ("Card", "Card")],
        validators=[DataRequired()],
        default="Cash",
    )
    fuel_type = SelectField(
        "Fuel Type",
        choices=[("Petrol", "Petrol"), ("Diesel", "Diesel")],
        validators=[DataRequired()],
    )
    liters = FloatField(
        "Liters",
        validators=[DataRequired(), NumberRange(min=0.01, max=1000, message="Liters out of range")],
    )


class EmployeeForm(FlaskForm):
    name = StringField("Employee Name", validators=[DataRequired(), Length(min=2, max=100)])
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=50)])
    email = StringField("Email", validators=[DataRequired(), Length(min=5, max=100)])
    phone = StringField("Phone", validators=[DataRequired(), Regexp(r"^\d{10}$", message="Phone must be exactly 10 digits")])
    role = SelectField(
        "Role",
        choices=[("Admin", "Admin"), ("Manager", "Manager"), ("Employee", "Employee")],
        validators=[DataRequired()],
    )
    status = SelectField(
        "Status",
        choices=[("Active", "Active"), ("Inactive", "Inactive")],
        validators=[DataRequired()],
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6, max=100)])


class EmployeeUpdateForm(FlaskForm):
    name = StringField("Employee Name", validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField("Email", validators=[DataRequired(), Length(min=5, max=100)])
    phone = StringField("Phone", validators=[DataRequired(), Regexp(r"^\d{10}$", message="Phone must be exactly 10 digits")])
    role = SelectField(
        "Role",
        choices=[("Admin", "Admin"), ("Manager", "Manager"), ("Employee", "Employee")],
        validators=[DataRequired()],
    )
    status = SelectField(
        "Status",
        choices=[("Active", "Active"), ("Inactive", "Inactive")],
        validators=[DataRequired()],
    )


# ==================== Bootstrap (indexes, default admin, default fuel) ====================


def _bootstrap():
    try:
        db = get_db()
        ensure_indexes(db)

        # Default admin creation
        db.users.update_one(
            {"username": DEFAULT_ADMIN["username"]},
            {
                "$setOnInsert": {
                    "name": DEFAULT_ADMIN["name"],
                    "username": DEFAULT_ADMIN["username"],
                    "password": generate_password_hash(DEFAULT_ADMIN["password"]),
                    "role": DEFAULT_ADMIN["role"],
                    "status": "Active",
                    "email": None,
                    "phone": None,
                    "failed_login_attempts": 0,
                    "locked_until": None,
                    "created_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )

        # Default fuel initialization
        create_default_fuel(db, DEFAULT_FUEL)

    except Exception:
        logger.exception("Bootstrap failed")


_bootstrap()


# ==================== Auth: credential validation ====================


def _normalize_phone(phone_10_digits: str) -> str:
    # templates/whatsapp expect +91XXXXXXXXXX
    p = (phone_10_digits or "").strip()
    return f"+91{p}" if len(p) == 10 else p


def validate_credentials(username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    db = get_db()

    user = db.users.find_one({"username": username})
    if not user:
        record_login_attempt(
            db,
            username=username,
            success=False,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or ""),
            user_agent=request.headers.get("User-Agent", ""),
            message="User not found",
        )
        return False, None, "Invalid username or password"

    if user.get("status") != "Active":
        record_login_attempt(
            db,
            username=username,
            success=False,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or ""),
            user_agent=request.headers.get("User-Agent", ""),
            message="Account inactive",
        )
        return False, None, "Account is inactive. Contact admin."

    locked, locked_until = user_auth_lock_state(db, user, LOCKOUT_DURATION_MINUTES)
    if locked:
        msg = f"Account is locked until {locked_until.strftime('%Y-%m-%d %H:%M:%S')}" if locked_until else "Account is locked"
        record_login_attempt(
            db,
            username=username,
            success=False,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or ""),
            user_agent=request.headers.get("User-Agent", ""),
            message=msg,
        )
        return False, None, msg

    if check_password_hash(user["password"], password):
        reset_failed_logins(db, username)
        db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": datetime.utcnow()}})
        record_login_attempt(
            db,
            username=username,
            success=True,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or ""),
            user_agent=request.headers.get("User-Agent", ""),
            message="Login successful",
        )
        return True, user, "Login successful"

    inc = increment_failed_login(db, username, MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION_MINUTES)
    record_login_attempt(
        db,
        username=username,
        success=False,
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or ""),
        user_agent=request.headers.get("User-Agent", ""),
        message=inc.get("message", "Invalid username or password"),
    )

    return False, None, (inc.get("message") or "Invalid username or password")


# ==================== Routes: /, /login, /logout ====================


@app.route("/", methods=["GET"])
@login_required
@role_required("Admin", "Manager", "Employee")
def dashboard():
    db = get_db()

    # Total revenue + transactions
    total_revenue = db.sales.aggregate([
        {"$group": {"_id": None, "total": {"$sum": {"$toDouble": {"$ifNull": ["$total", 0]}}}, "count": {"$sum": 1}}}
    ]).next().get("total", 0) if db.sales.count_documents({}) > 0 else 0

    # Fuel inventory
    fuels = list(db.fuel.find({}, {"_id": 0, "type": 1, "price": 1, "stock": 1}).sort("type", 1))

    # Fuel-wise summary
    fuel_summary = list(
        db.sales.aggregate(
            [
                {"$group": {"_id": "$fuel_type", "transactions": {"$sum": 1}, "revenue": {"$sum": {"$toDouble": "$total"}}, "total_liters": {"$sum": {"$toDouble": "$liters"}}}},
                {"$sort": {"revenue": -1}},
            ]
        )
    )
    fuel_summary = [
        {
            "fuel_type": r.get("_id"),
            "transactions": int(r.get("transactions", 0)),
            "revenue": float(r.get("revenue", 0) or 0),
            "total_liters": float(r.get("total_liters", 0) or 0),
        }
        for r in fuel_summary
    ]

    # Recent sales
    recent_cursor = db.sales.find({}, {"_id": 0}).sort("date", -1).limit(10)
    recent_sales = [
        {
            "customer": d.get("customer"),
            "fuel_type": d.get("fuel_type"),
            "liters": float(d.get("liters", 0) or 0),
            "total": float(d.get("total", 0) or 0),
            "date": d.get("date"),
        }
        for d in recent_cursor
    ]

    total_transactions = db.sales.count_documents({})

    return render_template(
        "dashboard.html",
        total_revenue=round(float(total_revenue), 2),
        total_transactions=total_transactions,
        fuels=fuels,
        fuel_summary=fuel_summary,
        recent_sales=recent_sales,
        username=session.get("username"),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()

    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        remember_me = bool(form.remember_me.data)

        ok, user, message = validate_credentials(username, password)
        if ok and user:
            session.permanent = remember_me
            session["user_id"] = str(user["_id"])
            session["username"] = username
            session["role"] = user.get("role") or "Employee"
            session["name"] = user.get("name") or username
            session["last_active"] = datetime.now().isoformat()
            flash(message, "success")
            logger.info("Login successful for %s", username)
            return redirect(url_for("dashboard"))

        flash(message, "error")

    # template expects login_type sometimes; keep minimal
    return render_template("login.html", form=form)


@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==================== Routes: /sales ====================


@app.route("/sales", methods=["GET", "POST"])
@login_required
def sales():
    db = get_db()
    form = SalesForm()
    bill: Optional[Dict[str, Any]] = None

    if form.validate_on_submit():
        customer = form.customer.data.strip()
        phone = form.phone.data.strip()
        fuel_type = form.fuel_type.data
        liters = float(form.liters.data)
        payment_mode = form.payment_mode.data

        phone_e164 = _normalize_phone(phone)

        fuel_doc = db.fuel.find_one({"type": fuel_type})
        if not fuel_doc:
            flash("Fuel type not found", "error")
            return redirect(url_for("sales"))

        price = float(fuel_doc.get("price", 0) or 0)
        stock = float(fuel_doc.get("stock", 0) or 0)

        if liters > stock:
            flash(f"Not enough stock! Available: {stock} L", "error")
            return redirect(url_for("sales"))

        # Bill/total
        user_id = session.get("user_id", "")
        bill_id = generate_bill_id(user_id)
        total = liters * price
        date_dt = datetime.utcnow()

        # Transactional consistency using update with conditions
        # 1) Upsert customer
        db.customers.update_one(
            {"phone": phone_e164},
            {"$setOnInsert": {"name": customer, "phone": phone_e164, "total_visits": 0, "total_fuel": 0, "created_at": datetime.utcnow()},
             "$set": {"updated_at": datetime.utcnow()}},
            upsert=True,
        )

        # 2) Update customer stats
        db.customers.update_one(
            {"phone": phone_e164},
            {"$inc": {"total_visits": 1, "total_fuel": liters}, "$set": {"updated_at": datetime.utcnow()}},
        )

        # 3) Decrement fuel stock only if enough stock
        updated = db.fuel.update_one(
            {"type": fuel_type, "stock": {"$gte": liters}},
            {"$inc": {"stock": -liters}, "$set": {"updated_at": datetime.utcnow()}},
        )

        if updated.matched_count == 0:
            flash("Stock changed. Try again.", "error")
            return redirect(url_for("sales"))

        # 4) Insert sale record
        sale_doc = {
            "bill_id": bill_id,
            "customer": customer,
            "phone": phone_e164,
            "payment_mode": payment_mode,
            "fuel_type": fuel_type,
            "liters": liters,
            "price": price,
            "total": total,
            "date": date_dt,
            "employee_id": session.get("user_id"),
            "created_at": datetime.utcnow(),
        }
        db.sales.insert_one(sale_doc)

        bill = {
            "bill_id": bill_id,
            "customer": customer,
            "phone": phone_e164,
            "fuel": fuel_type,
            "fuel_type": fuel_type,
            "liters": round(liters, 2),
            "price": round(price, 2),
            "total": round(total, 2),
            "date": date_dt,
            "payment_mode": payment_mode,
        }
        flash("Sale completed successfully!", "success")

    # Load all sales
    sales_cursor = db.sales.find({}, {"bill_id": 1, "customer": 1, "phone": 1, "fuel_type": 1, "liters": 1, "price": 1, "total": 1, "date": 1}).sort("date", -1)
    sales_list = [
        {
            "id": str(d.get("_id")),
            "bill_id": d.get("bill_id"),
            "customer": d.get("customer"),
            "phone": d.get("phone"),
            "fuel_type": d.get("fuel_type"),
            "liters": float(d.get("liters", 0) or 0),
            "price": float(d.get("price", 0) or 0),
            "total": float(d.get("total", 0) or 0),
            "date": d.get("date"),
        }
        for d in sales_cursor
    ]

    return render_template(
        "sales.html",
        sales=sales_list,
        bill=bill,
        form=form,
        username=session.get("username"),
    )


# ==================== Routes: /inventory ====================


@app.route("/inventory", methods=["GET", "POST"])
@login_required
@admin_required
def inventory():
    db = get_db()
    message = ""

    if request.method == "POST":
        fuel_type = (request.form.get("fuel") or "").strip()
        stock_input = request.form.get("stock")

        try:
            stock_to_add = float(stock_input)
        except Exception:
            flash("Invalid stock input", "error")
            return redirect(url_for("inventory"))

        if stock_to_add < 0:
            flash("Stock cannot be negative", "error")
            return redirect(url_for("inventory"))

        res = db.fuel.update_one(
            {"type": fuel_type},
            {"$inc": {"stock": stock_to_add}, "$set": {"updated_at": datetime.utcnow()}},
        )

        if res.matched_count == 0:
            message = "Fuel type not found"
            flash(message, "error")
        else:
            message = "success"
            flash("Inventory updated", "success")

    fuels = list(db.fuel.find({}, {"type": 1, "price": 1, "stock": 1}).sort("type", 1))
    # match template expectation: fuels iterable with keys id,type,price,stock
    fuels_out = [{"id": str(f.get("_id")), "type": f.get("type"), "price": f.get("price"), "stock": f.get("stock")} for f in fuels]

    return render_template("inventory.html", fuels=fuels_out, message=message, username=session.get("username"))


# ==================== Routes: /employees ====================


@app.route("/employees", methods=["GET", "POST"])
@login_required
@admin_required
def employees():
    db = get_db()

    add_form = EmployeeForm()
    update_form = EmployeeUpdateForm()

    if request.method == "POST":
        action = request.form.get("action", "add")

        if action == "add" and add_form.validate_on_submit():
            username = add_form.username.data.strip()
            password = add_form.password.data
            doc = {
                "name": add_form.name.data.strip(),
                "username": username,
                "email": add_form.email.data.strip(),
                "phone": add_form.phone.data.strip(),
                "role": add_form.role.data,
                "status": add_form.status.data,
                "password": generate_password_hash(password),
                "failed_login_attempts": 0,
                "locked_until": None,
                "created_at": datetime.utcnow(),
            }
            try:
                db.users.insert_one(doc)
                flash("Employee account added successfully!", "success")
            except Exception:
                flash("Username already exists or invalid data", "error")

        elif action == "update" and update_form.validate_on_submit():
            user_id = request.form.get("user_id")
            if user_id:
                update_doc = {
                    "name": update_form.name.data.strip(),
                    "email": update_form.email.data.strip(),
                    "phone": update_form.phone.data.strip(),
                    "role": update_form.role.data,
                    "status": update_form.status.data,
                }

                db.users.update_one(
                    {"_id": ObjectId(user_id), "role": {"$ne": "Admin"}},
                    {"$set": update_doc},
                )
                flash("Employee updated successfully!", "success")

        elif action == "delete":
            user_id = request.form.get("user_id")
            if user_id:
                db.users.delete_one({"_id": ObjectId(user_id), "role": {"$ne": "Admin"}})
                flash("Employee deleted successfully!", "success")

    employees_cursor = db.users.find(
        {"role": {"$ne": "Admin"}},
        {"password": 0, "failed_login_attempts": 0, "locked_until": 0},
    ).sort("created_at", -1)

    employees_list = [
        {
            "id": str(d.get("_id")),
            "name": d.get("name"),
            "username": d.get("username"),
            "email": d.get("email"),
            "phone": d.get("phone"),
            "role": d.get("role"),
            "status": d.get("status"),
            "created_at": d.get("created_at"),
        }
        for d in employees_cursor
    ]

    return render_template(
        "employees.html",
        employees=employees_list,
        add_form=add_form,
        update_form=update_form,
        username=session.get("username"),
    )


# ==================== Routes: /customers ====================


@app.route("/customers", methods=["GET", "POST"])
@login_required
@admin_required
def customers():
    db = get_db()

    # Add/update handled by POST from templates; keep simple API
    if request.method == "POST":
        form = CustomerForm()
        action = request.form.get("action", "add")

        if action == "add" and form.validate_on_submit():
            name = form.name.data.strip()
            phone = form.phone.data.strip()
            phone_e164 = _normalize_phone(phone)

            db.customers.update_one(
                {"phone": phone_e164},
                {"$setOnInsert": {"name": name, "phone": phone_e164, "total_visits": 0, "total_fuel": 0, "created_at": datetime.utcnow()},
                 "$set": {"name": name, "updated_at": datetime.utcnow()}},
                upsert=True,
            )
            flash("Customer added successfully!", "success")

        elif action == "update":
            customer_id = request.form.get("customer_id")
            name = (request.form.get("name") or "").strip()
            phone = request.form.get("phone")
            phone_e164 = _normalize_phone(phone.strip()) if phone else None

            if customer_id and phone_e164:
                db.customers.update_one({"_id": ObjectId(customer_id)}, {"$set": {"name": name, "phone": phone_e164, "updated_at": datetime.utcnow()}})
                flash("Customer updated!", "success")

        return redirect(url_for("customers"))

    # GET: load stats
    pipeline = [
        {
            "$lookup": {
                "from": "sales",
                "let": {"phone": "$phone"},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$phone", "$$phone"]}}},
                    {"$project": {"liters": 1, "date": 1}},
                ],
                "as": "sales_docs",
            }
        },
        {
            "$addFields": {
                "total_visits": {"$size": "$sales_docs"},
                "total_fuel": {"$sum": {"$map": {"input": "$sales_docs", "as": "s", "in": {"$toDouble": "$$s.liters"}}}},
                "first_visit": {"$min": {"$map": {"input": "$sales_docs", "as": "s", "in": "$$s.date"}}},
                "last_visit": {"$max": {"$map": {"input": "$sales_docs", "as": "s", "in": "$$s.date"}}},
            }
        },
        {"$project": {"sales_docs": 0}},
        {"$sort": {"total_fuel": -1, "total_visits": -1}},
    ]

    all_customers = list(db.customers.aggregate(pipeline))

    top_customers = list(
        db.customers.aggregate(pipeline + [{"$limit": 10}])
    )

    def normalize_customer(d: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(d.get("_id")),
            "name": d.get("name"),
            "phone": d.get("phone"),
            "total_visits": int(d.get("total_visits", 0) or 0),
            "total_fuel": float(d.get("total_fuel", 0) or 0),
            "first_visit": d.get("first_visit"),
            "last_visit": d.get("last_visit"),
        }

    customers_out = [normalize_customer(d) for d in all_customers]
    top_customers_out = [normalize_customer(d) for d in top_customers]

    return render_template(
        "customers.html",
        customers=customers_out,
        top_customers=top_customers_out,
        form=CustomerForm(),
        username=session.get("username"),
    )


# ==================== Routes: /reports (sales history) ====================


@app.route("/reports", methods=["GET"])
@login_required
def reports():
    db = get_db()

    page = int(request.args.get("page", 1))
    per_page = 20
    offset = (page - 1) * per_page

    date_filter = request.args.get("date_filter", "30days")
    payment_mode = request.args.get("payment_mode")
    fuel_type = request.args.get("fuel_type")

    now = datetime.utcnow()

    match_stage: Dict[str, Any] = {}
    if date_filter == "today":
        start = datetime(now.year, now.month, now.day)
        match_stage["date"] = {"$gte": start, "$lt": start + timedelta(days=1)}
    elif date_filter == "7days":
        match_stage["date"] = {"$gte": now - timedelta(days=7)}
    else:  # 30days
        match_stage["date"] = {"$gte": now - timedelta(days=30)}

    if payment_mode:
        match_stage["payment_mode"] = payment_mode
    if fuel_type:
        match_stage["fuel_type"] = fuel_type

    base_pipeline = [
        {"$match": match_stage},
        {"$sort": {"date": -1}},
    ]

    bills_pipeline = base_pipeline + [{"$skip": offset}, {"$limit": per_page}]
    bills = list(db.sales.aggregate(bills_pipeline))

    # count
    total = list(db.sales.aggregate(base_pipeline + [{"$count": "total"}]))
    total_count = total[0]["total"] if total else 0
    total_pages = (total_count + per_page - 1) // per_page if per_page else 1

    def normalize_bill(d: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(d.get("_id")),
            "bill_id": d.get("bill_id"),
            "customer": d.get("customer"),
            "phone": d.get("phone"),
            "fuel_type": d.get("fuel_type"),
            "liters": float(d.get("liters", 0) or 0),
            "price": float(d.get("price", 0) or 0),
            "total": float(d.get("total", 0) or 0),
            "date": d.get("date"),
        }

    bills_out = [normalize_bill(d) for d in bills]

    query_params = "&".join([f"{k}={v}" for k, v in request.args.items() if k != "page"])

    return render_template(
        "reports.html",
        bills=bills_out,
        current_page=page,
        total_pages=total_pages,
        prev_page=page - 1 if page > 1 else None,
        next_page=page + 1 if page < total_pages else None,
        query_params=query_params,
        date_filter=date_filter,
        payment_mode=payment_mode,
        fuel_type=fuel_type,
        username=session.get("username"),
    )


# ==================== Routes: /bill/pdf/<bill_id> ====================


@app.route("/bill/pdf/<bill_id>", methods=["GET"])
@login_required
def bill_pdf(bill_id: str):
    try:
        pdf_buffer = generate_bill_pdf_from_id(bill_id)
        if not pdf_buffer:
            flash("Bill not found", "error")
            return redirect(url_for("reports"))

        return app.response_class(
            response=pdf_buffer.getvalue(),
            status=200,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=bill_{bill_id}.pdf"},
        )
    except Exception as e:
        logger.exception("PDF generation error for %s", bill_id)
        flash("Error generating PDF", "error")
        return redirect(url_for("reports"))


# ==================== API: /api/dashboard/charts ====================


@app.route("/api/dashboard/charts", methods=["GET"])
@login_required
def dashboard_charts():
    db = get_db()
    try:
        now = datetime.utcnow()

        # last 7 days labels (daily sums)
        start_7 = now - timedelta(days=7)
        daily = list(
            db.sales.aggregate(
                [
                    {"$match": {"date": {"$gte": start_7}}},
                    {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}}, "revenue": {"$sum": {"$toDouble": "$total"}}}},
                    {"$sort": {"_id": 1}},
                ]
            )
        )

        daily_labels = [r.get("_id") for r in daily]
        daily_revenue = [float(r.get("revenue", 0) or 0) for r in daily]

        # fuel distribution pie chart (liters)
        fuel_pie = list(
            db.sales.aggregate(
                [
                    {"$match": {"fuel_type": {"$ne": None}}},
                    {"$group": {"_id": "$fuel_type", "liters_sold": {"$sum": {"$toDouble": "$liters"}}}},
                    {"$sort": {"_id": 1}},
                ]
            )
        )

        fuel_labels = [r.get("_id") for r in fuel_pie]
        fuel_data = [float(r.get("liters_sold", 0) or 0) for r in fuel_pie]

        # monthly revenue last 6 months
        start_6m = now - timedelta(days=30 * 6)
        monthly = list(
            db.sales.aggregate(
                [
                    {"$match": {"date": {"$gte": start_6m}}},
                    {"$group": {"_id": {"$dateToString": {"format": "%Y-%m", "date": "$date"}}, "revenue": {"$sum": {"$toDouble": "$total"}}}},
                    {"$sort": {"_id": 1}},
                ]
            )
        )

        monthly_labels = [r.get("_id") for r in monthly]
        monthly_revenue = [float(r.get("revenue", 0) or 0) for r in monthly]

        # low stock alerts
        low_stock = [
            {"type": d.get("type"), "stock": float(d.get("stock", 0) or 0)}
            for d in db.fuel.find({"stock": {"$lt": 100}}, {"type": 1, "stock": 1})
        ]

        return jsonify(
            {
                "status": "success",
                "daily": {"labels": daily_labels, "data": daily_revenue},
                "fuel_pie": {"labels": fuel_labels, "data": fuel_data},
                "monthly": {"labels": monthly_labels, "data": monthly_revenue},
                "low_stock": low_stock,
            }
        )

    except Exception:
        logger.exception("Dashboard charts API error")
        return jsonify({"status": "error", "message": "Error fetching chart data"}), 500


# ==================== API: /api/fuel-status ====================


@app.route("/api/fuel-status", methods=["GET"])
@login_required
def fuel_status():
    db = get_db()
    try:
        fuels = list(db.fuel.find({}, {"_id": 0, "type": 1, "stock": 1}))
        fuel_data = [{"type": f.get("type"), "stock": float(f.get("stock", 0) or 0)} for f in fuels]
        return jsonify({"status": "success", "data": fuel_data})
    except Exception:
        logger.exception("Fuel status API error")
        return jsonify({"status": "error", "message": "Error fetching fuel status"}), 500


# ==================== Run ====================


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)


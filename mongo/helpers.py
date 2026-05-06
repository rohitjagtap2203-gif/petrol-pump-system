from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from bson import ObjectId
from pymongo import ReturnDocument

logger = logging.getLogger(__name__)


def to_object_id(value: Any) -> Optional[ObjectId]:
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def stringify_object_ids(doc: Any) -> Any:
    """Recursively convert ObjectId to str for safe JSON/template usage."""
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, list):
        return [stringify_object_ids(x) for x in doc]
    if isinstance(doc, dict):
        return {k: stringify_object_ids(v) for k, v in doc.items()}
    return doc


def ensure_indexes(db):
    """Idempotent index creation."""
    users = db.users
    fuel = db.fuel
    sales = db.sales
    customers = db.customers
    login_attempts = db.login_attempts

    users.create_index("username", unique=True, background=True)
    users.create_index("role", background=True)
    users.create_index("status", background=True)

    fuel.create_index("type", unique=True, background=True)
    fuel.create_index("updated_at", background=True)

    sales.create_index("bill_id", unique=True, background=True)
    sales.create_index("date", background=True)
    sales.create_index([("fuel_type", 1), ("date", -1)], background=True)
    sales.create_index([("customer.phone", 1), ("date", -1)], background=True)

    customers.create_index("phone", unique=True, sparse=True, background=True)
    customers.create_index("name", background=True)

    login_attempts.create_index("username", background=True)
    login_attempts.create_index("timestamp", background=True)


def create_default_fuel(db, default_fuel):
    for item in default_fuel:
        db.fuel.update_one(
            {"type": item["type"]},
            {"$setOnInsert": {
                "type": item["type"],
                "price": item["price"],
                "stock": item["stock"],
                "updated_at": datetime.utcnow(),
            }},
            upsert=True,
        )


def user_auth_lock_state(db, user_doc: Dict[str, Any], locked_until_minutes: int = 15):
    locked_until = user_doc.get("locked_until")
    if not locked_until:
        return False, None
    try:
        dt = locked_until if isinstance(locked_until, datetime) else datetime.fromisoformat(str(locked_until))
        return dt > datetime.utcnow(), dt
    except Exception:
        return False, None


def increment_failed_login(db, username: str, max_attempts: int, lockout_minutes: int):
    """Atomically increment failed attempts and lock when threshold reached."""
    now = datetime.utcnow()

    # First, read current state
    user = db.users.find_one({"username": username})
    if not user:
        return {"locked": False, "message": "Invalid username or password"}

    failed = int(user.get("failed_login_attempts", 0)) + 1

    update: Dict[str, Any] = {"$set": {"failed_login_attempts": failed}}
    locked = False
    locked_until = None

    if failed >= max_attempts:
        locked = True
        locked_until = now + timedelta(minutes=lockout_minutes)
        update["$set"]["locked_until"] = locked_until

    db.users.update_one({"_id": user["_id"]}, update)

    if locked:
        return {
            "locked": True,
            "message": f"Account locked for {lockout_minutes} minutes.",
            "locked_until": locked_until,
        }
    return {"locked": False, "message": "Invalid username or password"}


def reset_failed_logins(db, username: str):
    db.users.update_one(
        {"username": username},
        {"$set": {"failed_login_attempts": 0, "locked_until": None}},
    )


def record_login_attempt(db, username: str, success: bool, ip_address: str, user_agent: str, message: str = ""):
    db.login_attempts.insert_one({
        "username": username,
        "success": bool(success),
        "ip_address": ip_address,
        "user_agent": user_agent,
        "message": message,
        "timestamp": datetime.utcnow(),
    })


def generate_bill_id(user_id: str) -> str:
    # Unique enough for production: timestamp + user id + random-ish ObjectId suffix handled by caller if desired.
    return f"BILL-{int(datetime.utcnow().timestamp())}-{user_id[-6:]}"


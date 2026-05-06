import os
from dotenv import load_dotenv

load_dotenv()

# =========================================================
# Flask Core
# =========================================================

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "change-me-to-a-secure-random-string"
)

DEBUG = os.getenv(
    "DEBUG",
    "False"
).lower() == "true"

# =========================================================
# MongoDB
# =========================================================

MONGO_URI = os.getenv("MONGO_URI")

# =========================================================
# Default Admin
# =========================================================

DEFAULT_ADMIN = {
    "name": os.getenv(
        "DEFAULT_ADMIN_NAME",
        "Admin"
    ),

    "username": os.getenv(
        "DEFAULT_ADMIN_USERNAME",
        "admin"
    ),

    "password": os.getenv(
        "DEFAULT_ADMIN_PASSWORD",
        "admin123"
    ),

    "role": "Admin"
}

# =========================================================
# Default Fuel Initialization
# =========================================================

DEFAULT_FUEL = [
    {
        "type": "Petrol",
        "price": float(
            os.getenv(
                "DEFAULT_PETROL_PRICE",
                100
            )
        ),
        "stock": float(
            os.getenv(
                "DEFAULT_PETROL_STOCK",
                500
            )
        )
    },

    {
        "type": "Diesel",
        "price": float(
            os.getenv(
                "DEFAULT_DIESEL_PRICE",
                90
            )
        ),
        "stock": float(
            os.getenv(
                "DEFAULT_DIESEL_STOCK",
                600
            )
        )
    }
]

# =========================================================
# Security / Login Protection
# =========================================================

MAX_LOGIN_ATTEMPTS = int(
    os.getenv(
        "MAX_LOGIN_ATTEMPTS",
        5
    )
)

LOCKOUT_DURATION_MINUTES = int(
    os.getenv(
        "LOCKOUT_DURATION_MINUTES",
        15
    )
)

# =========================================================
# Session Configuration
# =========================================================

SESSION_TIMEOUT_MINUTES = int(
    os.getenv(
        "SESSION_TIMEOUT_MINUTES",
        30
    )
)

PERMANENT_SESSION_LIFETIME_DAYS = int(
    os.getenv(
        "PERMANENT_SESSION_LIFETIME_DAYS",
        7
    )
)

SESSION_COOKIE_SECURE = os.getenv(
    "SESSION_COOKIE_SECURE",
    "false"
).lower() == "true"

SESSION_COOKIE_HTTPONLY = os.getenv(
    "SESSION_COOKIE_HTTPONLY",
    "true"
).lower() == "true"

SESSION_COOKIE_SAMESITE = os.getenv(
    "SESSION_COOKIE_SAMESITE",
    "Lax"
)

# =========================================================
# Twilio / WhatsApp
# =========================================================

ENABLE_WHATSAPP_NOTIFICATIONS = os.getenv(
    "ENABLE_WHATSAPP_NOTIFICATIONS",
    "false"
).lower() == "true"

TWILIO_ACCOUNT_SID = os.getenv(
    "TWILIO_ACCOUNT_SID",
    ""
)

TWILIO_AUTH_TOKEN = os.getenv(
    "TWILIO_AUTH_TOKEN",
    ""
)

TWILIO_WHATSAPP_NUMBER = os.getenv(
    "TWILIO_WHATSAPP_NUMBER",
    ""
)

# =========================================================
# Logging
# =========================================================

LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO"
)
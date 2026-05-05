"""
Configuration module for environment variables
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
ENABLE_WHATSAPP_NOTIFICATIONS = os.getenv("ENABLE_WHATSAPP_NOTIFICATIONS", "False").lower() == "true"

# App Configuration
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "petrol_pump_secret_2026")

# WhatsApp Configuration
def is_whatsapp_configured():
    """Check if WhatsApp credentials are properly configured"""
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and ENABLE_WHATSAPP_NOTIFICATIONS)

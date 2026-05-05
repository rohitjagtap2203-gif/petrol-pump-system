"""
WhatsApp Integration Module
Handles sending bill receipts via WhatsApp using Twilio API
"""
import logging
from twilio.rest import Client
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER, is_whatsapp_configured

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_whatsapp_phone(phone):
    """
    Validate and format phone number for WhatsApp
    Converts 10-digit Indian number to WhatsApp format: whatsapp:+91XXXXXXXXXX
    
    Args:
        phone (str): 10-digit phone number
        
    Returns:
        tuple: (is_valid, formatted_number, error_message)
    """
    if not phone or not isinstance(phone, str):
        return False, None, "Invalid phone number"
    
    # Remove spaces and dashes
    phone = phone.strip().replace(" ", "").replace("-", "")
    
    # Check if it contains only digits
    if not phone.isdigit():
        return False, None, "Phone number must contain only digits"
    
    # Check if it's exactly 10 digits
    if len(phone) != 10:
        return False, None, "Phone number must be exactly 10 digits"
    
    # Format to WhatsApp format: whatsapp:+91XXXXXXXXXX
    formatted_phone = f"whatsapp:+91{phone}"
    return True, formatted_phone, ""

def send_bill_to_whatsapp(phone_number, bill_data):
    """
    Send bill receipt to customer via WhatsApp
    
    Args:
        phone_number (str): 10-digit Indian phone number
        bill_data (dict): Bill information containing:
            - customer: Customer name
            - fuel_type: Type of fuel
            - liters: Quantity in liters
            - price: Price per liter
            - total: Total amount
            - date: Transaction date and time
    
    Returns:
        tuple: (success, message)
    """
    # Check if WhatsApp is configured
    if not is_whatsapp_configured():
        logger.warning("WhatsApp not configured. Set TWILIO credentials in .env file")
        return False, "WhatsApp service not configured"
    
    try:
        # Validate and format phone number
        is_valid, formatted_phone, error_msg = validate_whatsapp_phone(phone_number)
        
        if not is_valid:
            logger.error(f"Invalid phone number: {error_msg}")
            return False, error_msg
        
        # Format the bill message
        message_body = format_bill_message(bill_data)
        
        # Initialize Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Send WhatsApp message
        message = client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=message_body,
            to=formatted_phone
        )
        
        logger.info(f"WhatsApp bill sent successfully. Message SID: {message.sid}")
        return True, f"Bill sent to {formatted_phone}"
        
    except Exception as e:
        error_msg = f"WhatsApp sending failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg

def format_bill_message(bill_data):
    """
    Format bill data into a readable WhatsApp message
    
    Args:
        bill_data (dict): Bill information
        
    Returns:
        str: Formatted message
    """
    message = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━
⛽ PETROL PUMP RECEIPT
━━━━━━━━━━━━━━━━━━━━━━━━━━

🧾 Bill ID: {bill_data.get('bill_id', 'N/A')}
👤 Customer: {bill_data.get('customer', 'N/A')}
👨‍💼 Employee: {bill_data.get('employee_name', 'N/A')}
📅 Date & Time: {bill_data.get('date', 'N/A')}

📊 BILL DETAILS:
━━━━━━━━━━━━━━━━━━━━━━━━━━
⛽ Fuel Type: {bill_data.get('fuel_type', 'N/A')}
📏 Quantity: {bill_data.get('liters', 0):.2f} Liters
💰 Price/Liter: ₹{bill_data.get('price', 0):.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━
💳 TOTAL AMOUNT: ₹{bill_data.get('total', 0):.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━

Thank you for your purchase! 🙏
Visit us soon again!

⛽ Petrol Pump Management System
"""
    return message.strip()

def send_formatted_bill_to_whatsapp(phone_number, customer, fuel_type, liters, price, total, date, bill_id, employee_name):
    """
    Wrapper function to send bill with individual parameters
    
    Args:
        phone_number (str): 10-digit phone number
        customer (str): Customer name
        fuel_type (str): Type of fuel
        liters (float): Quantity in liters
        price (float): Price per liter
        total (float): Total amount
        date (str): Transaction date and time
        bill_id (str): Unique bill identifier
        employee_name (str): Name of the employee who processed the transaction
    
    Returns:
        tuple: (success, message)
    """
    bill_data = {
        'customer': customer,
        'fuel_type': fuel_type,
        'liters': liters,
        'price': price,
        'total': total,
        'date': date,
        'bill_id': bill_id,
        'employee_name': employee_name
    }
    
    return send_bill_to_whatsapp(phone_number, bill_data)

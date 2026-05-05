"""
PDF Bill Generation Service - Phase 4.1
Petrol Pump Management System
"""
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from io import BytesIO
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def generate_bill_pdf(bill_data):
    """
    Generate PDF bill receipt from bill data
    
    Args:
        bill_data (dict): Bill information from sales table
        
    Returns:
        BytesIO: PDF file buffer for download
    """
    buffer = BytesIO()
    
    # Document setup
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18
    )
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='CustomTitle',
        fontSize=24,
        spaceAfter=30,
        alignment=1,  # Center
        textColor=colors.darkblue
    ))
    
    styles.add(ParagraphStyle(
        name='CustomNormal',
        fontSize=12,
        spaceAfter=12,
        leftIndent=36
    ))
    
    story = []
    
    # Title
    story.append(Paragraph("⛽ PETROL PUMP MANAGEMENT", styles['CustomTitle']))
    story.append(Spacer(1, 12))
    story.append(Paragraph("RECEIPT / BILL", styles['Heading2']))
    story.append(Spacer(1, 24))
    
    # Bill data table
    bill_table_data = [
        ['Bill ID:', bill_data.get('bill_id', 'N/A')],
        ['Date:', bill_data.get('date', 'N/A')],
        ['Customer:', bill_data.get('customer', 'N/A')],
        ['Phone:', bill_data.get('phone', 'N/A')],
        ['Payment:', bill_data.get('payment_mode', 'Cash')],
        ['', ''],  # Spacer
        ['Fuel Type:', bill_data.get('fuel_type', 'N/A')],
        ['Quantity:', f"{bill_data.get('liters', 0):.2f} L"],
        ['Rate per L:', f"₹{bill_data.get('price', 0):.2f}"],
        ['', ''],  # Spacer
        ['TOTAL AMOUNT:', f"₹{bill_data.get('total', 0):.2f}"]
    ]
    
    bill_table = Table(bill_table_data, colWidths=[2.5*inch, 3*inch])
    bill_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (0, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 10), (1, 10), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 10), (-1, 10), [colors.lightgrey]),
    ]))
    
    story.append(bill_table)
    story.append(Spacer(1, 36))
    
    # Footer
    story.append(Paragraph(
        """
        <b>Thank you for your business!</b><br/><br/>
        ⛽ Petrol Pump Management System<br/>
        Professional Edition 2026<br/>
        Generated on {}
        """.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        styles['CustomNormal']
    ))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    return buffer

def get_db():
    """Get DB connection for PDF service (with context manager support)"""
    import sqlite3
    try:
        conn = sqlite3.connect("petrol_pump.db")
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"PDF DB connection error: {e}", exc_info=True)
        return None

def generate_bill_pdf_from_id(bill_id):
    """
    Generate PDF from bill_id (standalone - direct DB)
    
    Args:
        bill_id (str): Unique bill identifier
        
    Returns:
        BytesIO: PDF buffer or None if not found
    """
    conn = get_db()
    if not conn:
        logger.error("Database connection failed for PDF generation")
        return None
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT bill_id, customer, phone, payment_mode, fuel_type, liters, price, total, date 
        FROM sales WHERE bill_id = ?
    """, (bill_id,))
    
    bill = cursor.fetchone()
    conn.close()
    
    if not bill:
        logger.error(f"Bill {bill_id} not found")
        return None
    
    # Convert Row to dict
    bill_data = dict(bill)
    bill_data['payment_mode'] = bill_data.get('payment_mode', 'Cash')
    
    return generate_bill_pdf(bill_data)

"""PDF Bill Generation Service (MongoDB-based)."""

from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    Paragraph,
)

from mongo.db import get_db

logger = logging.getLogger(__name__)


def generate_bill_pdf(bill_data: Dict[str, Any]) -> BytesIO:
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CustomTitle",
            fontSize=24,
            spaceAfter=30,
            alignment=1,
            textColor=colors.darkblue,
        )
    )

    styles.add(
        ParagraphStyle(
            name="CustomNormal",
            fontSize=12,
            spaceAfter=12,
            leftIndent=36,
        )
    )

    story = []

    story.append(Paragraph("⛽ PETROL PUMP MANAGEMENT", styles["CustomTitle"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("RECEIPT / BILL", styles["Heading2"]))
    story.append(Spacer(1, 24))

    bill_table_data = [
        ["Bill ID:", bill_data.get("bill_id", "N/A")],
        ["Date:", bill_data.get("date", "N/A")],
        ["Customer:", bill_data.get("customer", "N/A")],
        ["Phone:", bill_data.get("phone", "N/A")],
        ["Payment:", bill_data.get("payment_mode", "Cash")],
        ["", ""],
        ["Fuel Type:", bill_data.get("fuel_type", "N/A")],
        ["Quantity:", f"{float(bill_data.get('liters', 0) or 0):.2f} L"],
        ["Rate per L:", f"₹{float(bill_data.get('price', 0) or 0):.2f}"],
        ["", ""],
        ["TOTAL AMOUNT:", f"₹{float(bill_data.get('total', 0) or 0):.2f}"],
    ]

    bill_table = Table(bill_table_data, colWidths=[2.5 * inch, 3 * inch])
    bill_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.darkblue),
                ("TEXTCOLOR", (0, 0), (0, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 10), (1, 10), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 14),
                ("FONTSIZE", (0, 1), (-1, -1), 12),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 10), (-1, 10), [colors.lightgrey]),
            ]
        )
    )

    story.append(bill_table)
    story.append(Spacer(1, 36))

    story.append(
        Paragraph(
            """
            <b>Thank you for your business!</b><br/><br/>
            ⛽ Petrol Pump Management System<br/>
            Professional Edition 2026<br/>
            Generated on {}
            """.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            styles["CustomNormal"],
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer


def get_bill_from_mongo(bill_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    if not db:
        return None

    doc = db.sales.find_one({"bill_id": bill_id})
    if not doc:
        return None

    # Normalize fields for the PDF layer
    return {
        "bill_id": doc.get("bill_id"),
        "date": doc.get("date"),
        "customer": doc.get("customer"),
        "phone": doc.get("phone"),
        "payment_mode": doc.get("payment_mode", "Cash"),
        "fuel_type": doc.get("fuel_type"),
        "liters": float(doc.get("liters", 0) or 0),
        "price": float(doc.get("price", 0) or 0),
        "total": float(doc.get("total", 0) or 0),
    }


def generate_bill_pdf_from_id(bill_id: str):
    bill_data = get_bill_from_mongo(bill_id)
    if not bill_data:
        return None
    return generate_bill_pdf(bill_data)


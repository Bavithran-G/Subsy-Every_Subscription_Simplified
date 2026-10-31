from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import Invoice

RED = colors.HexColor("#C62828")
GREY = colors.HexColor("#6B7280")


def _inr(v) -> str:
    return f"INR {v:,.2f}"


def invoice_pdf(inv: Invoice, company: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"Invoice {inv.number}")
    ss = getSampleStyleSheet()
    h = ss["Heading1"]
    h.textColor = RED
    small = ss["Normal"].clone("small", fontSize=9, textColor=GREY)
    story = [
        Paragraph(f"{company}", h),
        Paragraph("Powered by Subsy — Every Subscription, Simplified.", small),
        Spacer(1, 8),
        Table([
            [Paragraph(f"<b>INVOICE {inv.number}</b>", ss["Heading3"]), f"Status: {str(inv.state).upper()}"],
            [f"Invoice date: {inv.invoice_date}", f"Due date: {inv.due_date}"],
            [f"Billing period: {inv.period_start} to {inv.period_end}" if inv.period_start else "",
             f"Subscription: {inv.subscription.number if inv.subscription else '-'}"],
        ], colWidths=[100 * mm, 74 * mm]),
        Spacer(1, 8),
        Paragraph(f"<b>Bill to</b><br/>{inv.customer.name}<br/>{inv.customer.company or ''}<br/>"
                  f"{inv.customer.email}<br/>{(inv.customer.address or '').replace(chr(10), '<br/>')}"
                  + (f"<br/>GSTIN: {inv.customer.gstin}" if inv.customer.gstin else ""), ss["Normal"]),
        Spacer(1, 10),
    ]
    rows = [["Description", "Qty", "Unit price", "Discount", "Taxable", "Tax", "Total"]]
    for l in inv.lines:
        tax = f"{l.tax_name} {_inr(l.tax_amount)}" if l.tax_name else "-"
        rows.append([Paragraph(l.description, ss["BodyText"]), str(l.quantity), _inr(l.unit_price),
                     _inr(l.discount_amount), _inr(l.taxable_amount), Paragraph(tax, small), _inr(l.total)])
    t = Table(rows, colWidths=[52 * mm, 10 * mm, 24 * mm, 20 * mm, 24 * mm, 24 * mm, 22 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FDECEC")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#8E1B1B")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [t, Spacer(1, 10)]
    totals = [["Subtotal", _inr(inv.untaxed_amount)], ["Discount", f"- {_inr(inv.discount_amount)}"],
              ["Tax", _inr(inv.tax_amount)], ["Total", _inr(inv.total)], ["Paid", _inr(inv.amount_paid)],
              ["Amount due", _inr(inv.amount_due)]]
    tt = Table(totals, colWidths=[40 * mm, 36 * mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
                            ("FONTNAME", (0, 5), (-1, 5), "Helvetica-Bold"),
                            ("TEXTCOLOR", (0, 5), (-1, 5), RED),
                            ("LINEABOVE", (0, 3), (-1, 3), 0.5, GREY)]))
    story.append(tt)
    if inv.discount_applications:
        story += [Spacer(1, 8), Paragraph("Discounts applied: " + ", ".join(
            f"{a.discount.name} ({_inr(a.amount)})" for a in inv.discount_applications), small)]
    doc.build(story)
    return buf.getvalue()

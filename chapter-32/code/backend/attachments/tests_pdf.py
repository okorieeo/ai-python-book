import io

from reportlab.pdfgen import canvas


def text_pdf_bytes(pages=3) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for n in range(1, pages + 1):
        c.drawString(72, 720, f"Page {n}: the quarterly report says revenue grew in every region this year.")
        c.showPage()
    c.save()
    return buf.getvalue()

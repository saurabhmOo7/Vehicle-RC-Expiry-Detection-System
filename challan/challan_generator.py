import os
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
except Exception:
    A4 = None
    canvas = None


class ChallanGenerator:
    def __init__(self, db, pdf_dir: str):
        self.db = db
        self.pdf_dir = pdf_dir
        os.makedirs(self.pdf_dir, exist_ok=True)

    def generate_challan(self, vehicle: dict, violation_type: str, fine_amount: int, location: str):
        pdf_path = self._create_pdf(vehicle, violation_type, fine_amount, location)
        return self.db.create_challan(
            vehicle_number=vehicle["vehicle_number"],
            owner_name=vehicle["owner_name"],
            violation_type=violation_type,
            fine_amount=fine_amount,
            pdf_path=pdf_path,
        )

    def _create_pdf(self, vehicle: dict, violation_type: str, fine_amount: int, location: str):
        if canvas is None or A4 is None:
            return None

        timestamp = datetime.now()
        file_path = os.path.join(
            self.pdf_dir,
            f"challan_{vehicle['vehicle_number']}_{timestamp.strftime('%Y%m%d_%H%M%S')}.pdf",
        )
        pdf = canvas.Canvas(file_path, pagesize=A4)
        _, height = A4

        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(50, height - 60, "Traffic Violation Challan")

        pdf.setFont("Helvetica", 12)
        lines = [
            f"Vehicle Number: {vehicle['vehicle_number']}",
            f"Owner Name: {vehicle['owner_name']}",
            f"Vehicle Model: {vehicle['vehicle_model']}",
            f"Violation Type: {violation_type}",
            f"Fine Amount: INR {fine_amount}",
            f"Date and Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Location: {location}",
        ]

        y = height - 110
        for line in lines:
            pdf.drawString(50, y, line)
            y -= 28

        pdf.save()
        return file_path

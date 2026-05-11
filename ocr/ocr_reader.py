import logging
import re

import pytesseract

from utils.image_processing import preprocess_plate_image


logger = logging.getLogger("ocr_reader")


class OCRReader:
    def __init__(self):
        self.pattern = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z]{2}[0-9]{4}$")

    def read_plate(self, image_path: str) -> str | None:
        try:
            processed = preprocess_plate_image(image_path)
            config = "--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            text = pytesseract.image_to_string(processed, config=config)
            cleaned = self._clean_output(text)
            if cleaned:
                logger.info("OCR extracted plate %s", cleaned)
            return cleaned
        except Exception as exc:
            logger.exception("OCR failed for %s: %s", image_path, exc)
            return None

    def _clean_output(self, text: str) -> str | None:
        normalized = re.sub(r"\s+", "", text or "").upper()
        normalized = re.sub(r"[^A-Z0-9]", "", normalized)
        return normalized if self.pattern.fullmatch(normalized) else None

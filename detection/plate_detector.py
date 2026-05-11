import logging
import os
import time
from typing import List

import cv2

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None


logger = logging.getLogger("plate_detector")


class PlateDetector:
    def __init__(self, model_path: str, output_dir: str):
        self.model_path = model_path
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.model = None

        if YOLO and os.path.exists(model_path) and os.path.getsize(model_path) > 1024:
            try:
                self.model = YOLO(model_path)
                logger.info("Loaded YOLOv8 model from %s", model_path)
            except Exception as exc:
                logger.exception("Failed to load YOLO model: %s", exc)
        else:
            logger.warning(
                "YOLOv8 plate model not available at %s. Using contour-based demo detector.",
                model_path,
            )

    def detect(self, frame) -> List[dict]:
        if frame is None or getattr(frame, "size", 0) == 0:
            return []
        if self.model is not None:
            return self._detect_with_yolo(frame)
        return self._detect_with_contours(frame)

    def _detect_with_yolo(self, frame) -> List[dict]:
        detections = []
        try:
            results = self.model.predict(frame, imgsz=640, conf=0.35, verbose=False)
            for result in results:
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    crop_path = self._save_crop(frame, (x1, y1, x2, y2))
                    detections.append(
                        {
                            "bbox": (x1, y1, x2, y2),
                            "crop_path": crop_path,
                            "label": "YOLO Plate",
                        }
                    )
        except Exception as exc:
            logger.exception("YOLO detection failed, switching to fallback: %s", exc)
            return self._detect_with_contours(frame)
        return detections

    def _detect_with_contours(self, frame) -> List[dict]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blur, 100, 200)

        contours, _ = cv2.findContours(edged, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:20]
        detections = []

        for contour in contours:
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            if len(approx) != 4:
                continue

            x, y, w, h = cv2.boundingRect(approx)
            aspect_ratio = w / float(h)
            area = w * h
            if 2.0 <= aspect_ratio <= 6.5 and area > 2500:
                x1, y1, x2, y2 = x, y, x + w, y + h
                crop_path = self._save_crop(frame, (x1, y1, x2, y2))
                detections.append(
                    {
                        "bbox": (x1, y1, x2, y2),
                        "crop_path": crop_path,
                        "label": "Demo Plate",
                    }
                )
                break

        return detections

    def _save_crop(self, frame, bbox) -> str:
        x1, y1, x2, y2 = bbox
        crop = frame[max(0, y1):max(y1, y2), max(0, x1):max(x1, x2)]
        filename = f"plate_{int(time.time() * 1000)}.jpg"
        path = os.path.join(self.output_dir, filename)
        if crop.size > 0:
            cv2.imwrite(path, crop)
        return path

import atexit
import logging
import os
import threading
import time
from datetime import datetime

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, send_from_directory, request

from challan.challan_generator import ChallanGenerator
from database.db import DatabaseManager
from detection.plate_detector import PlateDetector
from ocr.ocr_reader import OCRReader


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
CAPTURED_PLATES_DIR = os.path.join(BASE_DIR, "captured_plates")
CHALLANS_DIR = os.path.join(BASE_DIR, "challans")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(CAPTURED_PLATES_DIR, exist_ok=True)
os.makedirs(CHALLANS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "system.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("app")

app = Flask(__name__)


class MonitoringSystem:
    def __init__(self):
        self.db = DatabaseManager(os.path.join(BASE_DIR, "vehicles.db"))
        self.db.initialize_database()
        self.detector = PlateDetector(
            model_path=os.path.join(BASE_DIR, "models", "yolov8_plate.pt"),
            output_dir=os.path.join(BASE_DIR, "sample_data", "crops"),
        )
        self.ocr = OCRReader()
        self.challan_generator = ChallanGenerator(self.db, pdf_dir=CHALLANS_DIR)

        self.lock = threading.Lock()
        self.running = True
        self.current_frame = None
        self.capture = None
        self.camera_index = None
        self.last_processed_plate = None
        self.last_processed_at = 0.0
        self.failed_reads = 0
        self.last_detection = self._default_detection_state()

        if os.environ.get("RENDER"):
            logger.info("Running on Render - browser camera mode enabled")
            self.capture = None
        else:
            self.capture = self._open_camera()
            self.thread = threading.Thread(target=self._processing_loop, daemon=True)
            self.thread.start()

    def _default_detection_state(self):
        return {
            "vehicle_number": "Waiting for detection",
            "owner_name": "-",
            "vehicle_model": "-",
            "rc_status": "UNKNOWN",
            "rc_expiry_date": "-",
            "fine_amount": 0,
            "challan_status": "No challan generated",
            "last_seen": "-",
            "location": "Main Gate Junction",
            "violation": False,
            "challan": None,
            "message": "Camera stream starting",
            "snapshot_url": None,
            "snapshot_name": None,
            "download_url": None,
            "download_name": None,
            "alert_title": "",
            "alert_text": "",
        }

    def _open_camera(self):
        backend_candidates = [None]
        if os.name == "nt":
            backend_candidates = [cv2.CAP_DSHOW, cv2.CAP_MSMF, None]

        for index in (0, 1):
            for backend in backend_candidates:
                capture = self._create_capture(index, backend)
                if capture is None:
                    continue

                if self._validate_capture(capture):
                    self.camera_index = index
                    backend_name = self._backend_name(backend)
                    logger.info(
                        "Webcam opened successfully on camera index %s using %s",
                        index,
                        backend_name,
                    )
                    self.last_detection["message"] = (
                        f"Camera stream active on camera index {index} using {backend_name}"
                    )
                    return capture

                logger.warning(
                    "Webcam opened but could not read frames on camera index %s using %s",
                    index,
                    self._backend_name(backend),
                )
                capture.release()

        self.last_detection.update(
            {
                "rc_status": "CAMERA ERROR",
                "message": "Unable to open webcam. Tried camera indices 0 and 1.",
            }
        )
        logger.error("Unable to open webcam. Tried camera indices 0 and 1.")
        return None

    def _create_capture(self, index, backend):
        try:
            capture = cv2.VideoCapture(index) if backend is None else cv2.VideoCapture(index, backend)
            if not capture.isOpened():
                logger.warning(
                    "Failed to open webcam on camera index %s using %s",
                    index,
                    self._backend_name(backend),
                )
                capture.release()
                return None

            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
            return capture
        except Exception as exc:
            logger.exception(
                "Error opening webcam on camera index %s using %s: %s",
                index,
                self._backend_name(backend),
                exc,
            )
            return None

    def _validate_capture(self, capture):
        for _ in range(5):
            ok, frame = capture.read()
            if ok and frame is not None and getattr(frame, "size", 0) > 0:
                return True
            time.sleep(0.1)
        return False

    def _backend_name(self, backend):
        if backend == cv2.CAP_DSHOW:
            return "CAP_DSHOW"
        if backend == cv2.CAP_MSMF:
            return "CAP_MSMF"
        return "default backend"

    def _processing_loop(self):
        logger.info("Camera processing loop started")
        while self.running:
            if self.capture is None or not self.capture.isOpened():
                with self.lock:
                    self.current_frame = self._build_error_frame(
                        "Webcam not available. Check camera permissions or close other apps using it."
                    )
                time.sleep(0.5)
                continue

            ok, frame = self.capture.read()
            if not ok:
                self.failed_reads += 1
                logger.warning("Unable to read frame from webcam")
                with self.lock:
                    self.current_frame = self._build_error_frame("Unable to read webcam frame.")
                if self.failed_reads >= 20:
                    logger.warning("Too many failed webcam reads. Attempting to reopen camera.")
                    if self.capture is not None:
                        self.capture.release()
                    self.capture = self._open_camera()
                    self.failed_reads = 0
                time.sleep(0.2)
                continue
            self.failed_reads = 0

            detections = self.detector.detect(frame)
            annotated = frame.copy()
            plate_detected = False
            ocr_done = False
            rc_checked = False
            challan_generated = False

            for detection in detections:
                x1, y1, x2, y2 = detection["bbox"]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                plate_detected = True

                plate_number = self.ocr.read_plate(detection["crop_path"])
                if not plate_number:
                    continue
                ocr_done = True

                label_text = plate_number
                confidence = detection.get("confidence")
                if isinstance(confidence, (int, float)):
                    confidence_percent = confidence * 100 if confidence <= 1 else confidence
                    confidence_percent = max(0.0, min(100.0, confidence_percent))
                    label_text = f"{plate_number} ({confidence_percent:.0f}%)"

                cv2.putText(
                    annotated,
                    label_text,
                    (x1, max(y1 - 12, 30)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                )
                self._handle_detection(plate_number, frame, (x1, y1, x2, y2))
                rc_checked = True
                challan_generated = bool(self.last_detection.get("violation"))

            status_lines = [
                (plate_detected, "Plate Detected"),
                (ocr_done, "OCR Completed"),
                (rc_checked, "RC Verified"),
                (challan_generated, "Challan Generated"),
            ]
            y = 30
            for checked, text in status_lines:
                marker = "[\u2714] " if checked else "[ ] "
                color = (0, 220, 0) if checked else (170, 170, 170)
                cv2.putText(
                    annotated,
                    f"{marker}{text}",
                    (15, y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                )
                y += 26

            with self.lock:
                self.current_frame = annotated

        logger.info("Camera processing loop stopped")

    def _handle_detection(self, plate_number: str, frame, bbox):
        now = time.time()
        if plate_number == self.last_processed_plate and now - self.last_processed_at < 10:
            return

        self.last_processed_plate = plate_number
        self.last_processed_at = now

        timestamp = datetime.now()
        location = "Main Gate Junction"
        snapshot_path = self._save_plate_snapshot(frame, bbox, plate_number, timestamp)
        snapshot_name = os.path.basename(snapshot_path) if snapshot_path else None
        snapshot_url = f"/captured_plates/{snapshot_name}" if snapshot_name else None

        vehicle = self.db.get_vehicle(plate_number)
        if not vehicle:
            logger.info("Detected unknown vehicle %s", plate_number)
            self.db.log_detection(plate_number, "NOT FOUND", snapshot_path)
            self.last_detection = {
                **self._default_detection_state(),
                "vehicle_number": plate_number,
                "owner_name": "Unknown",
                "vehicle_model": "Not in database",
                "rc_status": "NOT FOUND",
                "last_seen": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "message": "Vehicle not present in RC database",
                "snapshot_url": snapshot_url,
                "snapshot_name": snapshot_name,
            }
            return

        expired = self.db.is_rc_expired(vehicle["rc_expiry_date"])
        status = "EXPIRED" if expired else "VALID"
        self.db.log_detection(plate_number, status, snapshot_path)

        fine_amount = 2000 if expired else 0
        challan_status = "No challan generated"
        challan = None
        pdf_name = None
        pdf_url = None

        if expired:
            if not self.db.has_recent_challan(plate_number, seconds=60):
                challan = self.challan_generator.generate_challan(
                    vehicle=vehicle,
                    violation_type="RC Expired",
                    fine_amount=fine_amount,
                    location=location,
                )
                challan_status = "Challan Generated"
                logger.info("Generated challan for %s", plate_number)
            else:
                challan = self.db.get_latest_challan_for_vehicle(plate_number)
                challan_status = "Recent challan already exists"

            if challan and challan.get("pdf_path"):
                pdf_name = os.path.basename(challan["pdf_path"])
                pdf_url = f"/challan_files/{pdf_name}"

        self.last_detection = {
            **self._default_detection_state(),
            "vehicle_number": plate_number,
            "owner_name": vehicle["owner_name"],
            "vehicle_model": vehicle["vehicle_model"],
            "rc_status": status,
            "rc_expiry_date": vehicle["rc_expiry_date"],
            "fine_amount": fine_amount,
            "challan_status": challan_status,
            "last_seen": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "location": location,
            "violation": expired,
            "challan": challan,
            "message": "Digital challan generated for expired RC" if expired else "RC is valid",
            "snapshot_url": snapshot_url,
            "snapshot_name": snapshot_name,
            "download_url": pdf_url,
            "download_name": pdf_name,
            "alert_title": "RC EXPIRED" if expired else "",
            "alert_text": "Digital Challan Generated | Fine: INR 2000" if expired else "",
        }

    def _save_plate_snapshot(self, frame, bbox, plate_number: str, timestamp: datetime):
        x1, y1, x2, y2 = bbox
        crop = frame[max(0, y1):max(y1, y2), max(0, x1):max(x1, x2)]
        if crop is None or getattr(crop, "size", 0) == 0:
            return None

        filename = f"plate_{plate_number}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
        path = os.path.join(CAPTURED_PLATES_DIR, filename)
        cv2.imwrite(path, crop)
        return path

    def get_frame_bytes(self):
        with self.lock:
            frame = self.current_frame.copy() if self.current_frame is not None else None

        if frame is None:
            return None

        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            return None
        return buffer.tobytes()

    def _build_error_frame(self, message: str):
        frame = np.full((540, 960, 3), (18, 25, 38), dtype=np.uint8)
        cv2.putText(frame, "Camera Error", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 170, 255), 3)
        cv2.putText(frame, message, (40, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
        if self.camera_index is not None:
            cv2.putText(
                frame,
                f"Last working camera index: {self.camera_index}",
                (40, 255),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (200, 220, 255),
                2,
            )
        return frame

    def shutdown(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        if self.capture is not None and self.capture.isOpened():
            self.capture.release()
    def process_browser_frame(self, frame):
        detections = self.detector.detect(frame)

        annotated = frame.copy()

        for detection in detections:
            x1, y1, x2, y2 = detection["bbox"]

            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

            plate_number = self.ocr.read_plate(detection["crop_path"])

            if plate_number:
               cv2.putText(
                   annotated,
                   plate_number,
                   (x1, y1 - 10),
                   cv2.FONT_HERSHEY_SIMPLEX,
                   0.8,
                   (0, 255, 0),
                   2,
            )

            self._handle_detection(
                plate_number,
                frame,
                (x1, y1, x2, y2)
            )

        self.current_frame = annotated

monitor = MonitoringSystem()
atexit.register(monitor.shutdown)


def generate_frames():
    while True:
        success = monitor.capture is not None and monitor.capture.isOpened()
        frame = monitor.get_frame_bytes()
        if not success or frame is None:
            time.sleep(0.1)
            frame = monitor.get_frame_bytes()
            if frame is None:
                continue

        yield b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/challans")
def challans():
    return render_template("challans.html")


@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/captured_plates/<path:filename>")
def captured_plate_file(filename):
    return send_from_directory(CAPTURED_PLATES_DIR, filename)


@app.route("/challan_files/<path:filename>")
def challan_file(filename):
    return send_from_directory(CHALLANS_DIR, filename, as_attachment=True)

@app.route("/upload_frame", methods=["POST"])
def upload_frame():
    file = request.files.get("frame")

    if not file:
        return jsonify({"error": "No frame uploaded"}), 400

    npimg = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    if frame is None:
        return jsonify({"error": "Invalid image"}), 400

    monitor.process_browser_frame(frame)

    return jsonify({
        "success": True,
        "detection": monitor.last_detection
    })

@app.route("/api/status")
def api_status():
    return jsonify(
        {
            "current": monitor.last_detection,
            "history": monitor.db.get_recent_detections(limit=10),
            "challans": monitor.db.get_recent_challans(limit=10),
            "vehicles": monitor.db.get_all_vehicles(),
            "stats": monitor.db.get_dashboard_stats(),
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, use_reloader=False, host="0.0.0.0", port=port, threaded=True)

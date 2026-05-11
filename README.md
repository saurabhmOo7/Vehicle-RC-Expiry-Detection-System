# Real-Time Vehicle RC Expiry Detection and Smart Challan System

This project is a final year project demo that simulates a traffic monitoring pipeline on a local laptop. It captures webcam video, detects a vehicle number plate, extracts the registration number with OCR, validates RC status from a SQLite database, and generates a digital challan if the RC has expired.

## Features

- Live webcam stream on a Flask dashboard
- YOLOv8-based plate detection hook with a built-in contour fallback for offline demos
- OCR using Tesseract with grayscale, blur, and threshold preprocessing
- SQLite database for vehicle records, detections, and challans
- Bootstrap dashboard with live updates using JavaScript
- PDF challan generation with `reportlab`
- Logging and sample seed data

## Project Structure

```text
project/
├── app.py
├── challan/
│   └── challan_generator.py
├── database/
│   └── db.py
├── detection/
│   └── plate_detector.py
├── logs/
├── models/
│   └── yolov8_plate.pt
├── ocr/
│   └── ocr_reader.py
├── sample_data/
│   ├── challans/
│   ├── crops/
│   ├── demo_plate_1.svg
│   └── demo_plate_2.svg
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── dashboard.js
├── templates/
│   ├── challans.html
│   ├── dashboard.html
│   └── index.html
├── utils/
│   └── image_processing.py
├── vehicles.db
└── requirements.txt
```

## Setup

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Install Tesseract OCR and ensure `tesseract` is available in your PATH.

Windows example:

```powershell
tesseract --version
```

4. Optional but recommended: place a trained number plate YOLOv8 model at `models/yolov8_plate.pt`.

If the model file is missing, the app still runs using a contour-based fallback detector for demonstration.

## Run

```bash
python app.py
```

Open `http://127.0.0.1:5000` in a browser.

## Demo Data

Seed data includes:

- `DL01AB1234` | Rahul Sharma | RC expiry `2023-05-10`
- `MH12CD5678` | Priya Mehta | RC expiry `2027-11-28`
- `KA03EF9012` | Amit Verma | RC expiry `2024-08-14`
- `UP16GH3456` | Sneha Kapoor | RC expiry `2028-01-19`

On March 13, 2026, detecting `DL01AB1234` correctly results in `RC EXPIRED` and a challan with fine amount `INR 2000`.

## Notes

- `vehicles.db` is created automatically on first run.
- `sample_data/crops` stores cropped number plate images.
- `sample_data/challans` stores generated PDF challans.
- Logs are written to `logs/system.log`.
- For best OCR results, show a clear plate close to the webcam or test with the sample SVG plates.

## Future Improvements

- Add a trained Indian license plate model
- Add email notifications for challans
- Add searchable logs and filtering
- Add multi-camera support

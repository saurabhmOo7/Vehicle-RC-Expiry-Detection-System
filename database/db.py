import os
import sqlite3
from datetime import datetime, timedelta


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self):
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize_database(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        with self._connect() as conn:
            self._initialize_vehicles_table(conn)
            self._initialize_challans_table(conn)
            self._initialize_detections_table(conn)
            self._seed_data(conn)
            conn.commit()

    def _initialize_vehicles_table(self, conn):
        expected = {"vehicle_number", "owner_name", "vehicle_model", "rc_expiry_date"}
        columns = self._get_columns(conn, "vehicles")
        if columns != expected:
            conn.execute("DROP TABLE IF EXISTS vehicles")
            conn.execute(
                """
                CREATE TABLE vehicles (
                    vehicle_number TEXT PRIMARY KEY,
                    owner_name TEXT NOT NULL,
                    vehicle_model TEXT NOT NULL,
                    rc_expiry_date TEXT NOT NULL
                )
                """
            )

    def _initialize_challans_table(self, conn):
        expected = {
            "id",
            "vehicle_number",
            "owner_name",
            "violation_type",
            "fine_amount",
            "timestamp",
            "pdf_path",
        }
        columns = self._get_columns(conn, "challans")
        if columns != expected:
            conn.execute("DROP TABLE IF EXISTS challans")
            conn.execute(
                """
                CREATE TABLE challans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_number TEXT NOT NULL,
                    owner_name TEXT NOT NULL,
                    violation_type TEXT NOT NULL,
                    fine_amount INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    pdf_path TEXT
                )
                """
            )

    def _initialize_detections_table(self, conn):
        expected = {"id", "vehicle_number", "timestamp", "rc_status", "image_path"}
        columns = self._get_columns(conn, "detections")
        if columns != expected:
            conn.execute("DROP TABLE IF EXISTS detections")
            conn.execute(
                """
                CREATE TABLE detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_number TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    rc_status TEXT NOT NULL,
                    image_path TEXT
                )
                """
            )

    def _get_columns(self, conn, table_name: str):
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
        if not exists:
            return set()
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row[1] for row in rows}

    def _seed_data(self, conn):
        seed_rows = [
            ("DL01AB1234", "Rahul Sharma", "Honda City", "2023-05-10"),
            ("DL02CD5678", "Priya Singh", "Hyundai i20", "2027-11-20"),
            ("UP14EF4321", "Amit Verma", "Maruti Swift", "2022-04-15"),
            ("HR26GH8765", "Neha Kapoor", "Kia Seltos", "2026-03-18"),
            ("DL05JK1111", "Rohit Mehta", "Toyota Innova", "2021-09-30"),
            ("UP16LM2222", "Pooja Sharma", "Tata Nexon", "2028-01-12"),
            ("HR12NO3333", "Vikram Singh", "Mahindra XUV700", "2023-02-10"),
            ("DL03PQ4444", "Ankit Gupta", "Skoda Rapid", "2025-08-09"),
            ("UP32RS5555", "Deepak Yadav", "Maruti Baleno", "2022-12-21"),
            ("HR55TU6666", "Sneha Arora", "Hyundai Creta", "2026-06-17"),
            ("DL08VW7777", "Ramesh Patel", "Honda Amaze", "2021-07-11"),
            ("UP78XY8888", "Karan Khanna", "MG Hector", "2027-10-01"),
            ("HR20ZA9999", "Simran Kaur", "Tata Harrier", "2023-06-22"),
            ("DL09BC1010", "Aditya Jain", "Volkswagen Polo", "2024-03-15"),
            ("UP80DE2020", "Arjun Malhotra", "Ford Ecosport", "2028-09-09"),
        ]
        conn.executemany(
            """
            INSERT INTO vehicles (vehicle_number, owner_name, vehicle_model, rc_expiry_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(vehicle_number) DO UPDATE SET
                owner_name = excluded.owner_name,
                vehicle_model = excluded.vehicle_model,
                rc_expiry_date = excluded.rc_expiry_date
            """,
            seed_rows,
        )

    def get_vehicle(self, vehicle_number: str):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM vehicles WHERE vehicle_number = ?",
                (vehicle_number,),
            ).fetchone()
            return dict(row) if row else None

    def get_all_vehicles(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM vehicles ORDER BY vehicle_number ASC"
            ).fetchall()
            return [dict(row) for row in rows]

    def is_rc_expired(self, rc_expiry_date: str) -> bool:
        expiry = datetime.strptime(rc_expiry_date, "%Y-%m-%d").date()
        return expiry < datetime.now().date()

    def create_challan(self, vehicle_number, owner_name, violation_type, fine_amount, pdf_path=None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO challans (
                    vehicle_number, owner_name, violation_type, fine_amount, timestamp, pdf_path
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    vehicle_number,
                    owner_name,
                    violation_type,
                    fine_amount,
                    timestamp,
                    pdf_path,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM challans WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            return dict(row)

    def has_recent_challan(self, vehicle_number: str, seconds: int = 60) -> bool:
        threshold = (datetime.now() - timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM challans
                WHERE vehicle_number = ? AND timestamp >= ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (vehicle_number, threshold),
            ).fetchone()
            return row is not None

    def get_latest_challan_for_vehicle(self, vehicle_number: str):
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM challans
                WHERE vehicle_number = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (vehicle_number,),
            ).fetchone()
            return dict(row) if row else None

    def log_detection(self, vehicle_number: str, status: str, image_path: str | None):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO detections (vehicle_number, timestamp, rc_status, image_path)
                VALUES (?, ?, ?, ?)
                """,
                (
                    vehicle_number,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    status,
                    image_path,
                ),
            )
            conn.commit()

    def get_recent_detections(self, limit: int = 10):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM detections
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_recent_challans(self, limit: int = 10):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM challans
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_dashboard_stats(self):
        with self._connect() as conn:
            total_vehicles = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
            total_detections = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
            total_challans = conn.execute("SELECT COUNT(*) FROM challans").fetchone()[0]
            expired_rc = conn.execute(
                """
                SELECT COUNT(*) FROM vehicles
                WHERE DATE(rc_expiry_date) < DATE('now')
                """
            ).fetchone()[0]
            return {
                "total_vehicles": total_vehicles,
                "total_detections": total_detections,
                "total_challans": total_challans,
                "expired_rc": expired_rc,
            }

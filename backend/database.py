import aiosqlite
import logging
from config import Config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_path = Config.DATABASE_PATH

    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS print_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    moonraker_job_id TEXT UNIQUE,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_time REAL,
                    end_time REAL,
                    print_duration REAL DEFAULT 0,
                    total_duration REAL DEFAULT 0,
                    filament_used_mm REAL DEFAULT 0,
                    filament_used_g REAL DEFAULT 0,
                    spool_id INTEGER,
                    spool_name TEXT,
                    filament_type TEXT,
                    filament_color TEXT,
                    filament_cost_per_kg REAL DEFAULT 0,
                    filament_cost REAL DEFAULT 0,
                    electricity_cost REAL DEFAULT 0,
                    total_cost REAL DEFAULT 0,
                    metadata_thumbnail TEXT,
                    metadata_slicer TEXT,
                    metadata_layer_height REAL,
                    metadata_object_height REAL,
                    metadata_estimated_time REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cost_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value REAL NOT NULL,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    jobs_imported INTEGER DEFAULT 0,
                    jobs_updated INTEGER DEFAULT 0,
                    errors TEXT
                )
            """)
            defaults = [
                ("electricity_cost_per_kwh", Config.ELECTRICITY_COST_PER_KWH, "Stromkosten pro kWh in EUR"),
                ("printer_power_watts", Config.PRINTER_POWER_WATTS, "Druckerleistung in Watt"),
                ("default_filament_cost_per_kg", Config.DEFAULT_FILAMENT_COST_PER_KG, "Standard Filamentkosten pro kg"),
            ]
            for key, value, desc in defaults:
                await db.execute(
                    "INSERT OR IGNORE INTO cost_settings (key, value, description) VALUES (?, ?, ?)",
                    (key, value, desc))
            await db.commit()
            logger.info("Datenbank initialisiert")

    async def get_setting(self, key):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT value FROM cost_settings WHERE key = ?", (key,))
            row = await cursor.fetchone()
            return row[0] if row else 0.0

    async def update_setting(self, key, value):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE cost_settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
                (value, key))
            await db.commit()

    async def get_all_settings(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT key, value, description FROM cost_settings")
            rows = await cursor.fetchall()
            return {row["key"]: {"value": row["value"], "description": row["description"]} for row in rows}

    async def job_exists(self, moonraker_job_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id FROM print_jobs WHERE moonraker_job_id = ?", (moonraker_job_id,))
            return await cursor.fetchone() is not None

    async def insert_job(self, job_data):
        """Neuen Job einfügen oder existierenden komplett ersetzen (inkl. Spule)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO print_jobs (
                    moonraker_job_id, filename, status, start_time, end_time,
                    print_duration, total_duration, filament_used_mm, filament_used_g,
                    spool_id, spool_name, filament_type, filament_color,
                    filament_cost_per_kg, filament_cost, electricity_cost, total_cost,
                    metadata_thumbnail, metadata_slicer, metadata_layer_height,
                    metadata_object_height, metadata_estimated_time, updated_at
                ) VALUES (
                    :moonraker_job_id, :filename, :status, :start_time, :end_time,
                    :print_duration, :total_duration, :filament_used_mm, :filament_used_g,
                    :spool_id, :spool_name, :filament_type, :filament_color,
                    :filament_cost_per_kg, :filament_cost, :electricity_cost, :total_cost,
                    :metadata_thumbnail, :metadata_slicer, :metadata_layer_height,
                    :metadata_object_height, :metadata_estimated_time, CURRENT_TIMESTAMP
                )""", job_data)
            await db.commit()

    async def sync_job(self, job_data):
        """Job beim Sync einfügen. Bei existierenden Jobs wird die manuelle Spulenzuordnung beibehalten."""
        async with aiosqlite.connect(self.db_path) as db:
            # Prüfen ob Job bereits existiert
            cursor = await db.execute(
                "SELECT spool_id, spool_name, filament_type, filament_color, filament_cost_per_kg FROM print_jobs WHERE moonraker_job_id = ?",
                (job_data["moonraker_job_id"],)
            )
            existing = await cursor.fetchone()
            if existing:
                # Job existiert bereits — nur Status/Daten aktualisieren, Spule beibehalten
                await db.execute("""
                    UPDATE print_jobs SET
                        filename=:filename, status=:status,
                        print_duration=:print_duration, total_duration=:total_duration,
                        filament_used_mm=:filament_used_mm, filament_used_g=:filament_used_g,
                        metadata_thumbnail=:metadata_thumbnail, metadata_slicer=:metadata_slicer,
                        metadata_layer_height=:metadata_layer_height,
                        metadata_object_height=:metadata_object_height,
                        metadata_estimated_time=:metadata_estimated_time,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE moonraker_job_id=:moonraker_job_id
                """, job_data)
            else:
                # Neuer Job — komplett einfügen
                await db.execute("""
                    INSERT INTO print_jobs (
                        moonraker_job_id, filename, status, start_time, end_time,
                        print_duration, total_duration, filament_used_mm, filament_used_g,
                        spool_id, spool_name, filament_type, filament_color,
                        filament_cost_per_kg, filament_cost, electricity_cost, total_cost,
                        metadata_thumbnail, metadata_slicer, metadata_layer_height,
                        metadata_object_height, metadata_estimated_time
                    ) VALUES (
                        :moonraker_job_id, :filename, :status, :start_time, :end_time,
                        :print_duration, :total_duration, :filament_used_mm, :filament_used_g,
                        :spool_id, :spool_name, :filament_type, :filament_color,
                        :filament_cost_per_kg, :filament_cost, :electricity_cost, :total_cost,
                        :metadata_thumbnail, :metadata_slicer, :metadata_layer_height,
                        :metadata_object_height, :metadata_estimated_time
                    )""", job_data)
            await db.commit()
            return existing is not None

    async def get_all_jobs(self, limit=100, offset=0, status_filter=None, sort_by="end_time", sort_order="desc"):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            where = ""
            params = []
            if status_filter and status_filter != "all":
                where = "WHERE status = ?"
                params.append(status_filter)
            count_cursor = await db.execute(f"SELECT COUNT(*) FROM print_jobs {where}", params)
            total = (await count_cursor.fetchone())[0]
            allowed = ["end_time","start_time","total_cost","filename","filament_used_g","print_duration"]
            if sort_by not in allowed:
                sort_by = "end_time"
            order = "DESC" if sort_order.lower() == "desc" else "ASC"
            cursor = await db.execute(
                f"SELECT * FROM print_jobs {where} ORDER BY {sort_by} {order} LIMIT ? OFFSET ?",
                params + [limit, offset])
            rows = await cursor.fetchall()
            return [dict(row) for row in rows], total

    async def get_job_by_id(self, job_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM print_jobs WHERE id = ?", (job_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_statistics(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT COUNT(*) as total_jobs,
                    SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed_jobs,
                    SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) as cancelled_jobs,
                    SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as error_jobs,
                    COALESCE(SUM(total_cost),0) as total_cost,
                    COALESCE(SUM(filament_cost),0) as total_filament_cost,
                    COALESCE(SUM(electricity_cost),0) as total_electricity_cost,
                    COALESCE(SUM(filament_used_g),0) as total_filament_g,
                    COALESCE(SUM(print_duration),0) as total_print_time,
                    COALESCE(AVG(CASE WHEN status='completed' THEN total_cost END),0) as avg_cost_per_print
                FROM print_jobs
            """)
            stats = dict(await cursor.fetchone())
            c2 = await db.execute("""
                SELECT filament_type, COUNT(*) as count,
                    COALESCE(SUM(filament_used_g),0) as total_g,
                    COALESCE(SUM(total_cost),0) as total_cost
                FROM print_jobs WHERE filament_type IS NOT NULL
                GROUP BY filament_type ORDER BY total_cost DESC
            """)
            stats["by_filament_type"] = [dict(r) for r in await c2.fetchall()]
            c3 = await db.execute("""
                SELECT strftime('%Y-%m', datetime(end_time,'unixepoch')) as month,
                    COUNT(*) as count,
                    COALESCE(SUM(total_cost),0) as total_cost,
                    COALESCE(SUM(filament_used_g),0) as total_filament_g
                FROM print_jobs WHERE end_time IS NOT NULL
                GROUP BY month ORDER BY month DESC LIMIT 12
            """)
            stats["by_month"] = [dict(r) for r in await c3.fetchall()]
            return stats

    async def update_job_spool(self, job_id, spool_id, spool_name, filament_type, filament_color, cost_per_kg, filament_cost, electricity_cost, total_cost):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE print_jobs SET
                    spool_id=?, spool_name=?, filament_type=?, filament_color=?,
                    filament_cost_per_kg=?, filament_cost=?, electricity_cost=?, total_cost=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (spool_id, spool_name, filament_type, filament_color,
                   cost_per_kg, filament_cost, electricity_cost, total_cost, job_id))
            await db.commit()

    async def delete_job(self, job_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM print_jobs WHERE id = ?", (job_id,))
            await db.commit()

    async def log_sync(self, jobs_imported, jobs_updated, errors=None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sync_log (jobs_imported, jobs_updated, errors) VALUES (?,?,?)",
                (jobs_imported, jobs_updated, errors))
            await db.commit()

    async def get_last_sync(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM sync_log ORDER BY sync_time DESC LIMIT 1")
            row = await cursor.fetchone()
            return dict(row) if row else None

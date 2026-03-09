import aiosqlite
import logging
from config import Config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_path = Config.DATABASE_PATH

    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            # ── Legacy CFS-Slots ───────────────────────────────────────────────
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cfs_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot_key TEXT UNIQUE NOT NULL,
                    slot_label TEXT NOT NULL,
                    spool_id INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            default_slots = [
                ("CFS1A", "CFS 1A"), ("CFS1B", "CFS 1B"),
                ("CFS1C", "CFS 1C"), ("CFS1D", "CFS 1D"), ("LAGER", "Lager"),
            ]
            for key, label in default_slots:
                await db.execute(
                    "INSERT OR IGNORE INTO cfs_slots (slot_key, slot_label, spool_id) VALUES (?,?,NULL)",
                    (key, label))

            # ── Eigene Spulenverwaltung ────────────────────────────────────────
            await db.execute("""
                CREATE TABLE IF NOT EXISTS filament_vendors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    website TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS filaments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vendor_id INTEGER REFERENCES filament_vendors(id) ON DELETE SET NULL,
                    name TEXT NOT NULL,
                    material TEXT NOT NULL,
                    color_name TEXT,
                    color_hex TEXT,
                    diameter REAL DEFAULT 1.75,
                    density REAL DEFAULT 1.24,
                    weight_per_spool REAL DEFAULT 1000,
                    price_per_spool REAL DEFAULT 0,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS spools (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filament_id INTEGER REFERENCES filaments(id) ON DELETE SET NULL,
                    label TEXT,
                    location TEXT,
                    initial_weight REAL DEFAULT 1000,
                    remaining_weight REAL DEFAULT 1000,
                    is_active INTEGER DEFAULT 0,
                    is_empty INTEGER DEFAULT 0,
                    purchase_date TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ── Print Jobs ────────────────────────────────────────────────────
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

    # ── Settings ──────────────────────────────────────────────────────────────
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

    # ── Print Jobs ────────────────────────────────────────────────────────────
    async def sync_job(self, job_data):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT spool_id, spool_name, filament_type, filament_color, filament_cost_per_kg, filament_used_g FROM print_jobs WHERE moonraker_job_id = ?",
                (job_data["moonraker_job_id"],)
            )
            existing = await cursor.fetchone()
            if existing:
                existing_filament_g = existing[5]
                filament_g_to_use = job_data["filament_used_g"] \
                    if (not existing_filament_g or existing_filament_g <= 0) \
                    else existing_filament_g
                await db.execute("""
                    UPDATE print_jobs SET
                        filename=:filename, status=:status,
                        print_duration=:print_duration, total_duration=:total_duration,
                        filament_used_mm=:filament_used_mm,
                        metadata_thumbnail=:metadata_thumbnail, metadata_slicer=:metadata_slicer,
                        metadata_layer_height=:metadata_layer_height,
                        metadata_object_height=:metadata_object_height,
                        metadata_estimated_time=:metadata_estimated_time,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE moonraker_job_id=:moonraker_job_id
                """, job_data)
                if filament_g_to_use != existing_filament_g:
                    await db.execute(
                        "UPDATE print_jobs SET filament_used_g=? WHERE moonraker_job_id=?",
                        (filament_g_to_use, job_data["moonraker_job_id"]))
            else:
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

    async def get_all_jobs(self, limit=100, offset=0, status_filter=None, sort_by="end_time", sort_order="desc", filament_type_filter=None):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            conditions = []
            params = []
            if status_filter and status_filter != "all":
                conditions.append("status = ?")
                params.append(status_filter)
            if filament_type_filter and filament_type_filter != "all":
                conditions.append("filament_type = ?")
                params.append(filament_type_filter)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            count_cursor = await db.execute(f"SELECT COUNT(*) FROM print_jobs {where}", params)
            total = (await count_cursor.fetchone())[0]
            allowed = ["end_time", "start_time", "total_cost", "filename", "filament_used_g", "print_duration"]
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

    async def get_all_moonraker_job_ids(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT moonraker_job_id FROM print_jobs")
            rows = await cursor.fetchall()
            return {row[0] for row in rows}

    async def get_distinct_filament_types(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT DISTINCT filament_type FROM print_jobs WHERE filament_type IS NOT NULL AND filament_type != 'Unbekannt' ORDER BY filament_type")
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def update_job_filament(self, job_id, filament_g, filament_cost, electricity_cost, total_cost):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE print_jobs SET
                    filament_used_g=?, filament_cost=?, electricity_cost=?, total_cost=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (filament_g, filament_cost, electricity_cost, total_cost, job_id))
            await db.commit()

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

    # ── CFS-Slots (Legacy) ────────────────────────────────────────────────────
    async def get_cfs_slots(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT slot_key, slot_label, spool_id FROM cfs_slots ORDER BY id")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def update_cfs_slot(self, slot_key, spool_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE cfs_slots SET spool_id=?, updated_at=CURRENT_TIMESTAMP WHERE slot_key=?",
                (spool_id, slot_key))
            await db.commit()

    async def get_spool_id_to_slot(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT slot_label, spool_id FROM cfs_slots WHERE spool_id IS NOT NULL")
            rows = await cursor.fetchall()
            return {row["spool_id"]: row["slot_label"] for row in rows}

    # ── Eigene Spulenverwaltung: Vendors ──────────────────────────────────────
    async def get_all_vendors(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM filament_vendors ORDER BY name")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_vendor_by_id(self, vendor_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM filament_vendors WHERE id = ?", (vendor_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_vendor(self, name, website=None, notes=None):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO filament_vendors (name, website, notes) VALUES (?, ?, ?)",
                (name, website, notes))
            await db.commit()
            return cursor.lastrowid

    async def update_vendor(self, vendor_id, name, website=None, notes=None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE filament_vendors SET name=?, website=?, notes=? WHERE id=?",
                (name, website, notes, vendor_id))
            await db.commit()

    async def delete_vendor(self, vendor_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM filament_vendors WHERE id = ?", (vendor_id,))
            await db.commit()

    # ── Eigene Spulenverwaltung: Filaments ────────────────────────────────────
    async def get_all_filaments(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT f.*, v.name as vendor_name
                FROM filaments f
                LEFT JOIN filament_vendors v ON f.vendor_id = v.id
                ORDER BY v.name, f.material, f.name
            """)
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_filament_by_id(self, filament_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT f.*, v.name as vendor_name
                FROM filaments f
                LEFT JOIN filament_vendors v ON f.vendor_id = v.id
                WHERE f.id = ?
            """, (filament_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_filament(self, data: dict):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO filaments
                    (vendor_id, name, material, color_name, color_hex, diameter, density,
                     weight_per_spool, price_per_spool, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("vendor_id"), data["name"], data["material"],
                data.get("color_name"), data.get("color_hex"),
                data.get("diameter", 1.75), data.get("density", 1.24),
                data.get("weight_per_spool", 1000), data.get("price_per_spool", 0),
                data.get("notes")
            ))
            await db.commit()
            return cursor.lastrowid

    async def update_filament(self, filament_id, data: dict):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE filaments SET
                    vendor_id=?, name=?, material=?, color_name=?, color_hex=?,
                    diameter=?, density=?, weight_per_spool=?, price_per_spool=?, notes=?
                WHERE id=?
            """, (
                data.get("vendor_id"), data["name"], data["material"],
                data.get("color_name"), data.get("color_hex"),
                data.get("diameter", 1.75), data.get("density", 1.24),
                data.get("weight_per_spool", 1000), data.get("price_per_spool", 0),
                data.get("notes"), filament_id
            ))
            await db.commit()

    async def delete_filament(self, filament_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM filaments WHERE id = ?", (filament_id,))
            await db.commit()

    # ── Eigene Spulenverwaltung: Spools ───────────────────────────────────────
    async def get_all_local_spools(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT s.*,
                    f.name as filament_name, f.material, f.color_hex, f.color_name,
                    f.diameter, f.density, f.weight_per_spool, f.price_per_spool,
                    v.name as vendor_name
                FROM spools s
                LEFT JOIN filaments f ON s.filament_id = f.id
                LEFT JOIN filament_vendors v ON f.vendor_id = v.id
                ORDER BY s.is_active DESC, s.location, s.id
            """)
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_local_spool_by_id(self, spool_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT s.*,
                    f.name as filament_name, f.material, f.color_hex, f.color_name,
                    f.diameter, f.density, f.weight_per_spool, f.price_per_spool,
                    v.name as vendor_name
                FROM spools s
                LEFT JOIN filaments f ON s.filament_id = f.id
                LEFT JOIN filament_vendors v ON f.vendor_id = v.id
                WHERE s.id = ?
            """, (spool_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_local_spool(self, data: dict):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO spools
                    (filament_id, label, location, initial_weight, remaining_weight,
                     is_active, is_empty, purchase_date, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("filament_id"),
                data.get("label"),
                data.get("location"),
                data.get("initial_weight", 1000),
                data.get("remaining_weight", data.get("initial_weight", 1000)),
                1 if data.get("is_active") else 0,
                0,
                data.get("purchase_date"),
                data.get("notes")
            ))
            await db.commit()
            return cursor.lastrowid

    async def update_local_spool(self, spool_id, data: dict):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE spools SET
                    filament_id=?, label=?, location=?, initial_weight=?, remaining_weight=?,
                    is_active=?, is_empty=?, purchase_date=?, notes=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                data.get("filament_id"),
                data.get("label"),
                data.get("location"),
                data.get("initial_weight", 1000),
                data.get("remaining_weight", 1000),
                1 if data.get("is_active") else 0,
                1 if data.get("is_empty") else 0,
                data.get("purchase_date"),
                data.get("notes"),
                spool_id
            ))
            await db.commit()

    async def delete_local_spool(self, spool_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM spools WHERE id = ?", (spool_id,))
            await db.commit()

    async def deduct_filament_from_spool(self, spool_id, used_g):
        """Verbrauch vom verbleibenden Gewicht abziehen (min. 0)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE spools SET
                    remaining_weight = MAX(0, remaining_weight - ?),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (used_g, spool_id))
            await db.commit()

    async def get_local_spool_locations(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT DISTINCT location FROM spools WHERE location IS NOT NULL AND location != '' ORDER BY location")
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

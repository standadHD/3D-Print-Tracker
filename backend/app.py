import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import Database
from moonraker_client import MoonrakerClient
from spoolman_client import SpoolmanClient
from cost_calculator import CostCalculator
from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

db = Database()
moonraker = MoonrakerClient()
spoolman = SpoolmanClient()
calculator = CostCalculator()
scheduler = AsyncIOScheduler()

last_printer_state = {"state": None}

async def process_job(job):
    job_id = str(job.get("job_id", ""))
    if not job_id:
        return None
    status_map = {"completed": "completed", "cancelled": "cancelled",
                  "error": "error", "klippy_shutdown": "error",
                  "klippy_disconnect": "error", "server_exit": "error"}
    raw_status = job.get("status", "unknown")
    status = status_map.get(raw_status, raw_status)
    filename = job.get("filename", "unknown")
    metadata = job.get("metadata", {})
    filament_mm = job.get("filament_used", 0) or metadata.get("filament_total", 0) or 0
    spool = await spoolman.find_spool_for_job(job)
    fi = await spoolman.get_filament_info(spool)
    filament_g = calculator.mm_to_grams(filament_mm, fi["diameter"], fi["density"])
    if filament_g <= 0:
        filament_g = metadata.get("filament_weight_total", 0) or 0
    el_kwh = await db.get_setting("electricity_cost_per_kwh")
    pr_watts = await db.get_setting("printer_power_watts")
    duration = job.get("print_duration", 0) or 0
    f_cost = calculator.calc_filament_cost(filament_g, fi["cost_per_kg"])
    e_cost = calculator.calc_electricity_cost(duration, pr_watts, el_kwh)
    t_cost = calculator.calc_total_cost(f_cost, e_cost)
    thumbs = metadata.get("thumbnails", [])
    thumb = thumbs[-1].get("relative_path", "") if thumbs else ""
    # Location aus Spoolman-Spool direkt lesen
    spool_name = fi["spool_name"]
    if spool and spool.get("location"):
        spool_name = f"{spool['location']} – {spool_name}"
    return {
        "moonraker_job_id": job_id, "filename": filename, "status": status,
        "start_time": job.get("start_time"), "end_time": job.get("end_time"),
        "print_duration": duration, "total_duration": job.get("total_duration", 0),
        "filament_used_mm": round(filament_mm, 2), "filament_used_g": filament_g,
        "spool_id": fi["spool_id"], "spool_name": spool_name,
        "filament_type": fi["filament_type"], "filament_color": fi["filament_color"],
        "filament_cost_per_kg": fi["cost_per_kg"],
        "filament_cost": f_cost, "electricity_cost": e_cost, "total_cost": t_cost,
        "metadata_thumbnail": thumb,
        "metadata_slicer": metadata.get("slicer", ""),
        "metadata_layer_height": metadata.get("layer_height"),
        "metadata_object_height": metadata.get("object_height"),
        "metadata_estimated_time": metadata.get("estimated_time"),
    }

async def sync_jobs():
    logger.info("Starte Job-Synchronisation...")
    imported = 0
    updated = 0
    errors = []
    try:
        jobs = await moonraker.get_all_job_history()
        for job in jobs:
            try:
                job_data = await process_job(job)
                if job_data:
                    existed = await db.sync_job(job_data)
                    if existed:
                        updated += 1
                    else:
                        imported += 1
            except Exception as e:
                errors.append(str(e))
                logger.error(f"Job Fehler: {e}")
    except Exception as e:
        errors.append(str(e))
        logger.error(f"Sync Fehler: {e}")
    await db.log_sync(imported, updated, "; ".join(errors) if errors else None)
    logger.info(f"Sync fertig: {imported} neu, {updated} aktualisiert, {len(errors)} Fehler")

async def check_printer_state():
    try:
        status = await moonraker.get_printer_status()
        ps = status.get("print_stats", {})
        state = ps.get("state", "unknown")
        prev = last_printer_state["state"]
        if prev == "printing" and state in ("standby", "complete", "error", "cancelled"):
            logger.info(f"Druck beendet ({prev} -> {state}), starte Sync...")
            await asyncio.sleep(3)
            await sync_jobs()
        last_printer_state["state"] = state
    except Exception as e:
        logger.error(f"Printer check Fehler: {e}")

async def recalculate_all_costs():
    """Berechnet nur Filamentkosten neu. Historische Stromkosten bleiben unveraendert."""
    logger.info("Berechne Filamentkosten neu (Stromkosten unveraendert)...")
    jobs, total = await db.get_all_jobs(limit=99999)
    def_cost = await db.get_setting("default_filament_cost_per_kg")
    for job in jobs:
        cpkg = job.get("filament_cost_per_kg") or def_cost
        fg = job.get("filament_used_g", 0)
        fc = calculator.calc_filament_cost(fg, cpkg)
        ec = job.get("electricity_cost") or 0  # Historische Stromkosten beibehalten
        tc = calculator.calc_total_cost(fc, ec)
        await db.update_job_filament(job["id"], fg, fc, ec, tc)
    logger.info(f"{len(jobs)} Jobs neu berechnet (nur Filamentkosten)")

@asynccontextmanager
async def lifespan(a):
    await db.initialize()
    logger.info("Initiale Synchronisation...")
    await sync_jobs()
    scheduler.add_job(sync_jobs, "interval", minutes=5, id="sync_jobs")
    scheduler.add_job(check_printer_state, "interval", seconds=Config.POLL_INTERVAL, id="check_printer")
    scheduler.start()
    logger.info("Scheduler gestartet")
    yield
    scheduler.shutdown()

app = FastAPI(title="3D Print Cost Tracker", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.get("/api/status")
async def get_status():
    m = await moonraker.is_connected()
    s = await spoolman.is_connected()
    ls = await db.get_last_sync()
    return {"moonraker_connected": m, "spoolman_connected": s,
            "moonraker_url": Config.MOONRAKER_URL, "spoolman_url": Config.SPOOLMAN_URL,
            "last_sync": ls}

@app.post("/api/sync")
async def trigger_sync():
    await sync_jobs()
    return {"message": "Sync abgeschlossen"}

@app.get("/api/jobs")
async def get_jobs(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                   status: str = Query("all"), sort_by: str = Query("end_time"),
                   sort_order: str = Query("desc"),
                   filament_type: str = Query("all")):
    jobs, total = await db.get_all_jobs(limit, offset, status, sort_by, sort_order, filament_type)
    return {"jobs": jobs, "total": total, "limit": limit, "offset": offset}

@app.get("/api/filament-types")
async def get_filament_types():
    return await db.get_distinct_filament_types()

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: int):
    job = await db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    return job

@app.patch("/api/jobs/{job_id}/filament")
async def update_job_filament(job_id: int, payload: dict):
    job = await db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    filament_g = float(payload.get("filament_used_g", job["filament_used_g"] or 0))
    cost_per_kg = job.get("filament_cost_per_kg") or await db.get_setting("default_filament_cost_per_kg")
    f_cost = calculator.calc_filament_cost(filament_g, cost_per_kg)
    e_cost = job.get("electricity_cost") or 0  # Historische Stromkosten beibehalten
    t_cost = calculator.calc_total_cost(f_cost, e_cost)
    await db.update_job_filament(job_id, filament_g, f_cost, e_cost, t_cost)
    return {"message": "Filament aktualisiert", "filament_used_g": filament_g, "filament_cost": f_cost, "total_cost": t_cost}

@app.patch("/api/jobs/{job_id}/spool")
async def update_job_spool(job_id: int, payload: dict):
    job = await db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    spool_id = payload.get("spool_id")
    spool = await spoolman.get_spool_by_id(spool_id) if spool_id else None
    fi = await spoolman.get_filament_info(spool)
    f_cost = calculator.calc_filament_cost(job["filament_used_g"], fi["cost_per_kg"])
    e_cost = job.get("electricity_cost") or 0  # Historische Stromkosten beibehalten
    t_cost = calculator.calc_total_cost(f_cost, e_cost)
    await db.update_job_spool(
        job_id,
        fi["spool_id"], fi["spool_name"], fi["filament_type"], fi["filament_color"],
        fi["cost_per_kg"], f_cost, e_cost, t_cost
    )
    return {"message": "Spule aktualisiert"}

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int):
    job = await db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    await db.delete_job(job_id)
    return {"message": "Geloescht"}

@app.get("/api/statistics")
async def get_statistics():
    return await db.get_statistics()

@app.get("/api/spools")
async def get_spools():
    """Spoolman Rohdaten durchreichen - Frontend erwartet Original-Format"""
    spools = await spoolman.get_all_spools()
    return spools

@app.get("/api/settings")
async def get_settings():
    return await db.get_all_settings()

@app.post("/api/settings")
async def update_settings(settings: dict):
    for key, value in settings.items():
        if isinstance(value, (int, float)):
            await db.update_setting(key, float(value))
    return {"message": "Gespeichert"}

@app.post("/api/recalculate")
async def recalculate():
    await recalculate_all_costs()
    return {"message": "Neu berechnet"}

# ── Locations / CFS-Slots ───────────────────────────────────────
@app.get("/api/cfs-slots")
async def get_cfs_slots():
    """Locations aus Spoolman laden + Spulen pro Location gruppieren"""
    locations, spools_raw = await asyncio.gather(
        spoolman.get_all_locations(),
        spoolman.get_all_spools()
    )

    def spool_info(s):
        f = s.get("filament", {}) or {}
        v = (f.get("vendor") or {}).get("name", "")
        name = f"{v} {f.get('name','')}".strip() or f"Spool #{s['id']}"
        color = f.get("color_hex", "") or ""
        if color and not color.startswith("#"): color = f"#{color}"
        remaining = s.get("remaining_weight")
        return {
            "id": s["id"],
            "name": name,
            "color": color or "#888",
            "material": f.get("material", ""),
            "remaining_weight": round(remaining, 0) if remaining is not None else None,
            "location": s.get("location") or ""
        }

    all_spools = [spool_info(s) for s in spools_raw]

    # Locations aus Spoolman als Slots aufbauen
    # Spoolman gibt Locations als Liste von Strings zurueck
    if locations and isinstance(locations[0], str):
        loc_names = sorted(locations)
    elif locations:
        loc_names = sorted([loc["name"] for loc in locations])
    else:
        loc_names = []
    # Fallback falls keine Locations in Spoolman: eigene DB-Slots nutzen
    if not loc_names:
        db_slots = await db.get_cfs_slots()
        loc_names = [sl["slot_label"] for sl in db_slots]

    slots = []
    for loc in loc_names:
        spools_here = [sp for sp in all_spools if sp["location"] == loc]
        slots.append({"slot_key": loc, "slot_label": loc, "spools": spools_here})

    # Spulen ohne Location in "Lager (unbekannt)"
    assigned = {sp["id"] for slot in slots for sp in slot["spools"]}
    unassigned = [sp for sp in all_spools if sp["id"] not in assigned]
    if unassigned:
        slots.append({"slot_key": "__unassigned__", "slot_label": "Ohne Ort", "spools": unassigned})

    return {"slots": slots, "spools": all_spools}

@app.post("/api/cfs-slots")
async def update_cfs_slots(payload: dict):
    """Fallback: manuelle Slot-Zuweisung in eigener DB (wenn keine Spoolman-Locations)"""
    for item in payload.get("slots", []):
        spool_id = item.get("spool_id")
        await db.update_cfs_slot(
            item["slot_key"],
            int(spool_id) if spool_id else None
        )
    return {"message": "Slots gespeichert"}
# ─────────────────────────────────────────────────────────────

@app.get("/api/debug/job-sync-check")
async def debug_job_sync_check():
    """Vergleicht Moonraker Job-History mit der lokalen DB"""
    moonraker_jobs = await moonraker.get_all_job_history()
    moonraker_ids = {str(j.get("job_id")) for j in moonraker_jobs}

    # Alle IDs aus der DB holen
    db_ids = await db.get_all_moonraker_job_ids()

    missing_in_db = moonraker_ids - db_ids
    extra_in_db = db_ids - moonraker_ids

    # Details der fehlenden Jobs
    missing_details = [
        {"job_id": j.get("job_id"), "filename": j.get("filename"), "status": j.get("status"),
         "end_time": j.get("end_time")}
        for j in moonraker_jobs if str(j.get("job_id")) in missing_in_db
    ]

    return {
        "moonraker_total": len(moonraker_ids),
        "db_total": len(db_ids),
        "missing_in_db_count": len(missing_in_db),
        "extra_in_db_count": len(extra_in_db),
        "missing_in_db": sorted(missing_details, key=lambda x: x.get("end_time") or 0),
        "extra_in_db": sorted(extra_in_db),
        "in_sync": len(missing_in_db) == 0
    }

@app.get("/api/debug/spoolman")
async def debug_spoolman():
    locations = await spoolman.get_all_locations()
    spools = await spoolman.get_all_spools()
    return {
        "locations": locations,
        "locations_count": len(locations),
        "spools_count": len(spools),
        "spool_sample": spools[0] if spools else None
    }

@app.get("/api/debug/printer-objects")
async def debug_printer_objects():
    """Alle verfuegbaren Klipper Printer-Objects abfragen (Diagnose fuer CFS/Filament-Hub)"""
    return await moonraker.get_all_printer_objects()

@app.get("/api/debug/job-sample")
async def debug_job_sample():
    """Letzten Job mit allen Feldern zurueckgeben (Diagnose fuer auxiliary_data / CFS-Slot)"""
    result = await moonraker.get_job_history(limit=1)
    jobs = result.get("jobs", [])
    return jobs[0] if jobs else {"error": "Keine Jobs gefunden"}

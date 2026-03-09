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

# ── Hilfsfunktion: lokale Spule als filament_info-Dict aufbereiten ────────────
async def local_spool_to_fi(spool_row: dict) -> dict:
    price_per_spool = spool_row.get("price_per_spool") or 0
    weight = spool_row.get("weight_per_spool") or 1000
    cost_per_kg = (price_per_spool / weight * 1000) if (price_per_spool > 0 and weight > 0) else Config.DEFAULT_FILAMENT_COST_PER_KG
    color = spool_row.get("color_hex") or ""
    if color and not color.startswith("#"):
        color = f"#{color}"
    label = spool_row.get("label") or ""
    vendor = spool_row.get("vendor_name") or ""
    fname = spool_row.get("filament_name") or ""
    spool_name = label or f"{vendor} {fname}".strip() or f"Spule #{spool_row.get('id','?')}"
    return {
        "spool_id": spool_row.get("id"),
        "spool_name": spool_name,
        "filament_type": spool_row.get("material") or "Unbekannt",
        "filament_color": color or None,
        "cost_per_kg": cost_per_kg,
        "density": spool_row.get("density") or 1.24,
        "diameter": spool_row.get("diameter") or 1.75,
    }


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

    # Spule: erst Spoolman, dann lokale DB
    spool = await spoolman.find_spool_for_job(job)
    if spool:
        fi = await spoolman.get_filament_info(spool)
    else:
        # Lokale aktive Spule als Fallback
        local_spools = await db.get_all_local_spools()
        active = next((s for s in local_spools if s.get("is_active") and not s.get("is_empty")), None)
        fi = await local_spool_to_fi(active) if active else {
            "spool_id": None, "spool_name": "Unbekannt", "filament_type": "Unbekannt",
            "filament_color": None, "cost_per_kg": Config.DEFAULT_FILAMENT_COST_PER_KG,
            "density": 1.24, "diameter": 1.75,
        }

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
    logger.info("Berechne Filamentkosten neu (Stromkosten unveraendert)...")
    jobs, total = await db.get_all_jobs(limit=99999)
    def_cost = await db.get_setting("default_filament_cost_per_kg")
    for job in jobs:
        cpkg = job.get("filament_cost_per_kg") or def_cost
        fg = job.get("filament_used_g", 0)
        fc = calculator.calc_filament_cost(fg, cpkg)
        ec = job.get("electricity_cost") or 0
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


# ── Health / Status ───────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/status")
async def get_status():
    m = await moonraker.is_connected()
    s = await spoolman.is_connected()
    ls = await db.get_last_sync()
    jobs, total = await db.get_all_jobs(limit=1)
    _, total_count = await db.get_all_jobs(limit=99999)
    return {
        "moonraker_connected": m,
        "spoolman_connected": s,
        "moonraker_url": Config.MOONRAKER_URL,
        "spoolman_url": Config.SPOOLMAN_URL,
        "last_sync": ls,
        "total_jobs_in_db": total_count,
    }


@app.post("/api/sync")
async def trigger_sync():
    await sync_jobs()
    return {"message": "Sync abgeschlossen"}


# ── Print Jobs ────────────────────────────────────────────────────────────────
@app.get("/api/jobs")
async def get_jobs(
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    status: str = Query("all"), sort_by: str = Query("end_time"),
    sort_order: str = Query("desc"), filament_type: str = Query("all")
):
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
    e_cost = job.get("electricity_cost") or 0
    t_cost = calculator.calc_total_cost(f_cost, e_cost)
    await db.update_job_filament(job_id, filament_g, f_cost, e_cost, t_cost)
    return {"message": "Filament aktualisiert", "filament_used_g": filament_g,
            "filament_cost": f_cost, "total_cost": t_cost}


@app.patch("/api/jobs/{job_id}/spool")
async def update_job_spool(job_id: int, payload: dict):
    job = await db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    spool_id = payload.get("spool_id")
    spool_source = payload.get("spool_source", "auto")  # "spoolman" | "local" | "auto"

    fi = None
    # 1. Lokale Spule bevorzugen wenn spool_source == "local"
    if spool_source == "local" and spool_id:
        local = await db.get_local_spool_by_id(spool_id)
        if local:
            fi = await local_spool_to_fi(local)
    # 2. Spoolman
    if fi is None and spool_id:
        spool = await spoolman.get_spool_by_id(spool_id)
        if spool:
            fi = await spoolman.get_filament_info(spool)
    # 3. Lokale Spule als Fallback
    if fi is None and spool_id:
        local = await db.get_local_spool_by_id(spool_id)
        if local:
            fi = await local_spool_to_fi(local)
    # 4. Kein Spool
    if fi is None:
        fi = {"spool_id": None, "spool_name": "Unbekannt", "filament_type": "Unbekannt",
              "filament_color": None, "cost_per_kg": Config.DEFAULT_FILAMENT_COST_PER_KG,
              "density": 1.24, "diameter": 1.75}

    filament_g = job["filament_used_g"] or 0
    f_cost = calculator.calc_filament_cost(filament_g, fi["cost_per_kg"])
    e_cost = job.get("electricity_cost") or 0
    t_cost = calculator.calc_total_cost(f_cost, e_cost)
    await db.update_job_spool(
        job_id, fi["spool_id"], fi["spool_name"], fi["filament_type"],
        fi["filament_color"], fi["cost_per_kg"], f_cost, e_cost, t_cost
    )
    return {"message": "Spule aktualisiert"}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int):
    job = await db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    await db.delete_job(job_id)
    return {"message": "Geloescht"}


# ── Statistics ────────────────────────────────────────────────────────────────
@app.get("/api/statistics")
async def get_statistics():
    return await db.get_statistics()


# ── Settings ──────────────────────────────────────────────────────────────────
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


# ── Spoolman (optional / Legacy) ──────────────────────────────────────────────
@app.get("/api/spools")
async def get_spools():
    """Spoolman Rohdaten – wird nur noch genutzt wenn Spoolman verbunden ist."""
    spools = await spoolman.get_all_spools()
    return spools


@app.get("/api/cfs-slots")
async def get_cfs_slots():
    locations, spools_raw = await asyncio.gather(
        spoolman.get_all_locations(),
        spoolman.get_all_spools()
    )

    def spool_info(s):
        f = s.get("filament", {}) or {}
        v = (f.get("vendor") or {}).get("name", "")
        name = f"{v} {f.get('name','')}".strip() or f"Spool #{s['id']}"
        color = f.get("color_hex", "") or ""
        if color and not color.startswith("#"):
            color = f"#{color}"
        remaining = s.get("remaining_weight")
        return {
            "id": s["id"], "name": name, "color": color or "#888",
            "material": f.get("material", ""),
            "remaining_weight": round(remaining, 0) if remaining is not None else None,
            "location": s.get("location") or ""
        }

    all_spools = [spool_info(s) for s in spools_raw]
    if locations and isinstance(locations[0], str):
        loc_names = sorted(locations)
    elif locations:
        loc_names = sorted([loc["name"] for loc in locations])
    else:
        loc_names = []
    if not loc_names:
        db_slots = await db.get_cfs_slots()
        loc_names = [sl["slot_label"] for sl in db_slots]

    slots = []
    for loc in loc_names:
        spools_here = [sp for sp in all_spools if sp["location"] == loc]
        slots.append({"slot_key": loc, "slot_label": loc, "spools": spools_here})

    assigned = {sp["id"] for slot in slots for sp in slot["spools"]}
    unassigned = [sp for sp in all_spools if sp["id"] not in assigned]
    if unassigned:
        slots.append({"slot_key": "__unassigned__", "slot_label": "Ohne Ort", "spools": unassigned})

    return {"slots": slots, "spools": all_spools}


@app.post("/api/cfs-slots")
async def update_cfs_slots(payload: dict):
    for item in payload.get("slots", []):
        spool_id = item.get("spool_id")
        await db.update_cfs_slot(item["slot_key"], int(spool_id) if spool_id else None)
    return {"message": "Slots gespeichert"}


# ── Eigene Spulenverwaltung: Vendors ──────────────────────────────────────────
@app.get("/api/local/vendors")
async def list_vendors():
    return await db.get_all_vendors()


@app.post("/api/local/vendors")
async def create_vendor(payload: dict):
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(400, "Name ist erforderlich")
    new_id = await db.create_vendor(name, payload.get("website"), payload.get("notes"))
    return {"id": new_id, "message": "Hersteller angelegt"}


@app.put("/api/local/vendors/{vendor_id}")
async def update_vendor(vendor_id: int, payload: dict):
    existing = await db.get_vendor_by_id(vendor_id)
    if not existing:
        raise HTTPException(404, "Hersteller nicht gefunden")
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(400, "Name ist erforderlich")
    await db.update_vendor(vendor_id, name, payload.get("website"), payload.get("notes"))
    return {"message": "Hersteller aktualisiert"}


@app.delete("/api/local/vendors/{vendor_id}")
async def delete_vendor(vendor_id: int):
    existing = await db.get_vendor_by_id(vendor_id)
    if not existing:
        raise HTTPException(404, "Hersteller nicht gefunden")
    await db.delete_vendor(vendor_id)
    return {"message": "Hersteller geloescht"}


# ── Eigene Spulenverwaltung: Filaments ────────────────────────────────────────
@app.get("/api/local/filaments")
async def list_filaments():
    return await db.get_all_filaments()


@app.post("/api/local/filaments")
async def create_filament(payload: dict):
    if not payload.get("name") or not payload.get("material"):
        raise HTTPException(400, "Name und Material sind erforderlich")
    new_id = await db.create_filament(payload)
    return {"id": new_id, "message": "Filament angelegt"}


@app.put("/api/local/filaments/{filament_id}")
async def update_filament(filament_id: int, payload: dict):
    existing = await db.get_filament_by_id(filament_id)
    if not existing:
        raise HTTPException(404, "Filament nicht gefunden")
    if not payload.get("name") or not payload.get("material"):
        raise HTTPException(400, "Name und Material sind erforderlich")
    await db.update_filament(filament_id, payload)
    return {"message": "Filament aktualisiert"}


@app.delete("/api/local/filaments/{filament_id}")
async def delete_filament(filament_id: int):
    existing = await db.get_filament_by_id(filament_id)
    if not existing:
        raise HTTPException(404, "Filament nicht gefunden")
    await db.delete_filament(filament_id)
    return {"message": "Filament geloescht"}


# ── Eigene Spulenverwaltung: Spools ───────────────────────────────────────────
@app.get("/api/local/spools")
async def list_local_spools():
    return await db.get_all_local_spools()


@app.post("/api/local/spools")
async def create_local_spool(payload: dict):
    new_id = await db.create_local_spool(payload)
    return {"id": new_id, "message": "Spule angelegt"}


@app.put("/api/local/spools/{spool_id}")
async def update_local_spool(spool_id: int, payload: dict):
    existing = await db.get_local_spool_by_id(spool_id)
    if not existing:
        raise HTTPException(404, "Spule nicht gefunden")
    await db.update_local_spool(spool_id, payload)
    return {"message": "Spule aktualisiert"}


@app.delete("/api/local/spools/{spool_id}")
async def delete_local_spool(spool_id: int):
    existing = await db.get_local_spool_by_id(spool_id)
    if not existing:
        raise HTTPException(404, "Spule nicht gefunden")
    await db.delete_local_spool(spool_id)
    return {"message": "Spule geloescht"}


@app.patch("/api/local/spools/{spool_id}/deduct")
async def deduct_spool(spool_id: int, payload: dict):
    """Manuell Verbrauch von einer Spule abziehen."""
    existing = await db.get_local_spool_by_id(spool_id)
    if not existing:
        raise HTTPException(404, "Spule nicht gefunden")
    used_g = float(payload.get("used_g", 0))
    if used_g <= 0:
        raise HTTPException(400, "used_g muss > 0 sein")
    await db.deduct_filament_from_spool(spool_id, used_g)
    return {"message": f"{used_g}g abgezogen"}


@app.get("/api/local/spools/locations")
async def get_spool_locations():
    return await db.get_local_spool_locations()


# ── Debug ─────────────────────────────────────────────────────────────────────
@app.get("/api/debug/job-sync-check")
async def debug_job_sync_check():
    moonraker_jobs = await moonraker.get_all_job_history()
    moonraker_ids = {str(j.get("job_id")) for j in moonraker_jobs}
    db_ids = await db.get_all_moonraker_job_ids()
    missing_in_db = moonraker_ids - db_ids
    extra_in_db = db_ids - moonraker_ids
    missing_details = [
        {"job_id": j.get("job_id"), "filename": j.get("filename"),
         "status": j.get("status"), "end_time": j.get("end_time")}
        for j in moonraker_jobs if str(j.get("job_id")) in missing_in_db
    ]
    return {
        "moonraker_total": len(moonraker_ids), "db_total": len(db_ids),
        "missing_in_db_count": len(missing_in_db), "extra_in_db_count": len(extra_in_db),
        "missing_in_db": sorted(missing_details, key=lambda x: x.get("end_time") or 0),
        "extra_in_db": sorted(extra_in_db), "in_sync": len(missing_in_db) == 0
    }


@app.get("/api/debug/spoolman")
async def debug_spoolman():
    locations = await spoolman.get_all_locations()
    spools = await spoolman.get_all_spools()
    return {
        "locations": locations, "locations_count": len(locations),
        "spools_count": len(spools), "spool_sample": spools[0] if spools else None
    }


@app.get("/api/debug/printer-objects")
async def debug_printer_objects():
    return await moonraker.get_all_printer_objects()


@app.get("/api/debug/job-sample")
async def debug_job_sample():
    result = await moonraker.get_job_history(limit=1)
    jobs = result.get("jobs", [])
    return jobs[0] if jobs else {"error": "Keine Jobs gefunden"}

import aiohttp
import logging
from config import Config

logger = logging.getLogger(__name__)

class MoonrakerClient:
    def __init__(self):
        self.base_url = Config.MOONRAKER_URL

    async def get_job_history(self, limit=50, start=0, order="desc"):
        url = f"{self.base_url}/server/history/list"
        params = {"limit": limit, "start": start, "order": order}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("result", {})
                    logger.error(f"Moonraker HTTP {resp.status}")
                    return {}
        except Exception as e:
            logger.error(f"Moonraker Fehler: {e}")
            return {}

    async def get_all_job_history(self):
        all_jobs = []
        start = 0
        limit = 50
        while True:
            result = await self.get_job_history(limit=limit, start=start)
            jobs = result.get("jobs", [])
            if not jobs:
                break
            all_jobs.extend(jobs)
            total = result.get("count", 0)
            start += limit
            if start >= total:
                break
        logger.info(f"{len(all_jobs)} Jobs aus Moonraker geladen")
        return all_jobs

    async def get_printer_status(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/printer/objects/query",
                    params={"print_stats": "", "virtual_sdcard": ""},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("result", {}).get("status", {})
                    return {}
        except Exception as e:
            logger.error(f"Status Fehler: {e}")
            return {}

    async def get_metadata(self, filename):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/server/files/metadata",
                    params={"filename": filename},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("result", {})
                    return {}
        except Exception as e:
            logger.error(f"Metadata Fehler: {e}")
            return {}

    async def get_all_printer_objects(self):
        """Alle verfuegbaren Printer-Objects auflisten und CFS/Filament-relevante Details abrufen"""
        try:
            async with aiohttp.ClientSession() as session:
                # Schritt 1: alle verfuegbaren Object-Namen holen
                async with session.get(
                    f"{self.base_url}/printer/objects/list",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        return {"error": f"HTTP {resp.status}"}
                    data = await resp.json()
                    all_objects = data.get("result", {}).get("objects", [])

                # Schritt 2: interessante Objekte filtern
                keywords = ["cfs", "filament", "hub", "mmu", "ams", "spool", "multi", "creality", "slot"]
                relevant = [o for o in all_objects if any(k in o.lower() for k in keywords)]

                # Schritt 3: alle relevanten Objekte abfragen
                result = {
                    "all_objects": all_objects,
                    "relevant_objects": relevant,
                    "relevant_details": {}
                }

                if relevant:
                    params = {obj: "" for obj in relevant}
                    async with session.get(
                        f"{self.base_url}/printer/objects/query",
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp2:
                        if resp2.status == 200:
                            d2 = await resp2.json()
                            result["relevant_details"] = d2.get("result", {}).get("status", {})

                # Schritt 4: auch print_stats und toolhead abfragen fuer Kontext
                async with session.get(
                    f"{self.base_url}/printer/objects/query",
                    params={"print_stats": "", "toolhead": "", "extruder": ""},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp3:
                    if resp3.status == 200:
                        d3 = await resp3.json()
                        result["print_stats"] = d3.get("result", {}).get("status", {})

                # Schritt 5: letzten Job aus History mit allen Feldern
                async with session.get(
                    f"{self.base_url}/server/history/list",
                    params={"limit": 1},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp4:
                    if resp4.status == 200:
                        d4 = await resp4.json()
                        jobs = d4.get("result", {}).get("jobs", [])
                        result["last_job_raw"] = jobs[0] if jobs else None

                return result
        except Exception as e:
            logger.error(f"Printer objects Fehler: {e}")
            return {"error": str(e)}

    async def is_connected(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/server/info",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    return resp.status == 200
        except:
            return False

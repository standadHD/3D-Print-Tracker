import aiohttp
import logging
from config import Config

logger = logging.getLogger(__name__)

class SpoolmanClient:
    def __init__(self):
        self.base_url = Config.SPOOLMAN_URL

    async def get_all_spools(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/v1/spool",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return []
        except Exception as e:
            logger.error(f"Spoolman Fehler: {e}")
            return []

    async def get_spool_by_id(self, spool_id):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/v1/spool/{spool_id}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return {}
        except Exception as e:
            logger.error(f"Spool {spool_id} Fehler: {e}")
            return {}

    async def get_filament_info(self, spool):
        if not spool:
            return {
                "spool_id": None,
                "spool_name": "Unbekannt",
                "filament_type": "Unbekannt",
                "filament_color": None,
                "cost_per_kg": Config.DEFAULT_FILAMENT_COST_PER_KG,
                "density": 1.24,
                "diameter": 1.75,
            }
        filament = spool.get("filament", {})
        vendor = filament.get("vendor", {}) or {}
        net_weight = filament.get("weight", 1000) or 1000
        price = filament.get("price", 0) or 0
        if net_weight > 0 and price > 0:
            cost_per_kg = price / net_weight * 1000
        else:
            cost_per_kg = Config.DEFAULT_FILAMENT_COST_PER_KG
        vendor_name = vendor.get("name", "")
        filament_name = filament.get("name", "")
        spool_name = f"{vendor_name} {filament_name}".strip() or f"Spool #{spool.get('id','?')}"
        color_hex = filament.get("color_hex", "")
        if color_hex and not color_hex.startswith("#"):
            color_hex = f"#{color_hex}"
        return {
            "spool_id": spool.get("id"),
            "spool_name": spool_name,
            "filament_type": filament.get("material", "Unbekannt"),
            "filament_color": color_hex or None,
            "cost_per_kg": cost_per_kg,
            "density": filament.get("density", 1.24) or 1.24,
            "diameter": filament.get("diameter", 1.75) or 1.75,
        }

    async def find_spool_for_job(self, job):
        spool_id = None
        # Check auxiliary_data (Moonraker + Spoolman integration)
        for aux in job.get("auxiliary_data", []):
            if aux.get("provider") == "spoolman" and aux.get("name") == "spool_ids":
                ids = aux.get("value", [])
                if ids:
                    spool_id = ids[0]
                    break
        # Fallback: metadata
        if not spool_id:
            metadata = job.get("metadata", {})
            spool_id = metadata.get("spool_id")
        if spool_id:
            spool = await self.get_spool_by_id(spool_id)
            if spool:
                return spool
        # Last resort: active spool
        spools = await self.get_all_spools()
        for s in spools:
            if s.get("is_active", False):
                return s
        return None

    async def is_connected(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/v1/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    return resp.status == 200
        except:
            return False
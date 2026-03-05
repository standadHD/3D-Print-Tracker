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

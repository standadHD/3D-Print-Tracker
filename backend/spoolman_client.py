"""
SpoolmanClient – DEAKTIVIERT
Spoolman-Integration ist deaktiviert. Die App nutzt jetzt die eigene Spulenverwaltung.
Dieser Stub stellt sicher, dass bestehende Aufrufe keine Fehler werfen.
"""
import logging

logger = logging.getLogger(__name__)


class SpoolmanClient:
    def __init__(self):
        logger.info("SpoolmanClient: Spoolman-Integration ist deaktiviert – eigene Spulenverwaltung aktiv.")

    async def get_all_spools(self):
        return []

    async def get_all_locations(self):
        return []

    async def get_spool_by_id(self, spool_id):
        return {}

    async def get_filament_info(self, spool):
        from config import Config
        return {
            "spool_id": None,
            "spool_name": "Unbekannt",
            "filament_type": "Unbekannt",
            "filament_color": None,
            "cost_per_kg": Config.DEFAULT_FILAMENT_COST_PER_KG,
            "density": 1.24,
            "diameter": 1.75,
        }

    async def find_spool_for_job(self, job):
        return None

    async def is_connected(self):
        return False

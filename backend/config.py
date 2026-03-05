import os

class Config:
    MOONRAKER_URL = os.getenv("MOONRAKER_URL", "http://192.168.1.100:7125")
    SPOOLMAN_URL = os.getenv("SPOOLMAN_URL", "http://192.168.1.100:7912")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "/app/data/print_tracker.db")
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
    ELECTRICITY_COST_PER_KWH = float(os.getenv("ELECTRICITY_COST_PER_KWH", "0.30"))
    PRINTER_POWER_WATTS = float(os.getenv("PRINTER_POWER_WATTS", "200"))
    DEFAULT_FILAMENT_COST_PER_KG = float(os.getenv("DEFAULT_FILAMENT_COST_PER_KG", "25.00"))

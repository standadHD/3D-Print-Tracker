import math
import logging

logger = logging.getLogger(__name__)

class CostCalculator:
    @staticmethod
    def mm_to_grams(filament_mm, diameter=1.75, density=1.24):
        if not filament_mm or filament_mm <= 0:
            return 0.0
        radius_cm = (diameter / 2.0) / 10.0
        length_cm = filament_mm / 10.0
        volume_cm3 = math.pi * radius_cm * radius_cm * length_cm
        weight_g = volume_cm3 * density
        return round(weight_g, 2)

    @staticmethod
    def calc_filament_cost(weight_g, cost_per_kg):
        if not weight_g or weight_g <= 0 or not cost_per_kg:
            return 0.0
        return round((weight_g / 1000.0) * cost_per_kg, 4)

    @staticmethod
    def calc_electricity_cost(print_duration_s, power_watts, cost_per_kwh):
        if not print_duration_s or print_duration_s <= 0:
            return 0.0
        hours = print_duration_s / 3600.0
        kwh = (power_watts / 1000.0) * hours
        return round(kwh * cost_per_kwh, 4)

    @staticmethod
    def calc_total_cost(filament_cost, electricity_cost):
        return round((filament_cost or 0) + (electricity_cost or 0), 4)

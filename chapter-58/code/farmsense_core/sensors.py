"""What a sensor reading is allowed to look like. Hardware lies: cables get loose, batteries die, firmware has bugs.
Everything that enters the system is checked against physical reality first."""
import math
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple


@dataclass(frozen=True)
class SensorType:
    key: str
    unit: str
    minimum: float          # physically plausible range: outside it the reading is a sensor fault, not a measurement
    maximum: float
    decimals: int


SENSOR_TYPES: Dict[str, SensorType] = {t.key: t for t in [
    SensorType("temperature", "C", -40.0, 60.0, 1),
    SensorType("humidity", "%", 0.0, 100.0, 1),
    SensorType("soil_moisture", "%", 0.0, 100.0, 1),
    SensorType("co2", "ppm", 250.0, 10000.0, 0),
    SensorType("ammonia", "ppm", 0.0, 200.0, 1),
    SensorType("water_level", "cm", 0.0, 500.0, 1),
    SensorType("feed_level", "kg", 0.0, 100000.0, 1),
]}

# (sensor type, unit sent by the device) -> function that converts to the canonical unit
_CONVERSIONS: Dict[Tuple[str, str], Callable[[float], float]] = {
    ("temperature", "F"): lambda f: (f - 32.0) * 5.0 / 9.0,
    ("temperature", "K"): lambda k: k - 273.15,
    ("water_level", "m"): lambda m: m * 100.0,
    ("water_level", "in"): lambda i: i * 2.54,
    ("feed_level", "lb"): lambda lb: lb * 0.45359237,
}


def normalize_value(sensor_type: str, value, unit: Optional[str] = None) -> float:
    """Returns the value in the canonical unit, rounded sensibly. Raises ValueError with a short machine-readable reason."""
    st = SENSOR_TYPES.get(sensor_type)
    if st is None:
        raise ValueError("unknown_sensor_type")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid_value")
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        raise ValueError("invalid_value")
    if unit and unit != st.unit:
        convert = _CONVERSIONS.get((sensor_type, unit))
        if convert is None:
            raise ValueError("unknown_unit")
        value = convert(value)
    if not (st.minimum <= value <= st.maximum):
        raise ValueError("out_of_range")
    return round(value, st.decimals)

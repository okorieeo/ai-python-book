"""Back-of-the-envelope storage planning for time-series data. Do this BEFORE you choose a database."""


def estimate(sensors: int, interval_s: int, bytes_per_row: int = 72, index_factor: float = 1.0) -> dict:
    """bytes_per_row: a PostgreSQL row with timestamp, sensor id, value and the tuple header is around 50 to 80 bytes.
    index_factor: extra space for indexes as a share of the table (1.0 = indexes as big as the table)."""
    per_day = sensors * (86400 // interval_s)
    total_per_year = per_day * 365 * bytes_per_row * (1 + index_factor)
    return {"rows_per_day": per_day, "rows_per_year": per_day * 365,
            "gb_per_year": round(total_per_year / 1024 ** 3, 1),
            "writes_per_second": round(sensors / interval_s, 2)}

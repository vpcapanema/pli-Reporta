"""Extração de EXIF e GPS via Pillow, sem dependências extras."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from PIL import ExifTags, Image

_GPS_TAG_ID = next((k for k, v in ExifTags.TAGS.items() if v == "GPSInfo"), 34853)
_GPS_NAMES = {v: k for k, v in ExifTags.GPSTAGS.items()}


def _to_deg(value: Any) -> float | None:
    """EXIF GPS guarda como ((deg_num, deg_den), (min_num, min_den), (sec_num, sec_den))."""
    try:
        d, m, s = value
        d = float(d[0]) / float(d[1]) if isinstance(d, tuple) else float(d)
        m = float(m[0]) / float(m[1]) if isinstance(m, tuple) else float(m)
        s = float(s[0]) / float(s[1]) if isinstance(s, tuple) else float(s)
        return d + m / 60.0 + s / 3600.0
    except Exception:
        return None


def parse_exif(image_bytes: bytes) -> dict:
    """Devolve dict com latitude, longitude, datetime, software (se houver)."""
    out: dict = {}
    try:
        img = Image.open(BytesIO(image_bytes))
        exif = img.getexif()
        if not exif:
            return out
        # Software (indício de edição)
        for tag_id, val in exif.items():
            name = ExifTags.TAGS.get(tag_id, str(tag_id))
            if name == "Software" and isinstance(val, str):
                out["software"] = val.strip()
            elif name == "DateTimeOriginal" and isinstance(val, str):
                out["datetime"] = val.strip()
            elif name == "DateTime" and isinstance(val, str):
                out.setdefault("datetime", val.strip())

        gps = exif.get_ifd(_GPS_TAG_ID) or {}
        if gps:
            named = {ExifTags.GPSTAGS.get(k, str(k)): v for k, v in gps.items()}
            lat = _to_deg(named.get("GPSLatitude"))
            lon = _to_deg(named.get("GPSLongitude"))
            if lat is not None and named.get("GPSLatitudeRef") in ("S", b"S"):
                lat = -lat
            if lon is not None and named.get("GPSLongitudeRef") in ("W", b"W"):
                lon = -lon
            if lat is not None and lon is not None:
                out["lat"] = lat
                out["lon"] = lon
    except Exception:
        return out
    return out


def parse_exif_datetime(s: str) -> datetime | None:
    """EXIF formato típico: 'YYYY:MM:DD HH:MM:SS'."""
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None

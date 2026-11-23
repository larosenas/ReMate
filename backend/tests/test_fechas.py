"""«Hoy» en hora de España aunque el servidor esté en otra zona horaria."""

from datetime import UTC, date, datetime

from app import fechas


class _RelojFijo(datetime):
    """Un `datetime` cuyo «ahora» es el 13/11/2026 a las 23:30 UTC (00:30 del 14 en España)."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 11, 13, 23, 30, tzinfo=UTC).astimezone(tz)


def test_hoy_es_la_fecha_de_espana_y_no_la_de_utc(monkeypatch):
    monkeypatch.setattr(fechas, "datetime", _RelojFijo)
    assert fechas.hoy() == date(2026, 11, 14)

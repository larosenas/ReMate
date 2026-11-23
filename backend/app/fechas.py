"""«Hoy» en hora de España, sea cual sea la zona horaria del servidor.

Con `date.today()` valdría la del servidor: si está en UTC, entre las 00:00 y las 02:00 de
España «hoy» sería todavía ayer (plazos, entregas y recordatorio). El código de la necesidad
también usa la hora de Madrid (CU-001).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("Europe/Madrid")


def hoy() -> date:
    return datetime.now(ZONA).date()

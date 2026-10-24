"""(Copia independiente de server/logfilter.py: el cliente no importa del servidor.)
Filtro de logging que redacta credenciales en query string (`token=<JWT>` -> `token=***`).

uvicorn registra la URL completa del WebSocket (`/ws?token=...`). El filtro se aplica a los
HANDLERS (que ven todo lo propagado) y a los loggers de uvicorn, tanto en el mensaje como en los args."""
from __future__ import annotations

import logging
import re

_PATRON = re.compile(r"""(?i)(\btoken=)[^\s&"'#<>]+""")


def redactar(texto: str) -> str:
    return _PATRON.sub(r"\1***", texto)


class RedactarTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redactar(record.msg)
            elif record.args:
                record.msg = redactar(str(record.msg))
            args = record.args
            if isinstance(args, tuple):
                record.args = tuple(redactar(a) if isinstance(a, str) else a for a in args)
            elif isinstance(args, dict):
                record.args = {k: redactar(v) if isinstance(v, str) else v for k, v in args.items()}
            if record.exc_text:
                record.exc_text = redactar(record.exc_text)
        except Exception:  # noqa: BLE001 - un filtro de log nunca debe romper el log
            pass
        return True

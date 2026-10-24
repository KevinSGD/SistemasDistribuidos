"""El filtro de logs redacta `token=<JWT>` en mensaje y args, sin tocar el resto de la linea."""
import io
import logging

import pytest

from client.infrastructure.logfilter import RedactarTokenFilter as FiltroCliente
from server.logfilter import RedactarTokenFilter, redactar

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.firma_abc-123"


@pytest.mark.parametrize("entrada,esperado", [
    (f"/ws?token={JWT}", "/ws?token=***"),
    (f'WebSocket /ws?token={JWT} [accepted]', "WebSocket /ws?token=*** [accepted]"),
    (f"/ws?a=1&token={JWT}&b=2", "/ws?a=1&token=***&b=2"),
    (f'"GET /ws?TOKEN={JWT} HTTP/1.1" 403', '"GET /ws?TOKEN=*** HTTP/1.1" 403'),
    (f"ws://127.0.0.1:8000/ws?token={JWT}#x", "ws://127.0.0.1:8000/ws?token=***#x"),
    ("sin credenciales /api/v1/health", "sin credenciales /api/v1/health"),
])
def test_redactar(entrada, esperado):
    assert redactar(entrada) == esperado
    assert JWT not in redactar(entrada)


def _linea(filtro_cls, msg, args=()):
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    h.addFilter(filtro_cls())
    lg = logging.getLogger("prueba.logfilter." + filtro_cls.__module__)
    lg.handlers, lg.propagate = [h], False
    lg.setLevel(logging.INFO)
    lg.info(msg, *args)
    return buf.getvalue()


@pytest.mark.parametrize("cls", [RedactarTokenFilter, FiltroCliente])
def test_filtro_en_mensaje_y_en_args(cls):
    # formato de uvicorn.access: args = (addr, metodo, path_con_query, version, status)
    out = _linea(cls, '%s - "%s %s HTTP/%s" %d', ("1.2.3.4:5", "GET", f"/ws?token={JWT}", "1.1", 403))
    assert JWT not in out and "/ws?token=*** HTTP/1.1" in out and "403" in out
    # uvicorn.error WebSocket: el path va en un arg
    out = _linea(cls, '%s - "WebSocket %s" [accepted]', ("1.2.3.4:5", f"/ws?token={JWT}"))
    assert JWT not in out and "token=***" in out
    # token ya dentro del mensaje (f-string)
    out = _linea(cls, f"conectando a ws://h/ws?token={JWT}")
    assert JWT not in out and "token=***" in out
    # args no str intactos
    assert "7" in _linea(cls, "n=%d", (7,))


def test_filtro_con_args_dict():
    rec = logging.LogRecord("x", logging.INFO, "f", 1, "%(p)s", ({"p": f"/ws?token={JWT}"},), None)
    RedactarTokenFilter().filter(rec)
    assert JWT not in rec.getMessage()


def test_configurar_logs_aplica_filtro_a_handlers_y_uvicorn(tmp_path, monkeypatch):
    from server import main as m
    monkeypatch.setenv("INVENTARIO_LOG_DIR", str(tmp_path))
    raiz = logging.getLogger()
    previos, nivel = raiz.handlers[:], raiz.level
    try:
        ruta = m.configurar_logs()
        for h in raiz.handlers:
            assert any(isinstance(f, RedactarTokenFilter) for f in h.filters)
        logging.getLogger("uvicorn.error").info('%s - "WebSocket %s" [accepted]', "ip", f"/ws?token={JWT}")
        logging.getLogger("uvicorn.access").info('%s - "GET %s"', "ip", f"/ws?token={JWT}")
        for h in raiz.handlers:
            h.flush()
        assert JWT not in ruta.read_text(encoding="utf-8")
        assert "token=***" in ruta.read_text(encoding="utf-8")
    finally:
        for h in raiz.handlers:
            h.close()
        raiz.handlers = previos
        raiz.setLevel(nivel)

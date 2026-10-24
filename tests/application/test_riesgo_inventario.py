import threading
import time
from datetime import timedelta

import pytest

from server.application.errores import RolNoPermitido
from server.application.eventos import EventBus
from server.application.riesgo_service import Scheduler
from server.domain.errors import NoEncontrado
from server.infrastructure.db.engine import sesion
from server.infrastructure.db.repos import DescuentoRepo, ProductoRepo

from .conftest import AHORA


def tipos(eventos):
    return [e["tipo"] for e in eventos]


# -- riesgo ------------------------------------------------------------------
def test_escaneo_retira_vencidos_y_aplica_descuentos(riesgo, factory, crear_producto, eventos):
    v = crear_producto("Viejo", venc=AHORA - timedelta(days=1))
    c = crear_producto("Critico", precio=10.0, venc=AHORA + timedelta(days=2))
    n = crear_producto("Normal", venc=AHORA + timedelta(days=60))
    r = riesgo.escanear()
    assert r["retirados"] == ["Viejo"] and r["cambios"] is True
    assert [d["producto_id"] for d in r["descuentos_aplicados"]] == [c.id]
    with sesion(factory) as s:
        assert ProductoRepo(s).obtener(v.id).activo is False
        assert DescuentoRepo(s).activo_de(c.id).porcentaje == 50.0
        assert DescuentoRepo(s).activo_de(n.id) is None
    assert "productos_retirados" in tipos(eventos) and "descuento_cambiado" in tipos(eventos)
    pr = next(e for e in eventos if e["tipo"] == "productos_retirados")
    assert pr["payload"] == {"nombres": ["Viejo"]}


def test_escaneo_idempotente_no_publica(riesgo, crear_producto, eventos):
    crear_producto(venc=AHORA + timedelta(days=2))
    riesgo.escanear()
    eventos.clear()
    r = riesgo.escanear()
    assert r["cambios"] is False and eventos == []


def test_escaneo_limpia_descuentos_obsoletos(riesgo, factory, config, crear_producto, eventos):
    p = crear_producto(precio=10.0, venc=AHORA + timedelta(days=2))
    riesgo.escanear()
    # Politica sin descuento critico -> el descuento viejo debe desactivarse
    config.actualizar({"descuento_critico": 0}, "admin")
    eventos.clear()
    r = riesgo.escanear()
    assert [d["producto_id"] for d in r["descuentos_removidos"]] == [p.id]
    with sesion(factory) as s:
        assert DescuentoRepo(s).activo_de(p.id) is None
    ev = [e for e in eventos if e["tipo"] == "descuento_cambiado"]
    assert ev[0]["payload"]["porcentaje"] == 0.0


def test_descuento_de_producto_dado_de_baja_se_limpia(riesgo, factory, crear_producto):
    p = crear_producto(venc=AHORA + timedelta(days=2))
    riesgo.escanear()
    with sesion(factory) as s:
        ProductoRepo(s).baja_logica(p.id)   # baja por fuera del servicio
    riesgo.escanear()
    with sesion(factory) as s:
        assert DescuentoRepo(s).listar_activos() == []


def test_dashboard_alertas_y_ofertas(riesgo, crear_producto):
    crear_producto("Crit", venc=AHORA + timedelta(days=1))
    crear_producto("Alto", venc=AHORA + timedelta(days=5))
    crear_producto("Sin stock", stock=0, venc=AHORA + timedelta(days=1))
    crear_producto("Ok", venc=AHORA + timedelta(days=90))
    d = riesgo.resumen_dashboard("admin")
    assert d["total_activos"] == 4
    assert d["conteos"]["critico"] == 2 and d["conteos"]["alto"] == 1
    assert d["atencion"][0]["nivel"] == "critico"
    al = riesgo.alertas_por_severidad("admin")
    assert [i["nombre"] for i in al["alto"]] == ["Alto"]
    of = riesgo.ofertas("comprador")
    assert sorted(i["nombre"] for i in of) == ["Alto", "Crit"]
    assert all(i["precio_final"] < i["precio_original"] and i["motivo"] for i in of)
    with pytest.raises(RolNoPermitido):
        riesgo.resumen_dashboard("comprador")
    with pytest.raises(RolNoPermitido):
        riesgo.escanear_manual("comprador")


def test_ofertas_excluye_vencidos_aun_sin_escaneo(riesgo, crear_producto):
    crear_producto("Vencido", venc=AHORA - timedelta(hours=1))
    assert riesgo.ofertas("admin") == []


# -- scheduler ---------------------------------------------------------------
def esperar(cond, t=3.0):
    fin = time.time() + t
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_scheduler_arranca_y_detiene():
    n = []
    sch = Scheduler(lambda: n.append(1), lambda: 0.02)
    sch.iniciar()
    assert sch.activo and esperar(lambda: len(n) >= 3)
    sch.detener()
    assert not sch.activo
    congelado = len(n)
    time.sleep(0.1)
    assert len(n) == congelado
    sch.iniciar()          # reinicio limpio
    assert esperar(lambda: len(n) > congelado)
    sch.detener()


def test_scheduler_sobrevive_a_excepciones():
    n = []

    def tarea():
        n.append(1)
        if len(n) == 1:
            raise RuntimeError("boom")
    sch = Scheduler(tarea, lambda: 0.02)
    sch.iniciar()
    assert esperar(lambda: len(n) >= 3)
    assert sch.activo and sch.errores == 1
    sch.detener()


def test_scheduler_lee_intervalo_en_cada_ciclo_y_es_daemon():
    lecturas = []
    sch = Scheduler(lambda: None, lambda: lecturas.append(1) or 0.02)
    sch.iniciar()
    assert esperar(lambda: len(lecturas) >= 3)
    assert sch._hilo.daemon
    sch.detener()


def test_scheduler_con_servicio_real(riesgo, config, factory, crear_producto):
    v = crear_producto("Viejo", venc=AHORA - timedelta(days=1))
    sch = Scheduler.para(riesgo, config)
    sch.iniciar()
    try:
        def retirado():
            with sesion(factory) as s:
                return ProductoRepo(s).obtener(v.id).activo is False
        assert esperar(retirado)
    finally:
        sch.detener()


# -- eventos -----------------------------------------------------------------
def test_bus_publica_desde_hilos_y_aisla_fallos():
    bus = EventBus()
    recibidos = []

    def malo(_):
        raise RuntimeError("x")
    bus.suscribir(malo)
    baja = bus.suscribir(recibidos.append)
    ts = [threading.Thread(target=bus.publicar,
                           args=({"tipo": "config_cambiada", "payload": {"claves": [str(i)]}},))
          for i in range(10)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(recibidos) == 10
    baja()
    bus.publicar({"tipo": "sesion_cerrada", "payload": {}})
    assert len(recibidos) == 10
    with pytest.raises(ValueError):
        bus.publicar({"tipo": "inventado", "payload": {}})


def test_bus_con_loop_asyncio():
    import asyncio

    async def main():
        bus = EventBus()
        bus.vincular_loop(asyncio.get_running_loop())
        q: asyncio.Queue = asyncio.Queue()
        hilo_cb = []
        bus.suscribir(lambda e: (hilo_cb.append(threading.current_thread()), q.put_nowait(e)))
        threading.Thread(target=bus.publicar, args=({"tipo": "sesion_cerrada",
                                                      "payload": {"motivo": "x"}},)).start()
        e = await asyncio.wait_for(q.get(), 2)
        assert e["payload"] == {"motivo": "x"}
        assert hilo_cb[0] is threading.main_thread()
    asyncio.run(main())


# -- inventario --------------------------------------------------------------
DATOS = {"nombre": "Arroz", "categoria": "Granos", "precio_base": 3.5, "stock": 10,
         "stock_maximo": 50, "fecha_vencimiento": "2027-01-31T00:00:00"}


def test_crud_inventario_y_eventos(inventario, factory, eventos):
    p = inventario.crear(DATOS, "admin")
    assert p.id and p.fecha_vencimiento.year == 2027
    assert tipos(eventos) == ["stock_actualizado"]
    e = inventario.editar(p.id, {"stock": 7, "precio_base": 4}, "admin")
    assert (e.stock, e.precio_base) == (7, 4.0)
    assert eventos[-1]["payload"]["stock"] == 7
    n = len(eventos)
    inventario.editar(p.id, {"nombre": "Arroz Extra"}, "admin")   # sin cambio de stock
    assert len(eventos) == n
    assert [x.id for x in inventario.listar("comprador")] == [p.id]
    inventario.dar_de_baja(p.id, "admin")
    assert inventario.listar("admin") == []
    assert [x.id for x in inventario.listar("admin", activos=False)] == [p.id]
    assert [x.id for x in inventario.listar("admin", activos=None)] == [p.id]
    with pytest.raises(NoEncontrado):
        inventario.editar(999, {"stock": 1}, "admin")


def test_baja_desactiva_descuentos(inventario, riesgo, factory):
    p = inventario.crear({**DATOS, "fecha_vencimiento": AHORA + timedelta(days=2)}, "admin")
    riesgo.escanear()
    inventario.dar_de_baja(p.id, "admin")
    with sesion(factory) as s:
        assert DescuentoRepo(s).activo_de(p.id) is None


@pytest.mark.parametrize("rol", ["comprador", None, "root"])
def test_solo_admin_muta_inventario(inventario, crear_producto, rol):
    p = crear_producto()
    with pytest.raises(RolNoPermitido) as ei:
        inventario.crear(DATOS, rol)
    assert ei.value.codigo == "ROL_NO_PERMITIDO" and ei.value.http == 403
    with pytest.raises(RolNoPermitido):
        inventario.editar(p.id, {"stock": 1}, rol)
    with pytest.raises(RolNoPermitido):
        inventario.dar_de_baja(p.id, rol)


@pytest.mark.parametrize("malo", [
    {"nombre": ""}, {"nombre": "  "}, {"precio_base": -1}, {"precio_base": "x"},
    {"precio_base": float("nan")}, {"stock": -1}, {"stock": 1.5}, {"stock": True},
    {"stock_maximo": -5}, {"fecha_vencimiento": "no-es-fecha"}, {"fecha_vencimiento": 20270101},
    {"color": "rojo"}, {"activo": "si"},
])
def test_validacion_inventario(inventario, malo):
    from server.application.errores import ErrorValidacion
    with pytest.raises(ErrorValidacion):
        inventario.crear({**DATOS, **malo}, "admin")


def test_crear_exige_nombre_y_precio(inventario):
    from server.application.errores import ErrorValidacion
    with pytest.raises(ErrorValidacion):
        inventario.crear({"nombre": "x"}, "admin")

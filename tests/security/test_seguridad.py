import hashlib
import pathlib
from datetime import timedelta

import jwt
import pytest

from server.infrastructure.db.engine import crear_engine, crear_esquema, crear_session_factory
from server.infrastructure.db.repos import SesionRepo, UsuarioRepo
from server.security import bootstrap, tokens
from server.security.dependencias import extraer_bearer, requiere_rol
from server.security.errores import (CredencialesInvalidas, RolNoPermitido, SesionCerrada,
                                     SesionInactiva, TokenInvalido, TooManyAttempts)
from server.security.hashing import hashear, verificar
from server.security.sesiones import AuthService, Contexto

from .conftest import poner_config

HORA = timedelta(hours=1)


# -- hashing --
def test_argon2id_hash_y_verificacion():
    h = hashear("secreta")
    assert h.startswith("$argon2id$")
    assert verificar("secreta", h) == (True, False)
    assert verificar("otra", h) == (False, False)


def test_sha256_legacy_valido_pide_rehash():
    h = "sha256$" + hashlib.sha256("vieja".encode()).hexdigest()
    assert verificar("vieja", h) == (True, True)
    assert verificar("mala", h) == (False, False)


@pytest.mark.parametrize("h", ["", None, "basura", "$argon2id$roto", "sha256$"])
def test_hash_invalido_no_lanza(h):
    assert verificar("x", h) == (False, False)


# -- tokens --
def test_token_ida_y_vuelta_y_manipulado(reloj):
    exp = reloj() + HORA
    t = tokens.emitir(7, "admin", "jti1", exp)
    assert tokens.decodificar(t, reloj()) == {
        "usuario_id": 7, "rol": "admin", "jti": "jti1", "exp": int(exp.timestamp())}
    with pytest.raises(TokenInvalido):
        tokens.decodificar(t[:-3] + "abc", reloj())
    with pytest.raises(TokenInvalido):
        tokens.decodificar("no.es.token", reloj())
    ajeno = jwt.encode({"sub": "7", "rol": "admin", "jti": "j", "exp": 9999999999}, "otro" * 8, "HS256")
    with pytest.raises(TokenInvalido):
        tokens.decodificar(ajeno, reloj())
    sin_exp = jwt.encode({"sub": "7", "rol": "admin", "jti": "j"}, tokens.obtener_secreto(), "HS256")
    with pytest.raises(TokenInvalido):
        tokens.decodificar(sin_exp, reloj())
    sin_firma = jwt.encode({"sub": "7", "rol": "admin", "jti": "j", "exp": 9999999999}, None, "none")
    with pytest.raises(TokenInvalido):
        tokens.decodificar(sin_firma, reloj())


def test_token_expirado(auth, reloj, factory):
    poner_config(factory, "sesion_maxima_minutos", 1)
    poner_config(factory, "inactividad_segundos", 3600)
    tk = auth.login("ana", "clave-ana")["token"]
    reloj.avanzar(61)
    with pytest.raises(TokenInvalido) as e:
        auth.validar_token(tk)
    assert e.value.detalle["motivo"] == "expirado"


def test_secreto_se_genera_en_archivo_y_se_reutiliza(monkeypatch, tmp_path):
    monkeypatch.delenv("INVENTARIO_JWT_SECRET")
    monkeypatch.setenv("INVENTARIO_DATA_DIR", str(tmp_path / "otro"))
    tokens._cache.clear()
    s1 = tokens.obtener_secreto()
    assert len(s1) == 64
    assert (tmp_path / "otro" / "jwt_secret").read_text().strip() == s1
    tokens._cache.clear()
    assert tokens.obtener_secreto() == s1


# -- login --
def test_login_ok(auth):
    r = auth.login("ana", "clave-ana")
    assert r["usuario"] == {"id": 1, "nombre": "Ana", "rol": "admin"}
    assert r["sesion"] == {"inactividad_segundos": 180, "aviso_segundos": 30}
    assert r["token"] and r["expira_en"]
    ctx = auth.validar_token(r["token"])
    assert ctx.rol == "admin" and ctx.usuario_id == 1


def test_login_error_generico(auth):
    msgs = set()
    for u, p in [("ana", "mala"), ("noexiste", "x"), ("inac", "clave-inac"), ("", ""), ("ana", "")]:
        with pytest.raises(CredencialesInvalidas) as e:
            auth.login(u, p)
        assert e.value.http == 401 and e.value.codigo == "CREDENCIALES_INVALIDAS"
        msgs.add(e.value.mensaje)
    assert len(msgs) == 1


def test_login_rehash_sha256(auth, factory):
    with factory() as s:
        UsuarioRepo(s).actualizar(2, password_hash="sha256$" + hashlib.sha256(b"vieja").hexdigest())
        s.commit()
    auth.login("beto", "vieja")
    with factory() as s:
        h = UsuarioRepo(s).obtener(2).password_hash
    assert h.startswith("$argon2id$")
    assert verificar("vieja", h) == (True, False)
    auth.login("beto", "vieja")


def test_bloqueo_por_intentos(auth, reloj):
    for _ in range(5):
        with pytest.raises(CredencialesInvalidas):
            auth.login("ana", "mala")
    with pytest.raises(TooManyAttempts) as e:
        auth.login("ana", "clave-ana")  # ni la correcta pasa durante el bloqueo
    assert e.value.http == 429
    reloj.avanzar(59)
    with pytest.raises(TooManyAttempts):
        auth.login("ana", "clave-ana")
    reloj.avanzar(2)
    assert auth.login("ana", "clave-ana")["token"]
    # el exito resetea el contador
    for _ in range(4):
        with pytest.raises(CredencialesInvalidas):
            auth.login("beto", "mala")
    auth.login("beto", "clave-beto")
    for _ in range(4):
        with pytest.raises(CredencialesInvalidas):
            auth.login("beto", "mala")


# -- inactividad --
def test_inactividad_179_vive_181_muere(factory, reloj, bus):
    auth = AuthService(factory, bus, reloj)
    tk = auth.login("ana", "clave-ana")["token"]
    reloj.avanzar(179)
    auth.validar_token(tk)
    reloj.avanzar(2)  # 181
    with pytest.raises(SesionInactiva) as e:
        auth.validar_token(tk)
    assert e.value.codigo == "SESION_INACTIVA" and e.value.http == 401
    assert bus.eventos == [("sesion_cerrada", {"motivo": "inactividad"}, 1)]
    with factory() as s:
        assert SesionRepo(s).listar_abiertas() == []
    with pytest.raises(SesionCerrada):
        auth.validar_token(tk)


def test_borde_exacto_180_vive(auth, reloj):
    tk = auth.login("ana", "clave-ana")["token"]
    reloj.avanzar(180)
    auth.validar_token(tk)


def test_validar_no_renueva_y_actividad_si(auth, reloj):
    tk = auth.login("ana", "clave-ana")["token"]
    reloj.avanzar(100)
    auth.validar_token(tk)
    assert auth.estado_sesion(tk).segundos_restantes == 80  # validar/estado no renovaron
    reloj.avanzar(79)
    auth.validar_token(tk)
    assert auth.registrar_actividad(tk) == 180
    reloj.avanzar(179)
    auth.validar_token(tk)  # vivo gracias a la actividad (279 s desde el login)
    reloj.avanzar(2)
    with pytest.raises(SesionInactiva):
        auth.validar_token(tk)


def test_actividad_sobre_sesion_caducada_falla(auth, reloj):
    tk = auth.login("ana", "clave-ana")["token"]
    reloj.avanzar(200)
    with pytest.raises(SesionInactiva):
        auth.registrar_actividad(tk)


def test_estado_sesion(auth, reloj):
    tk = auth.login("ana", "clave-ana")["token"]
    reloj.avanzar(50)
    e = auth.estado_sesion(tk)
    assert (e.segundos_restantes, e.inactividad_segundos, e.aviso_segundos) == (130, 180, 30)


def test_cambio_de_config_aplica_a_sesion_abierta(auth, reloj, factory):
    tk = auth.login("ana", "clave-ana")["token"]
    reloj.avanzar(90)
    auth.validar_token(tk)  # con 180 vive
    poner_config(factory, "inactividad_segundos", 60)
    with pytest.raises(SesionInactiva):
        auth.validar_token(tk)


def test_cambio_de_config_amplia(auth, reloj, factory):
    tk = auth.login("ana", "clave-ana")["token"]
    poner_config(factory, "inactividad_segundos", 600)
    reloj.avanzar(500)
    auth.validar_token(tk)
    assert auth.estado_sesion(tk).segundos_restantes == 100


# -- logout / revocacion --
def test_logout_revoca(auth):
    tk = auth.login("ana", "clave-ana")["token"]
    auth.logout(tk)
    with pytest.raises(SesionCerrada):
        auth.validar_token(tk)


def test_cerrar_sesiones_de_usuario(auth, bus):
    t1 = auth.login("beto", "clave-beto")["token"]
    t2 = auth.login("beto", "clave-beto")["token"]
    ta = auth.login("ana", "clave-ana")["token"]
    assert auth.cerrar_sesiones_de(2) == 2
    for t in (t1, t2):
        with pytest.raises(SesionCerrada):
            auth.validar_token(t)
    auth.validar_token(ta)
    assert ("sesion_cerrada", {"motivo": "revocada"}, 2) in bus.eventos


def test_usuario_desactivado_pierde_sesion(auth, factory):
    tk = auth.login("beto", "clave-beto")["token"]
    with factory() as s:
        UsuarioRepo(s).actualizar(2, activo=False)
        s.commit()
    with pytest.raises(SesionCerrada):
        auth.validar_token(tk)


def test_token_de_sesion_inexistente(auth, reloj):
    t = tokens.emitir(1, "admin", "fantasma", reloj() + HORA)
    with pytest.raises(TokenInvalido):
        auth.validar_token(t)


def test_sin_bus(factory, reloj):
    a = AuthService(factory, reloj=reloj)
    tk = a.login("ana", "clave-ana")["token"]
    reloj.avanzar(500)
    with pytest.raises(SesionInactiva):
        a.validar_token(tk)


# -- dependencias --
def test_requiere_rol():
    chk = requiere_rol("admin")
    ctx = Contexto(1, "admin", "j")
    assert chk(ctx) is ctx
    with pytest.raises(RolNoPermitido) as e:
        chk(Contexto(2, "comprador", "j"))
    assert e.value.http == 403 and e.value.codigo == "ROL_NO_PERMITIDO"
    assert requiere_rol("admin", "comprador")(Contexto(2, "comprador", "j"))


def test_extraer_bearer():
    assert extraer_bearer("Bearer abc.def") == "abc.def"
    assert extraer_bearer("bearer abc") == "abc"
    for malo in (None, "", "Bearer", "Basic abc", "Bearer a b", "abc"):
        with pytest.raises(TokenInvalido):
            extraer_bearer(malo)


# -- bootstrap --
def _bd(tmp_path, nombre):
    eng = crear_engine(tmp_path / nombre)
    crear_esquema(eng)
    return eng, crear_session_factory(eng)


def test_bootstrap_genera_credenciales_y_es_idempotente(tmp_path):
    eng, f = _bd(tmp_path, "b.db")
    salida = []
    with f() as s:
        assert bootstrap.asegurar_usuarios_iniciales(s, imprimir=salida.append) == ["admin", "comprador"]
        s.commit()
    archivo = tmp_path / "datos" / "credenciales_iniciales.txt"
    txt = archivo.read_text()
    pw = {ln.split(": ")[0]: ln.split(": ")[1] for ln in txt.splitlines() if ": " in ln}
    assert set(pw) == {"admin", "comprador"} and pw["admin"] != pw["comprador"]
    assert any(pw["admin"] in ln for ln in salida)
    with f() as s:
        us = {u.usuario: u for u in UsuarioRepo(s).listar()}
        assert us["admin"].rol == "admin" and us["comprador"].rol == "comprador"
        assert verificar(pw["admin"], us["admin"].password_hash)[0]
        assert bootstrap.asegurar_usuarios_iniciales(s, imprimir=salida.append) == []
        assert len(UsuarioRepo(s).listar()) == 2
    assert archivo.read_text() == txt
    eng.dispose()


def test_bootstrap_con_variables_de_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("INVENTARIO_ADMIN_PASSWORD", "pw-admin-env")
    monkeypatch.setenv("INVENTARIO_COMPRADOR_PASSWORD", "pw-comp-env")
    eng, f = _bd(tmp_path, "c.db")
    with f() as s:
        bootstrap.asegurar_usuarios_iniciales(s, imprimir=lambda *_: None)
        us = {u.usuario: u for u in UsuarioRepo(s).listar()}
        assert verificar("pw-admin-env", us["admin"].password_hash)[0]
        assert verificar("pw-comp-env", us["comprador"].password_hash)[0]
    assert not (tmp_path / "datos" / "credenciales_iniciales.txt").exists()
    eng.dispose()


def test_sin_contrasenas_fijas_en_codigo():
    src = pathlib.Path(bootstrap.__file__).read_text()
    for flojo in ("admin123", "comprador123", "password =", "123456"):
        assert flojo not in src

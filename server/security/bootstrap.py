"""Usuarios iniciales sin contrasenas fijas en el codigo.

Credenciales de demo: defina INVENTARIO_ADMIN_PASSWORD / INVENTARIO_COMPRADOR_PASSWORD antes del
primer arranque, o arranque sin ellas y lea `credenciales_iniciales.txt` en el directorio de datos
del servidor (INVENTARIO_DATA_DIR o el directorio de INVENTARIO_DB). Tambien se imprimen una vez
en consola. Cambielas tras el primer ingreso y borre el archivo."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from sqlalchemy.orm import Session

from server.infrastructure.db.repos import UsuarioRepo

from .hashing import hashear
from .rutas import directorio_datos, escribir_privado

ARCHIVO_CREDENCIALES = "credenciales_iniciales.txt"
INICIALES = (
    ("admin", "Administrador", "admin", "INVENTARIO_ADMIN_PASSWORD"),
    ("comprador", "Comprador", "comprador", "INVENTARIO_COMPRADOR_PASSWORD"),
)


def asegurar_usuarios_iniciales(sesion: Session, directorio: Path | None = None,
                                imprimir=print) -> list[str]:
    """Si no hay usuarios crea admin y comprador. Devuelve los usuarios creados (vacio si ya habia).
    No hace commit (lo hace quien abre la sesion)."""
    repo = UsuarioRepo(sesion)
    if repo.listar():
        return []
    generadas: list[tuple[str, str]] = []
    creados = []
    for usuario, nombre, rol, var in INICIALES:
        pw = os.environ.get(var)
        if not pw:
            pw = secrets.token_urlsafe(12)
            generadas.append((usuario, pw))
        repo.crear(nombre, usuario, hashear(pw), rol=rol)
        creados.append(usuario)
    if generadas:
        ruta = (directorio or directorio_datos()) / ARCHIVO_CREDENCIALES
        cuerpo = ("Credenciales iniciales (generadas una sola vez).\n"
                  "CAMBIELAS tras el primer ingreso y borre este archivo.\n\n"
                  + "".join(f"{u}: {p}\n" for u, p in generadas))
        escribir_privado(ruta, cuerpo, exclusivo=False)
        imprimir("=" * 60)
        imprimir("USUARIOS INICIALES CREADOS (cambie las contrasenas):")
        for u, p in generadas:
            imprimir(f"  {u}: {p}")
        imprimir(f"Guardadas en: {ruta}")
        imprimir("=" * 60)
    return creados

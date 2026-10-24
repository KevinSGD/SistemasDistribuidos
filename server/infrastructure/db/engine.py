"""Engine SQLAlchemy 2.0, pragmas de conexion y manejo de sesiones de vida corta."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from platformdirs import user_data_dir
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

ENV_DB = "INVENTARIO_DB"


def ruta_db_por_defecto() -> Path:
    ruta = os.environ.get(ENV_DB)
    if ruta:
        return Path(ruta)
    return Path(user_data_dir("InventarioApp")) / "servidor.db"


def _activar_pragmas(dbapi_con, _record) -> None:
    cur = dbapi_con.cursor()
    try:
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
    finally:
        cur.close()


def crear_engine(ruta: str | Path | None = None) -> Engine:
    """Crea un engine nuevo. Los pragmas se aplican en CADA conexion."""
    ruta = Path(ruta) if ruta is not None else ruta_db_por_defecto()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(f"sqlite:///{ruta}", connect_args={"check_same_thread": False})
    event.listen(eng, "connect", _activar_pragmas)
    return eng


_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def crear_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_engine() -> Engine:
    """Engine del proceso (perezoso; lee INVENTARIO_DB al primer uso)."""
    global _engine, _factory
    if _engine is None:
        _engine = crear_engine()
        _factory = crear_session_factory(_engine)
    return _engine


def configurar(engine: Engine) -> None:
    """Sustituye el engine del proceso (tests / arranque de la app)."""
    global _engine, _factory
    _engine = engine
    _factory = crear_session_factory(engine)


def crear_esquema(engine: Engine | None = None) -> None:
    from .orm import Base

    Base.metadata.create_all(engine or get_engine())


@contextmanager
def sesion(factory: sessionmaker[Session] | None = None) -> Iterator[Session]:
    """Sesion de vida corta: commit al salir, rollback ante excepcion, close siempre."""
    if factory is None:
        get_engine()
        factory = _factory
    s = factory()
    try:
        yield s
        s.commit()
    except BaseException:
        s.rollback()
        raise
    finally:
        s.close()


def get_db() -> Iterator[Session]:
    """Dependencia FastAPI: una sesion por peticion."""
    with sesion() as s:
        yield s

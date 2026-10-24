import pytest

from server.infrastructure.db.engine import crear_engine, crear_esquema, crear_session_factory


@pytest.fixture
def engine(tmp_path):
    eng = crear_engine(tmp_path / "t.db")
    crear_esquema(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine):
    return crear_session_factory(engine)


@pytest.fixture
def s(factory):
    ses = factory()
    yield ses
    ses.rollback()
    ses.close()

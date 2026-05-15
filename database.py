from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import DB_PATH, crear_directorios

crear_directorios()

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

def get_session():
    return SessionLocal()

def inicializar_bd():
    from models import Producto, Venta, Descuento, Usuario
    Base.metadata.create_all(bind=engine)

    # Crear usuario admin por defecto si no existe
    session = SessionLocal()
    admin = session.query(Usuario).filter(Usuario.usuario == "admin").first()
    if not admin:
        from models import Usuario
        admin = Usuario(
            nombre   = "Administrador",
            usuario  = "admin",
            password = Usuario.hashear_password("admin123"),
            rol      = "admin"
        )
        session.add(admin)
        session.commit()
        print("OK: usuario admin creado (usuario: admin, contrasena: admin123)")

    comprador = session.query(Usuario).filter(Usuario.usuario == "comprador").first()
    if not comprador:
        from models import Usuario
        comprador = Usuario(
            nombre   = "Comprador",
            usuario  = "comprador",
            password = Usuario.hashear_password("comprador123"),
            rol      = "usuario"
        )
        session.add(comprador)
        session.commit()
        print("OK: usuario comprador creado (usuario: comprador, contrasena: comprador123)")

    session.close()
    print("OK: base de datos inicializada correctamente.")
#!/usr/bin/env python3
"""Carga datos de demostracion (minimercado colombiano) usando el API real del servidor.

Solo requiere `httpx`. Las fechas de vencimiento son RELATIVAS A HOY, de modo que la demo
siempre cubre todos los niveles de riesgo.  Es idempotente (no duplica por nombre).

Uso:
  python deploy/seed_demo.py --desde-wsl                 # lee la clave del admin de WSL
  python deploy/seed_demo.py --password XXXX             # o INVENTARIO_ADMIN_PASSWORD
  python deploy/seed_demo.py --desde-wsl --reset-fechas  # re-arma fechas/stock (y reactiva retirados)
  python deploy/seed_demo.py --desde-wsl --limpiar       # da de baja los productos de la demo
  python deploy/seed_demo.py --desde-wsl --reset-fechas --minutos 2   # retiro en vivo en ~2 min

La contrasena nunca se imprime.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta

try:
    import httpx
except ImportError:  # pragma: no cover
    sys.exit("Falta httpx: pip install httpx (en Windows: .\\.venv\\Scripts\\python.exe -m pip install httpx)")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SIN = None  # sin vencimiento
HOY_TARDE = "hoy_tarde"
EN_MINUTOS = "en_minutos"

# (nombre, categoria, precio, stock, stock_maximo, vencimiento)
#   vencimiento: dias desde hoy (int, a las 23:59), SIN, HOY_TARDE o EN_MINUTOS
CATALOGO: list[tuple] = [
    # Lacteos
    ("Leche entera 1 L", "Lácteos", 4200, 45, 120, 60),
    ("Yogur natural 200 g", "Lácteos", 6900, 30, 60, 2),                  # critico
    ("Queso campesino 500 g", "Lácteos", 12800, 18, 40, 6),               # alto
    # Carnes frias
    ("Jamón de cerdo 250 g", "Carnes frías", 11500, 14, 40, 3),           # critico
    ("Salchicha ranchera x6", "Carnes frías", 9800, 8, 40, 90),           # stock bajo
    ("Chorizo santarrosano x8", "Carnes frías", 13500, 25, 50, 45),
    # Panaderia
    ("Pan tajado 450 g", "Panadería", 5400, 36, 60, 1),                   # critico
    ("Croissant x4", "Panadería", 7200, 20, 40, 4),                       # alto
    ("Pan integral 400 g", "Panadería", 6300, 28, 50, 12),
    ("Sándwich de pollo (retiro en vivo)", "Panadería", 8500, 15, 30, EN_MINUTOS),
    # Frutas y verduras
    ("Banano por kg", "Frutas y verduras", 3200, 60, 80, 7),              # alto (limite)
    ("Tomate chonto por kg", "Frutas y verduras", 4500, 48, 50, 12),      # sobrestock
    ("Lechuga crespa unidad", "Frutas y verduras", 2800, 15, 30, 2),      # critico
    ("Papa pastusa 2 kg", "Frutas y verduras", 7500, 70, 100, 30),
    ("Ensalada de frutas 250 g (vence hoy)", "Frutas y verduras", 5200, 12, 30, HOY_TARDE),
    # Abarrotes
    ("Arroz blanco 1 kg", "Abarrotes", 4800, 150, 160, 200),              # sobrestock
    ("Aceite de girasol 1 L", "Abarrotes", 14900, 60, 100, 180),
    ("Sal refinada 1 kg", "Abarrotes", 2100, 90, 150, SIN),
    ("Panela cuadrada 500 g", "Abarrotes", 3600, 55, 100, SIN),
    # Bebidas
    ("Gaseosa cola 1.5 L", "Bebidas", 5600, 80, 100, 120),
    ("Agua sin gas 600 ml", "Bebidas", 2000, 120, 130, 200),              # sobrestock
    ("Jugo de naranja 1 L", "Bebidas", 7800, 22, 40, 5),                  # alto
    ("Café molido 500 g", "Bebidas", 16500, 25, 60, 150),
    # Congelados
    ("Pollo apanado 1 kg", "Congelados", 18900, 7, 30, 90),               # stock bajo
    ("Helado de vainilla 1 L", "Congelados", 12400, 35, 50, 100),
]


def fecha_venc(spec, ahora: datetime, minutos: int) -> datetime | None:
    if spec is SIN:
        return None
    if spec == EN_MINUTOS:
        return (ahora + timedelta(minutes=minutos)).replace(microsecond=0)
    if spec == HOY_TARDE:
        limite = ahora.replace(hour=23, minute=59, second=0, microsecond=0)
        # si ya casi acaba el dia, que quede al menos 5 minutos en el futuro
        return limite if (limite - ahora) > timedelta(minutes=5) else ahora + timedelta(minutes=5)
    return (ahora + timedelta(days=int(spec))).replace(hour=23, minute=59, second=0, microsecond=0)


def _wsl(cmd: str, distro: str) -> str:
    try:
        r = subprocess.run(["wsl", "-d", distro, "--", "bash", "-lc", cmd],
                           capture_output=True, text=True, encoding="utf-8", timeout=30)
    except FileNotFoundError:
        raise SystemExit("No se encontro 'wsl' en el PATH; use --password o INVENTARIO_ADMIN_PASSWORD.")
    except subprocess.TimeoutExpired:
        raise SystemExit("WSL no respondio en 30 s.")
    if r.returncode != 0:
        raise SystemExit(f"WSL fallo (codigo {r.returncode}); verifique la distro '{distro}'.")
    return r.stdout


def password_desde_wsl(distro: str) -> str:
    for linea in _wsl("cat ~/.inventario/credenciales.env", distro).splitlines():
        if linea.startswith("INVENTARIO_ADMIN_PASSWORD="):
            return linea.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit("No hay INVENTARIO_ADMIN_PASSWORD en ~/.inventario/credenciales.env de WSL (¿ejecuto setup.sh?).")


def hora_del_servidor(args) -> datetime:
    """Los vencimientos son datetimes ingenuos en hora local DEL SERVIDOR. Con --desde-wsl se
    toma el reloj de WSL; si no, el de esta maquina (en la demo es la misma y la misma zona)."""
    if args.desde_wsl:
        try:
            return datetime.fromisoformat(_wsl("date +%Y-%m-%dT%H:%M:%S", args.distro).strip())
        except (ValueError, SystemExit):
            pass
    return datetime.now().replace(microsecond=0)


class Api:
    def __init__(self, url: str):
        self.c = httpx.Client(base_url=url.rstrip("/") + "/api/v1", timeout=15.0)

    def req(self, metodo: str, ruta: str, **kw):
        try:
            r = self.c.request(metodo, ruta, **kw)
        except httpx.ConnectError:
            raise SystemExit(f"No se pudo conectar con {self.c.base_url}. ¿Esta el servidor en marcha? "
                             "(.\\deploy\\windows\\start_server_wsl.ps1)")
        except httpx.TimeoutException:
            raise SystemExit(f"Tiempo de espera agotado hablando con {self.c.base_url}.")
        except httpx.HTTPError as e:
            raise SystemExit(f"Error de red: {e.__class__.__name__}")
        if r.status_code == 401:
            raise SystemExit("401 No autorizado: contrasena de admin incorrecta o sesion caducada.")
        if r.status_code == 429:
            raise SystemExit("429 Demasiados intentos de login; espere 60 s.")
        if r.status_code >= 400:
            try:
                d = r.json()
                msg = f"{d.get('codigo')}: {d.get('mensaje')}"
            except ValueError:
                msg = r.text[:200]
            raise SystemExit(f"Error {r.status_code} en {metodo} {ruta}: {msg}")
        return r

    def login(self, usuario: str, password: str):
        r = self.req("POST", "/auth/login", json={"usuario": usuario, "password": password})
        self.c.headers["Authorization"] = "Bearer " + r.json()["token"]

    def logout(self):
        try:
            self.c.post("/auth/logout")
        except httpx.HTTPError:
            pass


def iso(d: datetime | None):
    return d.isoformat(timespec="seconds") if d else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("INVENTARIO_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--usuario", default="admin")
    ap.add_argument("--password", default=os.environ.get("INVENTARIO_ADMIN_PASSWORD"))
    ap.add_argument("--desde-wsl", action="store_true", help="leer la clave de ~/.inventario/credenciales.env en WSL")
    ap.add_argument("--distro", default=os.environ.get("INVENTARIO_WSL_DISTRO", "Ubuntu"))
    ap.add_argument("--reset-fechas", action="store_true",
                    help="si el producto ya existe, restablece precio, stock, fecha y lo reactiva")
    ap.add_argument("--limpiar", action="store_true", help="da de baja los productos de la demo")
    ap.add_argument("--minutos", type=int, default=4,
                    help="minutos hasta el vencimiento del producto de retiro en vivo (def. 4)")
    args = ap.parse_args()

    password = args.password
    if not password and args.desde_wsl:
        password = password_desde_wsl(args.distro)
    if not password:
        print("Falta la contrasena: use --desde-wsl, --password o INVENTARIO_ADMIN_PASSWORD.", file=sys.stderr)
        return 2

    api = Api(args.url)
    api.login(args.usuario, password)
    try:
        existentes: dict[str, dict] = {}
        for activos in ("true", "false"):
            for p in api.req("GET", "/productos", params={"activos": activos}).json():
                existentes[p["nombre"]] = p
        nombres_demo = {c[0] for c in CATALOGO}

        if args.limpiar:
            n = 0
            for nombre in nombres_demo:
                p = existentes.get(nombre)
                if p and p["activo"]:
                    api.req("DELETE", f"/productos/{p['id']}")
                    n += 1
            print(f"Limpieza: {n} producto(s) de la demo dados de baja.")
            return 0

        ahora = hora_del_servidor(args)
        creados = omitidos = actualizados = 0
        for nombre, cat, precio, stock, maximo, spec in CATALOGO:
            venc = fecha_venc(spec, ahora, args.minutos)
            cuerpo = {"nombre": nombre, "categoria": cat, "precio_base": float(precio), "stock": stock,
                      "stock_maximo": maximo, "fecha_vencimiento": iso(venc), "activo": True}
            p = existentes.get(nombre)
            if p is None:
                api.req("POST", "/productos", json=cuerpo)
                creados += 1
            elif args.reset_fechas:
                cuerpo.pop("nombre")
                api.req("PUT", f"/productos/{p['id']}", json=cuerpo)
                actualizados += 1
            else:
                omitidos += 1
            if spec == EN_MINUTOS and (p is None or args.reset_fechas):
                print(f"  Retiro en vivo: '{nombre}' vence a las {venc:%H:%M:%S} "
                      f"(el escaneo automatico lo retira en <= 60 s despues).")
        print(f"Productos: {creados} creados, {actualizados} restablecidos, {omitidos} omitidos (ya existian).")
        if omitidos and not args.reset_fechas:
            print("  (use --reset-fechas para re-armar fechas y stock; las fechas de una carga anterior envejecen)")

        res = api.req("GET", "/riesgo/resumen").json()
        c = res.get("conteos", {})
        print(f"\nResumen de riesgo ({res.get('total_activos')} productos activos, "
              f"{res.get('con_descuento')} con descuento):")
        for nivel in ("critico", "alto", "medio", "normal"):
            print(f"  {nivel:<8} {c.get(nivel, 0)}")
        return 0
    finally:
        api.logout()


if __name__ == "__main__":
    sys.exit(main())

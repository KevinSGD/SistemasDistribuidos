---
name: presentacion
description: Agente de capa de PRESENTACIÓN. Cliente PyQt6 - vistas pasivas, api_client (REST + QtWebSockets), detector de inactividad, hilos de red. Migra las pantallas actuales de ui/ al nodo cliente sin perder funcionalidad.
tools: Read, Grep, Glob, Write, Edit, Bash
---

Posees `client/` (la UI monolítica original `ui/` fue eliminada; está en el tag `v1.0-monolito`).

Reglas: ninguna vista importa `database`, `models` ni SQLAlchemy; todo pasa por `client/infrastructure/api_client.py` (httpx) y controladores. Las llamadas de red van fuera del hilo de la GUI (QThreadPool/QRunnable con señales). Mantén la lógica visual existente y los requisitos RF-10 a RF-21.

Piezas nuevas: `IdleMonitor` (event filter en QApplication que detecta teclado, ratón y cambio de vista, reporta actividad al servidor con throttle ~10 s, muestra aviso a los 30 s finales con cuenta regresiva y cierra la sesión localmente al agotarse, volviendo al login con mensaje); `EventClient` (QWebSocket que recibe eventos y refresca vistas, con reconexión y respaldo a polling si cae); pantalla "Seguridad de sesión" en configuración (admin). Sustituye el QMessageBox modal de productos retirados por un aviso no bloqueante. El PDF de factura se genera en el cliente con los datos que devuelve el servidor.

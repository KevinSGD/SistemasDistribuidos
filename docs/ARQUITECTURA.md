# Arquitectura — InventarioApp distribuido (borrador)

## Nodos
- **Nodo A, servidor**: Ubuntu (WSL2). FastAPI + uvicorn, SQLite, scheduler de riesgo, WebSocket.
- **Nodo B, cliente**: Windows. PyQt6, `httpx`, `QtWebSockets`.
- Comunicación: HTTP/JSON + WebSocket sobre TCP, puerto 8000. El contrato está en `CONTRATO_API.md`.

## Estructura de carpetas
```
shared/                    DTOs Pydantic (contrato único)
server/
  main.py                  arranque (uvicorn), scheduler
  api/                     routers FastAPI, dependencias, WebSocket, manejo de errores
  application/             servicios y casos de uso, EventBus, puertos
  domain/                  entidades y reglas puras (sin frameworks)
  infrastructure/db/       ORM, constraints, repositorios, migración, seed
  security/                argon2id, JWT, sesión por inactividad
client/
  main.py
  presentation/            vistas pasivas, widgets, tema (estilos centralizados)
  application/             controladores / view-models
  infrastructure/          api_client, event_client (WS), idle_monitor, token_store
deploy/                    wsl/, scripts de arranque, guía de red
tests/                     domain, application, infra, security, api, e2e
docs/                      este documento, contrato, ADRs, informe de pruebas
```

## Regla de dependencias
`presentation → client/application → api_client ⇢ red ⇢ api → application → domain`. `infrastructure` y `security` implementan puertos definidos en `application`. `domain` no importa frameworks.

## Decisiones (ADR resumidas)
1. **FastAPI** para REST y WebSocket en el mismo proceso: tipado con Pydantic, documentación automática en `/docs` útil en la sustentación.
2. **SQLite** se mantiene (alcance académico) con WAL y FK activas; el servidor es el único proceso que la abre.
3. **JWT + tabla `sesiones`**: el JWT identifica, la tabla decide la caducidad por inactividad. Así el cambio del admin aplica a sesiones abiertas y el servidor puede revocar.
4. **Inactividad = input real del usuario**, reportado por el cliente; el refresco automático y el WebSocket no cuentan.
5. **Eventos por WebSocket con respaldo de polling** para tolerar caídas de red.
6. **PDF de factura en el cliente** (ReportLab) a partir de los datos del servidor; el servidor no depende de ReportLab ni de PyQt.
7. **Servidor sin pandas/matplotlib**: dependencias mínimas por nodo.

## Mapa de requisitos
RF-01/02 → seguridad + api/auth; RF-03..07 → InventarioService; RF-08/09/22 → domain + RiesgoService; RF-10/11 → /riesgo; RF-12 → /ofertas; RF-13 → /config; RF-14 → /auth/logout; RF-15..21 → /compras + facturas; RNF-01 → argon2id; RNF-02 → scheduler servidor + hilos cliente; RNF-03 → transacción por caso de uso; RNF-05 → servidor Linux + cliente Windows.

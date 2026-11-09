# Backend de gestión cafetera — CafeSmart

API REST para apoyar la administración de fincas cafeteras. Organiza fincas y lotes, registra trabajadores, jornadas y recolecciones, liquida pagos laborales, controla ventas y egresos operativos, ofrece resúmenes analíticos, un asistente de IA y sincronización para trabajar sin conexión.

Los productores acceden solo a sus propios datos; los administradores tienen acceso global.

---

## Tecnologías

- Python y Django 6.1.
- Django REST Framework (DRF) para la API.
- Simple JWT para autenticación con tokens Bearer (access: 1 día, refresh: 30 días).
- SQLite por defecto en desarrollo; PostgreSQL en producción vía `DATABASE_URL`.
- `django-cors-headers` para CORS (frontend en React).
- Groq para el asistente de IA.
- Despliegue en Render (`render.yaml`).

Dependencias: [`requirements.txt`](requirements.txt).

---

## Requisitos

- Python compatible con Django 6.1.
- `pip`.

---

## Instalación y ejecución local

Desde la carpeta raíz del proyecto:

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

```powershell
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

La API queda disponible en `http://127.0.0.1:8000/` y el panel de administración en `http://127.0.0.1:8000/admin/`.

Para crear un superusuario:

```bash
python manage.py createsuperuser
```

Si se modifican modelos:

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## Variables de entorno (`.env`)

Crear un archivo `.env` en la raíz (no subirlo a control de versiones):

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `SECRET_KEY` | Clave secreta de Django | `django-insecure-...` |
| `DEBUG` | `True` en desarrollo, `False` en producción | `True` |
| `ALLOWED_HOSTS` | Hosts permitidos | `localhost,127.0.0.1` |
| `DATABASE_URL` | Conexión a la base de datos (producción) | `postgres://...` |
| `GROQ_API_KEY` | Clave de Groq para el asistente de IA | `gsk_...` |
| `GROQ_MODEL` | Modelo de Groq (opcional) | `openai/gpt-oss-120b` |
| `FRONTEND_URLS` | URLs del frontend para CORS, separadas por coma | `https://cafesmart.netlify.app` |

---

## Autenticación

La mayoría de los endpoints requiere un token JWT.

1. Iniciar sesión: `POST /accounts/login/` con `email` y `password`.
2. Enviar el token de acceso en las peticiones protegidas:

```http
Authorization: Bearer <access_token>
```

- El token de acceso dura **1 día**; el de refresco **30 días** (rotación habilitada).
- `POST /accounts/token/refresh/` renueva el access token.
- `POST /accounts/token/verify/` verifica un token.
- Los permisos aíslan los datos por productor; los administradores ven todo.

---

## Estructura de carpetas (resumida)

```
backend_coffe_app/
├── sistema_cafe/         # Configuración Django (settings, urls, middleware, wsgi/asgi)
├── apps/                 # Módulos de negocio
│   ├── accounts/         # Usuarios, auth, login, perfil, catálogo de usuarios
│   ├── farms/            # Fincas y lotes
│   ├── labor/            # Mano de obra (trabajadores, jornadas, pesajes)
│   ├── payroll/          # Liquidaciones laborales y pagos
│   ├── finance/          # Egresos operativos
│   ├── production/       # Ventas de café y producción
│   ├── analytics/        # Resúmenes analíticos (finanzas + producción)
│   ├── assistant/        # Asistente de IA (Groq)
│   ├── synchronization/  # Sincronización offline (push / pull / ping)
│   └── integrations/     # Integraciones (reserva futura, módulo vacío)
├── manage.py
├── requirements.txt
├── render.yaml           # Despliegue en Render
├── .env                  # Variables de entorno (no subir)
└── README.md
```

Los identificadores de los recursos principales son **UUID**.

---

## Módulos y qué hace cada uno (resumido)

| Módulo | Qué hace |
|--------|----------|
| `accounts` | Registro, login, perfil, cambio de contraseña y administración del catálogo de usuarios (solo administradores). |
| `farms` | CRUD de fincas y lotes (nombre, ubicación, variedad, área, cantidad de plantas, estado activo). |
| `labor` | Trabajadores, tipos de actividad, jornadas, detalles por lote y pesajes de recolección de café. |
| `payroll` | Liquidaciones laborales (abierta → liquidada → pagada), detalles por jornal o kilogramo y pagos. |
| `finance` | Egresos operativos por categoría (mano de obra, insumos, herramientas, transporte, servicios, otros). |
| `production` | Ventas de café (pergamino / pasilla) y resúmenes de producción por finca y lote. |
| `analytics` | Resumen financiero y de producción: egresos por categoría, ingresos, balance neto, series temporales. |
| `assistant` | Asistente de IA que responde preguntas en lenguaje natural con las métricas del usuario autenticado. |
| `synchronization` | Cola de operaciones offline (`push`), descarga de datos (`pull`) y comprobación de servidor (`ping`). |
| `integrations` | Módulo reservado para futuras integraciones (actualmente vacío). |

---

## Endpoints

Todos los caminos son relativos a `http://127.0.0.1:8000`. Los ViewSets CRUD usan los métodos estándar de DRF: `GET` (listar/consultar), `POST` (crear), `PUT/PATCH` (actualizar), `DELETE` (eliminar), salvo que se indique otra cosa.

### Cuentas y usuarios — `/accounts/`

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/accounts/register/` | `POST` | Registra un productor (público). |
| `/accounts/login/` | `POST` | Login con email y contraseña; devuelve tokens y datos del usuario. |
| `/accounts/token/refresh/` | `POST` | Renueva el token de acceso. |
| `/accounts/token/verify/` | `POST` | Verifica un token. |
| `/accounts/profile/` | `GET`, `PUT`, `PATCH` | Consulta o actualiza el perfil del usuario autenticado. |
| `/accounts/change-password/` | `PUT`, `PATCH` | Cambia la contraseña validando la actual. |
| `/accounts/users/` | `GET`, `POST` | Lista usuarios o crea una cuenta con rol. Solo administradores. |
| `/accounts/users/{id}/` | `GET`, `PUT`, `PATCH` | Consulta o actualiza una cuenta. Solo administradores (no borrado físico). |
| `/accounts/users/{id}/deactivate/` | `POST` | Desactiva una cuenta. Solo administradores. |
| `/accounts/users/{id}/activate/` | `POST` | Reactiva una cuenta. Solo administradores. |

### Fincas y lotes — `/farms/`

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/farms/` y `/farms/{id}/` | CRUD | Lista, crea, consulta, actualiza o elimina fincas. |
| `/farms/lots/` y `/farms/lots/{id}/` | CRUD | Administra lotes (variedad, área, plantas, descripción, estado activo). |

### Mano de obra — `/labor/`

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/labor/workers/` y `/labor/workers/{id}/` | CRUD | Trabajadores del productor (desactivar en lugar de eliminar si tienen historial). |
| `/labor/activity-types/` y `/labor/activity-types/{id}/` | CRUD | Tipos de actividad (`is_harvest` distingue recolección). |
| `/labor/workdays/` y `/labor/workdays/{id}/` | CRUD | Jornadas diarias de una finca (una por productor, finca y fecha). |
| `/labor/workdays/{id}/close/` | `POST` | Cierra la jornada (`status: cerrada`, `closed_at`). |
| `/labor/workdays/{id}/labor/` | `PATCH` | Actualiza actividad, modalidad y tarifa de todas las participaciones no anuladas (solo jornada abierta). |
| `/labor/workday-workers/` y `/labor/workday-workers/{id}/` | CRUD | Participación de un trabajador en una jornada (modalidad, tarifa, estado de liquidación). |
| `/labor/workday-workers/{id}/cancel/` | `POST` | Anula una participación pendiente. |
| `/labor/workday-workers/{id}/reactivate/` | `POST` | Reactiva una participación anulada en jornada abierta. |
| `/labor/workday-details/` y `/labor/workday-details/{id}/` | CRUD | Asocia actividad y lote a una participación de jornada. |
| `/labor/harvest-records/` y `/labor/harvest-records/{id}/` | CRUD | Pesajes de recolección en kg asociados a un detalle de jornada. |
| `/labor/harvest-records/{id}/cancel/` | `POST` | Anula un pesaje registrado (no liquidado). |

### Liquidaciones y pagos — `/payroll/`

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/payroll/settlements/` y `/payroll/settlements/{id}/` | CRUD restringido | Crea y consulta liquidaciones. Solo se modifica/elimina si está abierta y sin detalles. |
| `/payroll/settlements/pending/` | `GET` | Registros pendientes de liquidar (requiere `worker` y `farm`; opcional `start_date`, `end_date`). |
| `/payroll/settlements/add-workday/` | `POST` | Añade una participación (jornal) a una liquidación abierta. |
| `/payroll/settlements/add-harvest/` | `POST` | Añade un pesaje (kg) a una liquidación abierta. |
| `/payroll/settlements/close/` | `POST` | Cierra la liquidación, calcula el total y la pasa a `liquidada`. |
| `/payroll/settlements/pay/` | `POST` | Registra el pago de una liquidación `liquidada` y la pasa a `pagada`. |
| `/payroll/settlements/cancel/` | `POST` | Anula una liquidación abierta sin detalles. |
| `/payroll/settlement-workdays/` y `/{id}/` | `GET` | Detalles de liquidación por jornal (solo lectura). |
| `/payroll/settlement-harvests/` y `/{id}/` | `GET` | Detalles de liquidación por kilogramo (solo lectura). |
| `/payroll/payments/` y `/{id}/` | `GET` | Pagos laborales registrados (solo lectura). |

Estados de liquidación: `abierta`, `liquidada`, `pagada`, `anulada`.

### Finanzas — `/finance/`

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/finance/expenses/` y `/finance/expenses/{id}/` | `GET`, `POST`, `PUT`, `PATCH` | Egresos operativos (no admite `DELETE` para conservar historial). |

Filtros en el listado: `category`, `farm` (UUID), `date_from`, `date_to` (`AAAA-MM-DD`).

Categorías: `labor`, `inputs`, `tools_materials`, `transport`, `services`, `other`.

### Producción y ventas — `/production/`

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/production/sales/` y `/production/sales/{id}/` | CRUD (borrado lógico) | Ventas de café por finca, tipo, cantidad y precio. El total se calcula automáticamente. |
| `/production/sales/revenue-by-farm/` | `GET` | Ingresos por ventas agrupados por finca. |
| `/production/production/by-farm/` | `GET` | Producción en kg y número de pesajes por finca. |
| `/production/production/by-lot/` | `GET` | Producción en kg y número de pesajes por lote. |

Tipos de café: `pergamino`, `pasilla`. Filtros opcionales: `farm_id`, `lot_id`, `year`, `month`.

### Analíticas — `/analytics/`

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/analytics/summary/` | `GET` | Egresos por categoría, ingresos por ventas, egresos totales, balance neto, producción por lote, totales de semana/mes/año y serie de barras. |

Parámetros opcionales: `farm_id` y `period` (`week`, `month`, `year`, `all`; por defecto `month`).

### Asistente de IA — `/assistant/`

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/assistant/ask/` | `POST` | Responde una pregunta en texto usando métricas del usuario autenticado. |

Request: `{"question": "...", "history": [{"role": "user", "content": "..."}]}` (histórico opcional, hasta 8 mensajes, roles `user`/`assistant`).  
Response: `{"answer": "..."}`.

### Sincronización — `/sync/`

| Endpoint | Métodos | Descripción |
|----------|---------|-------------|
| `/sync/push/` | `POST` | Recibe la cola de operaciones offline y las aplica en orden. Cuerpo: `{"operations": [...]}`. |
| `/sync/pull/` | `GET` | Descarga datos operativos del usuario para trabajar sin conexión. |
| `/sync/ping/` | `GET` | Comprueba si el servidor está disponible (sin autenticación). |

---

## JSON de datos por tabla (lo que se envía al front)

A continuación un ejemplo de **request** (entrada) y **response** (salida) para cada tabla principal. Los campos marcado como `read_only` se devuelven en la respuesta pero no se envían al crear.

### 1. Usuario (`accounts`)

**Registro** `POST /accounts/register/`
```json
{
  "first_name": "Juan",
  "last_name": "Pérez",
  "email": "juan@example.com",
  "phone_number": "3001234567",
  "password": "contraseñaSegura123"
}
```

**Respuesta login** `POST /accounts/login/`
```json
{
  "access": "eyJ...",
  "refresh": "eyJ...",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "juan@example.com",
    "first_name": "Juan",
    "last_name": "Pérez",
    "phone_number": "3001234567",
    "role": "PRODUCER",
    "full_name": "Juan Pérez"
  }
}
```

**Perfil** `GET/PUT/PATCH /accounts/profile/`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "first_name": "Juan",
  "last_name": "Pérez",
  "email": "juan@example.com",
  "phone_number": "3001234567",
  "role": "PRODUCER",
  "role_label": "Productor",
  "full_name": "Juan Pérez"
}
```

### 2. Finca (`farms.Farm`)

**Request** `POST /farms/`
```json
{
  "id_productor": "550e8400-e29b-41d4-a716-446655440000",
  "name": "El Porvenir",
  "location": "Vereda La Pradera, Antioquia",
  "description": "Finca familiar de café especial"
}
```

**Response**
```json
{
  "id": "a1b2c3d4-1111-2222-3333-444455556666",
  "id_productor": "550e8400-e29b-41d4-a716-446655440000",
  "producer_email": "juan@example.com",
  "producer_name": "Juan Pérez",
  "name": "El Porvenir",
  "location": "Vereda La Pradera, Antioquia",
  "description": "Finca familiar de café especial",
  "lots_count": 2,
  "created_at": "2026-10-20T08:00:00Z",
  "updated_at": "2026-10-20T08:00:00Z"
}
```

### 3. Lote (`farms.Lot`)

**Request** `POST /farms/lots/`
```json
{
  "id_farm": "a1b2c3d4-1111-2222-3333-444455556666",
  "name": "Lote Norte",
  "coffee_variety": "Caturra",
  "area_m2": 5000.00,
  "plant_count": 1200,
  "description": "Lote de altura, sombreado",
  "is_active": true
}
```

**Response**
```json
{
  "id": "b2c3d4e5-2222-3333-4444-555566667777",
  "id_farm": "a1b2c3d4-1111-2222-3333-444455556666",
  "farm_name": "El Porvenir",
  "producer_email": "juan@example.com",
  "name": "Lote Norte",
  "coffee_variety": "Caturra",
  "area_m2": "5000.00",
  "area_hectares": "5000.00",
  "plant_count": 1200,
  "description": "Lote de altura, sombreado",
  "is_active": true,
  "created_at": "2026-10-20T08:00:00Z",
  "updated_at": "2026-10-20T08:00:00Z"
}
```

### 4. Trabajador (`labor.Worker`)

**Request** `POST /labor/workers/`
```json
{
  "producer": "550e8400-e29b-41d4-a716-446655440000",
  "identification": "12345678",
  "first_name": "Carlos",
  "last_name": "Gómez",
  "phone": "3009876543",
  "is_active": true
}
```

**Response**
```json
{
  "id": "c3d4e5f6-3333-4444-5555-666677778888",
  "producer": "550e8400-e29b-41d4-a716-446655440000",
  "producer_name": "Juan Pérez",
  "producer_email": "juan@example.com",
  "identification": "12345678",
  "first_name": "Carlos",
  "last_name": "Gómez",
  "phone": "3009876543",
  "is_active": true,
  "created_at": "2026-10-20T08:00:00Z"
}
```

### 5. Tipo de actividad (`labor.ActivityType`)

**Request** `POST /labor/activity-types/`
```json
{
  "producer": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Recolección selectiva",
  "description": "Cosecha de café maduro a mano",
  "is_harvest": true
}
```

**Response**
```json
{
  "id": "d4e5f6a7-4444-5555-6666-777788889999",
  "producer": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Recolección selectiva",
  "description": "Cosecha de café maduro a mano",
  "is_harvest": true
}
```

### 6. Jornada (`labor.Workday`)

**Request** `POST /labor/workdays/`
```json
{
  "farm": "a1b2c3d4-1111-2222-3333-444455556666",
  "date": "2026-10-20"
}
```

**Response**
```json
{
  "id": "e5f6a7b8-5555-6666-7777-888899990000",
  "producer": "550e8400-e29b-41d4-a716-446655440000",
  "farm": "a1b2c3d4-1111-2222-3333-444455556666",
  "farm_name": "El Porvenir",
  "date": "2026-10-20",
  "status": "abierta",
  "closed_at": null,
  "created_at": "2026-10-20T08:00:00Z"
}
```

**Cerrar jornada** `POST /labor/workdays/{id}/close/` (sin cuerpo)

**Response**
```json
{
  "id": "e5f6a7b8-5555-6666-7777-888899990000",
  "status": "cerrada",
  "closed_at": "2026-10-20T17:00:00Z"
}
```

**Actualizar labor** `PATCH /labor/workdays/{id}/labor/`
```json
{
  "activity_type": "d4e5f6a7-4444-5555-6666-777788889999",
  "payment_mode": "kg",
  "agreed_rate": "1200.00"
}
```

### 7. Participación de trabajador (`labor.WorkdayWorker`)

**Request** `POST /labor/workday-workers/`
```json
{
  "workday": "e5f6a7b8-5555-6666-7777-888899990000",
  "worker": "c3d4e5f6-3333-4444-5555-666677778888",
  "payment_mode": "jornal",
  "agreed_rate": "50000.00"
}
```

**Response**
```json
{
  "id": "f6a7b8c9-6666-7777-8888-999900001111",
  "workday": "e5f6a7b8-5555-6666-7777-888899990000",
  "worker": "c3d4e5f6-3333-4444-5555-666677778888",
  "worker_name": "Carlos Gómez",
  "worker_identification": "12345678",
  "payment_mode": "jornal",
  "agreed_rate": "50000.00",
  "settlement_status": "pendiente",
  "details": []
}
```

### 8. Detalle de jornada (`labor.WorkdayDetail`)

**Request** `POST /labor/workday-details/`
```json
{
  "workday_worker": "f6a7b8c9-6666-7777-8888-999900001111",
  "activity_type": "d4e5f6a7-4444-5555-6666-777788889999",
  "lot": "b2c3d4e5-2222-3333-4444-555566667777"
}
```

**Response**
```json
{
  "id": "a7b8c9d0-7777-8888-9999-000011112222",
  "workday_worker": "f6a7b8c9-6666-7777-8888-999900001111",
  "activity_type": "d4e5f6a7-4444-5555-6666-777788889999",
  "activity_name": "Recolección selectiva",
  "activity_is_harvest": true,
  "lot": "b2c3d4e5-2222-3333-4444-555566667777",
  "lot_name": "Lote Norte",
  "harvest_records": []
}
```

### 9. Pesaje de recolección (`labor.HarvestRecord`)

**Request** `POST /labor/harvest-records/`
```json
{
  "workday_detail": "a7b8c9d0-7777-8888-9999-000011112222",
  "quantity_kg": "10.500",
  "time": "10:00:00"
}
```

**Response**
```json
{
  "id": "b8c9d0e1-8888-9999-0000-111122223333",
  "workday_detail": "a7b8c9d0-7777-8888-9999-000011112222",
  "quantity_kg": "10.500",
  "time": "10:00:00",
  "settlement_status": "registrado"
}
```

### 10. Liquidación (`payroll.Settlement`)

**Crear** `POST /payroll/settlements/`
```json
{
  "worker": "c3d4e5f6-3333-4444-5555-666677778888",
  "farm": "a1b2c3d4-1111-2222-3333-444455556666",
  "start_date": "2026-10-01",
  "end_date": "2026-10-31"
}
```

**Response**
```json
{
  "id": "c9d0e1f2-9999-0000-1111-222233334444",
  "worker": "c3d4e5f6-3333-4444-5555-666677778888",
  "farm": "a1b2c3d4-1111-2222-3333-444455556666",
  "start_date": "2026-10-01",
  "end_date": "2026-10-31",
  "total_calculated": "0.00",
  "status": "abierta",
  "created_at": "2026-10-01T08:00:00Z",
  "closed_at": null,
  "paid_at": null,
  "workday_details": [],
  "harvest_details": [],
  "payment": null
}
```

**Añadir participación** `POST /payroll/settlements/add-workday/`
```json
{
  "settlement_id": "c9d0e1f2-9999-0000-1111-222233334444",
  "workday_worker_id": "f6a7b8c9-6666-7777-8888-999900001111"
}
```

**Añadir pesaje** `POST /payroll/settlements/add-harvest/`
```json
{
  "settlement_id": "c9d0e1f2-9999-0000-1111-222233334444",
  "harvest_record_id": "b8c9d0e1-8888-9999-0000-111122223333"
}
```

**Cerrar liquidación** `POST /payroll/settlements/close/`
```json
{
  "settlement_id": "c9d0e1f2-9999-0000-1111-222233334444"
}
```

**Registrar pago** `POST /payroll/settlements/pay/`
```json
{
  "settlement_id": "c9d0e1f2-9999-0000-1111-222233334444",
  "date": "2026-11-01",
  "amount_paid": "62000.00",
  "payment_method": "efectivo",
  "notes": "Pago quincenal"
}
```

**Detalle de liquidación por jornal** (`payroll.SettlementDetailWorkday`)
```json
{
  "id": "d0e1f2a3-0000-1111-2222-333344445555",
  "settlement": "c9d0e1f2-9999-0000-1111-222233334444",
  "workday_worker": "f6a7b8c9-6666-7777-8888-999900001111",
  "applied_daily_rate": "50000.00",
  "paid_amount": "50000.00"
}
```

**Detalle de liquidación por kilogramo** (`payroll.SettlementDetailHarvest`)
```json
{
  "id": "e1f2a3b4-1111-2222-3333-444455556666",
  "settlement": "c9d0e1f2-9999-0000-1111-222233334444",
  "harvest_record": "b8c9d0e1-8888-9999-0000-111122223333",
  "paid_kg": "10.500",
  "applied_kg_rate": "1200.00",
  "paid_amount": "12600.00"
}
```

**Pago laboral** (`payroll.LaborPayment`)
```json
{
  "id": "f2a3b4c5-2222-3333-4444-555566667777",
  "settlement": "c9d0e1f2-9999-0000-1111-222233334444",
  "date": "2026-11-01",
  "amount_paid": "62000.00",
  "payment_method": "efectivo",
  "notes": "Pago quincenal",
  "created_at": "2026-11-01T09:00:00Z"
}
```

**Consulta pendientes** `GET /payroll/settlements/pending/?worker=...&farm=...`
```json
{
  "worker": "c3d4e5f6-3333-4444-5555-666677778888",
  "farm": "a1b2c3d4-1111-2222-3333-444455556666",
  "period": {
    "start_date": "2026-10-01",
    "end_date": "2026-10-31"
  },
  "workday_participations": [
    {
      "id": "f6a7b8c9-6666-7777-8888-999900001111",
      "date": "2026-10-15",
      "farm": "a1b2c3d4-1111-2222-3333-444455556666",
      "payment_mode": "jornal",
      "agreed_rate": "50000.00",
      "settlement_status": "pendiente"
    }
  ],
  "harvest_records": [
    {
      "id": "b8c9d0e1-8888-9999-0000-111122223333",
      "date": "2026-10-16",
      "farm": "a1b2c3d4-1111-2222-3333-444455556666",
      "quantity_kg": "10.000",
      "agreed_rate": "1200.00",
      "settlement_status": "registrado"
    }
  ],
  "totals": {
    "workday_amount": "50000.00",
    "harvest_amount": "12000.00",
    "total": "62000.00"
  }
}
```

### 11. Egreso operativo (`finance.OperatingExpense`)

**Request** `POST /finance/expenses/`
```json
{
  "farm": "a1b2c3d4-1111-2222-3333-444455556666",
  "date": "2026-10-20",
  "concept": "Compra de abono orgánico",
  "amount": "45000.00",
  "category": "inputs"
}
```

**Response**
```json
{
  "id": "a3b4c5d6-3333-4444-5555-666677778888",
  "farm": "a1b2c3d4-1111-2222-3333-444455556666",
  "farm_name": "El Porvenir",
  "labor_payment": null,
  "date": "2026-10-20",
  "concept": "Compra de abono orgánico",
  "amount": "45000.00",
  "category": "inputs",
  "created_at": "2026-10-20T08:00:00Z",
  "updated_at": "2026-10-20T08:00:00Z"
}
```

### 12. Venta de café (`production.Sale`)

**Request** `POST /production/sales/`
```json
{
  "farm": "a1b2c3d4-1111-2222-3333-444455556666",
  "sale_date": "2026-10-25",
  "coffee_type": "pergamino",
  "quantity_kg": "25.00",
  "unit_price": "18000.00",
  "buyer": "Comercial Café del Valle",
  "notes": "Venta de octubre"
}
```

**Response**
```json
{
  "id": "b4c5d6e7-4444-5555-6666-777788889999",
  "farm": "a1b2c3d4-1111-2222-3333-444455556666",
  "sale_date": "2026-10-25",
  "coffee_type": "pergamino",
  "quantity_kg": "25.00",
  "unit_price": "18000.00",
  "total_amount": "450000.00",
  "buyer": "Comercial Café del Valle",
  "notes": "Venta de octubre",
  "is_active": true,
  "created_at": "2026-10-25T08:00:00Z",
  "updated_at": "2026-10-25T08:00:00Z"
}
```

### 13. Asistente de IA (`assistant`)

**Request** `POST /assistant/ask/`
```json
{
  "question": "¿Cuánto café coseché este mes?",
  "history": [
    { "role": "user", "content": "Hola" },
    { "role": "assistant", "content": "Hola, ¿en qué te puedo ayudar?" }
  ]
}
```

**Response**
```json
{
  "answer": "Este mes cosechaste un total de 145.5 kg de café en el lote Norte..."
}
```

### 14. Sincronización (`synchronization`)

**Push** `POST /sync/push/`
```json
{
  "operations": [
    {
      "op_id": "c5d6e7f8-5555-6666-7777-888899990000",
      "entity": "harvest_record",
      "action": "create",
      "object_id": null,
      "data": { "workday_detail": "...", "quantity_kg": "10.500", "time": "10:00:00" },
      "client_ts": "2026-10-20T10:00:00Z"
    }
  ]
}
```

**Response**
```json
{
  "results": [
    {
      "op_id": "c5d6e7f8-5555-6666-7777-888899990000",
      "status": "applied",
      "object_id": "b8c9d0e1-8888-9999-0000-111122223333",
      "http_status": 201
    }
  ],
  "server_time": "2026-10-20T10:05:00Z"
}
```

**Pull** `GET /sync/pull/`
```json
{
  "data": { ... },
  "server_time": "2026-10-20T10:05:00Z"
}
```

**Ping** `GET /sync/ping/`
```json
{
  "ok": true,
  "server_time": "2026-10-20T10:05:00Z"
}
```

---

## Flujo recomendado (mano de obra → liquidación → pago)

1. Crear la jornada (`POST /labor/workdays/`).
2. Registrar participaciones (`POST /labor/workday-workers/`).
3. Registrar detalles (`POST /labor/workday-details/`) y pesajes (`POST /labor/harvest-records/`).
4. Cerrar la jornada (`POST /labor/workdays/{id}/close/`).
5. Consultar pendientes (`GET /payroll/settlements/pending/`).
6. Crear la liquidación (`POST /payroll/settlements/`).
7. Añadir participaciones y pesajes (`add-workday`, `add-harvest`).
8. Cerrar la liquidación (`close`) y registrar el pago (`pay`).

---

## Administración de Django

El panel administrativo está en `/admin/`. Crear una cuenta con `python manage.py createsuperuser` y ejecutar el servidor de desarrollo.

Solo se permiten borrados lógicos (desactivar) en lugar de eliminar físicamente cuando existen registros asociados, para conservar el historial.
# Backend de gestión cafetera

API REST para apoyar la administración de fincas cafeteras: organiza fincas y lotes, registra trabajadores, labores y recolecciones, liquida pagos laborales y controla ventas y egresos operativos. Los productores acceden a sus propios datos y los administradores pueden consultar y gestionar los recursos del sistema.

## Tecnologías

- Python y Django 6.1.
- Django REST Framework (DRF) para la API.
- Simple JWT para autenticación con tokens Bearer.
- SQLite como base de datos configurada por defecto.
- `django-cors-headers` para configuración CORS.

Las dependencias y versiones están listadas en [`requirements.txt`](requirements.txt).

## Requisitos

- Python compatible con la versión de Django indicada en `requirements.txt`.
- `pip`.

## Instalación y ejecución local

Ejecuta los comandos desde la carpeta raíz del proyecto.

### Linux o macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

La API queda disponible en `http://127.0.0.1:8000/` y el panel administrativo en `http://127.0.0.1:8000/admin/`.

Si se modifican los modelos, genera primero las migraciones y después aplícalas:

```bash
python manage.py makemigrations
python manage.py migrate
```

Para crear un usuario administrador local:

```bash
python manage.py createsuperuser
```

El proyecto usa SQLite (`db.sqlite3`) por defecto. La configuración actual es para desarrollo; antes de desplegarlo en producción se deben configurar apropiadamente, entre otros, `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, CORS y la base de datos.

## Autenticación

La mayoría de los endpoints requiere un token JWT. Inicia sesión en `POST /accounts/login/` con correo y contraseña. Envía el token de acceso en las peticiones protegidas:

```http
Authorization: Bearer <access_token>
```

El token de acceso dura un día y el de refresco treinta días, de acuerdo con la configuración vigente. Los permisos aíslan los datos por productor; los usuarios administradores tienen acceso global en los módulos que implementan ese permiso.

## Módulos y endpoints implementados

Los endpoints de abajo se muestran relativos a `http://127.0.0.1:8000`. Los ViewSets CRUD indican los métodos estándar de DRF: `GET` para listar y consultar por identificador, `POST` para crear, `PUT`/`PATCH` para actualizar y `DELETE` para eliminar, salvo que se indique una restricción. Los identificadores de los recursos principales son UUID.

### Cuentas y usuarios — `/accounts/`

Registro, inicio de sesión, perfil, cambio de contraseña y administración de cuentas. El registro público crea productores; la administración del catálogo de usuarios está restringida a administradores.

| Endpoint | Métodos | Descripción |
|---|---|---|
| `/accounts/register/` | `POST` | Registra un productor. |
| `/accounts/login/` | `POST` | Inicia sesión con correo y contraseña; devuelve tokens y datos básicos del usuario y su rol. |
| `/accounts/token/refresh/` | `POST` | Renueva el token de acceso usando un token de refresco. La rotación está habilitada. |
| `/accounts/token/verify/` | `POST` | Verifica un token. |
| `/accounts/profile/` | `GET`, `PUT`, `PATCH` | Consulta o actualiza el perfil del usuario autenticado. |
| `/accounts/change-password/` | `PUT`, `PATCH` | Cambia la contraseña validando la contraseña actual y las reglas de Django. |
| `/accounts/users/` | `GET`, `POST` | Lista usuarios o crea una cuenta con rol. Solo administradores. |
| `/accounts/users/{id}/` | `GET`, `PUT`, `PATCH` | Consulta o actualiza una cuenta. Solo administradores; no hay borrado físico. |
| `/accounts/users/{id}/deactivate/` | `POST` | Desactiva una cuenta sin eliminarla. Solo administradores. |
| `/accounts/users/{id}/activate/` | `POST` | Reactiva una cuenta. Solo administradores. |

### Fincas y lotes — `/farms/`

Permite administrar fincas y sus lotes. Un productor solo consulta los recursos que le pertenecen; el administrador puede consultar todos. Una finca o lote con registros asociados puede no admitir borrado para preservar la integridad del historial.

| Endpoint | Métodos | Descripción |
|---|---|---|
| `/farms/` y `/farms/{id}/` | CRUD | Lista, crea, consulta, actualiza o elimina fincas. |
| `/farms/lots/` y `/farms/lots/{id}/` | CRUD | Administra lotes, su variedad, área, descripción y estado activo. |

### Mano de obra — `/labor/`

Gestiona trabajadores, tipos de actividad, jornadas, detalles de labores por lote y registros de pesaje de café. Las jornadas relacionan un trabajador con una fecha y modalidad de pago; cada detalle vincula jornada, actividad y lote.

**Campos de entrada por ruta:**

| Ruta | Campo | Requerido | Descripción |
|---|---|---|---|
| `POST /labor/workdays/` | `farm` | Sí | UUID de la finca (debe pertenecer al productor autenticado). |
| | `date` | Sí | Fecha de la jornada (`AAAA-MM-DD`). No se aceptan fechas futuras. |
| `POST /labor/workdays/{id}/close/` | — | — | Sin cuerpo. Cierra la jornada (`status: cerrada`, `closed_at`). |
| `PATCH /labor/workdays/{id}/labor/` | `activity_type`, `payment_mode`, `agreed_rate` | Sí | Actualiza actividad, modalidad y tarifa de todas las participaciones no anuladas y sus detalles. Solo jornadas abiertas; rechaza participaciones bloqueadas y cambios incompatibles con pesajes. |
| `POST /labor/workday-workers/` | `workday` | Sí | UUID de la jornada (debe estar abierta). |
| | `worker` | Sí | UUID del trabajador (debe estar activo y pertenecer al productor). |
| | `payment_mode` | Sí | `"jornal"` o `"kg"`. |
| | `agreed_rate` | Sí | Tarifa acordada, debe ser mayor que cero. |
| `POST /labor/workday-workers/{id}/cancel/` | — | — | Sin cuerpo. Solo si la participación está pendiente. |
| `POST /labor/workday-workers/{id}/reactivate/` | — | — | Sin cuerpo. Reactiva una participación anulada si el trabajador sigue activo y la jornada continúa abierta. |
| `POST /labor/workday-details/` | `workday_worker` | Sí | UUID de la participación (jornada abierta, participación pendiente). |
| | `activity_type` | Sí | UUID de la actividad (debe pertenecer al productor). |
| | `lot` | Sí | UUID del lote (debe pertenecer a la finca de la jornada y estar activo). |
| `POST /labor/harvest-records/` | `workday_detail` | Sí | UUID del detalle de jornada (actividad de recolección). |
| | `quantity_kg` | Sí | Cantidad en kilogramos, debe ser mayor que cero. |
| | `time` | Sí | Hora del pesaje (`HH:MM:SS`). |
| `POST /labor/harvest-records/{id}/cancel/` | — | — | Sin cuerpo. Solo si el pesaje está registrado (no liquidado). |

| Endpoint | Métodos | Descripción |
|---|---|---|
| `/labor/workers/` y `/labor/workers/{id}/` | CRUD | Registra y administra trabajadores del productor. Los trabajadores con historial deben desactivarse en lugar de eliminarse. |
| `/labor/activity-types/` y `/labor/activity-types/{id}/` | CRUD | Define actividades, diferenciando las de recolección mediante `is_harvest`. |
| `/labor/workdays/` y `/labor/workdays/{id}/` | CRUD | Registra y consulta jornadas, tarifa, fecha y modalidad (`jornal` o `kg`). |
| `/labor/workdays/{id}/close/` | `POST` | Cierra la jornada (`status: cerrada`, `closed_at`). Una jornada cerrada no admite cambios ni registros nuevos; solo las jornadas cerradas pueden liquidarse. |
| `/labor/workdays/{id}/labor/` | `PATCH` | Actualiza atómicamente actividad, modalidad de pago y tarifa en todas las participaciones no anuladas y sus detalles de una jornada abierta. Requiere `activity_type`, `payment_mode` y `agreed_rate`; rechaza participaciones bloqueadas y no permite cambiar a pago por jornal si hay pesajes asociados. |
| `/labor/workday-workers/` y `/labor/workday-workers/{id}/` | CRUD | Registra la participación de un trabajador en una jornada, con modalidad, tarifa acordada y estado de liquidación. |
| `/labor/workday-workers/{id}/cancel/` | `POST` | Anula una participación pendiente. No se puede anular si ya fue liquidada o incluida en una liquidación. |
| `/labor/workday-workers/{id}/reactivate/` | `POST` | Reactiva una participación anulada en una jornada abierta. No se permite si el trabajador está inactivo o la participación está liquidada/incluida en una liquidación. |
| `/labor/workday-details/` y `/labor/workday-details/{id}/` | CRUD | Asocia una actividad y un lote a una jornada. |
| `/labor/harvest-records/` y `/labor/harvest-records/{id}/` | CRUD | Registra pesajes de recolección en kilogramos asociados a detalles de jornada de una actividad marcada como recolección. |
| `/labor/harvest-records/{id}/cancel/` | `POST` | Anula un pesaje registrado. No se puede anular si ya fue liquidado. |

Los listados están filtrados por productor. El sistema también valida la propiedad de trabajadores, fincas y lotes, la actividad de recolección y el uso de lotes activos al crear los registros correspondientes.

**Ejemplos de petición y respuesta:**

```json
POST /labor/workdays/
{
  "farm": "UUID_DE_LA_FINCA",
  "date": "2026-10-20"
}
```

```json
// Respuesta 201
{
  "id": "UUID_JORNADA",
  "producer": "UUID_PRODUCTOR",
  "farm": "UUID_DE_LA_FINCA",
  "farm_name": "El Porvenir",
  "date": "2026-10-20",
  "status": "abierta",
  "closed_at": null,
  "created_at": "2026-10-20T08:00:00Z"
}
```

```json
POST /labor/workdays/{UUID_JORNADA}/close/
// sin cuerpo
```

```json
// Respuesta 200
{
  "id": "UUID_JORNADA",
  "producer": "UUID_PRODUCTOR",
  "farm": "UUID_DE_LA_FINCA",
  "farm_name": "El Porvenir",
  "date": "2026-10-20",
  "status": "cerrada",
  "closed_at": "2026-10-20T17:00:00Z",
  "created_at": "2026-10-20T08:00:00Z"
}
```

```json
POST /labor/workday-workers/
{
  "workday": "UUID_DE_LA_JORNADA",
  "worker": "UUID_DEL_TRABAJADOR",
  "payment_mode": "jornal",
  "agreed_rate": "50000.00"
}
```

```json
POST /labor/workday-details/
{
  "workday_worker": "UUID_DE_LA_PARTICIPACION",
  "activity_type": "UUID_DEL_TIPO_DE_ACTIVIDAD",
  "lot": "UUID_DEL_LOTE"
}
```

```json
POST /labor/harvest-records/
{
  "workday_detail": "UUID_DETALLE",
  "quantity_kg": "10.000",
  "time": "10:00:00"
}
```

### Liquidaciones y pagos — `/payroll/`

Calcula y conserva liquidaciones laborales, sus detalles por jornal o kilogramo y sus pagos. Los detalles y pagos se consultan en modo de solo lectura; se crean a través de las acciones de liquidación para aplicar las reglas de negocio.

**Campos de entrada por ruta:**

| Ruta | Campo | Requerido | Descripción |
|---|---|---|---|
| `POST /payroll/settlements/` | `worker` | Sí | UUID del trabajador (debe pertenecer al productor). |
| | `farm` | Sí | UUID de la finca (debe pertenecer al mismo productor). |
| | `start_date` | Sí | Fecha de inicio del periodo (`AAAA-MM-DD`). |
| | `end_date` | Sí | Fecha fin del periodo (`AAAA-MM-DD`). Debe ser >= `start_date`. |
| `GET /payroll/settlements/pending/` | `worker` | Sí | UUID del trabajador (query param). |
| | `farm` | Sí | UUID de la finca (query param). |
| | `start_date` | No | Fecha inicio opcional para filtrar pendientes. |
| | `end_date` | No | Fecha fin opcional para filtrar pendientes. |
| `POST /payroll/settlements/add-workday/` | `settlement_id` | Sí | UUID de la liquidación abierta. |
| | `workday_worker_id` | Sí | UUID de la participación (jornada cerrada, pendiente). |
| `POST /payroll/settlements/add-harvest/` | `settlement_id` | Sí | UUID de la liquidación abierta. |
| | `harvest_record_id` | Sí | UUID del pesaje (jornada cerrada, registrado). |
| `POST /payroll/settlements/close/` | `settlement_id` | Sí | UUID de la liquidación abierta. |
| `POST /payroll/settlements/pay/` | `settlement_id` | Sí | UUID de la liquidación `liquidada`. |
| | `date` | Sí | Fecha del pago (`AAAA-MM-DD`). |
| | `amount_paid` | Sí | Importe a pagar, debe ser > 0 e igual al total calculado. |
| | `payment_method` | Sí | `"efectivo"`, `"transferencia"` o `"otro"`. |
| | `notes` | No | Notas del pago (texto opcional). |
| `POST /payroll/settlements/cancel/` | `settlement_id` | Sí | UUID de la liquidación abierta sin detalles. |

| Endpoint | Métodos | Descripción |
|---|---|---|
| `/payroll/settlements/` y `/payroll/settlements/{id}/` | CRUD con restricciones | Crea y consulta liquidaciones. Solo se puede modificar o eliminar una liquidación abierta y sin detalles; las liquidadas, pagadas y anuladas conservan su historial. |
| `/payroll/settlements/pending/` | `GET` | Consulta registros pendientes de liquidar. Requiere `worker` y `farm`; opcionalmente `start_date` y `end_date`. Solo incluye jornadas cerradas. |
| `/payroll/settlements/add-workday/` | `POST` | Añade una participación (`workday_worker_id`) liquidable por jornal a una liquidación. La jornada debe estar cerrada. |
| `/payroll/settlements/add-harvest/` | `POST` | Añade un pesaje liquidable por kilogramo a una liquidación. La jornada debe estar cerrada. |
| `/payroll/settlements/close/` | `POST` | Cierra una liquidación, calcula su total y la pasa a `liquidada`. Rechaza liquidaciones vacías o con total cero. |
| `/payroll/settlements/pay/` | `POST` | Registra el pago exacto de una liquidación `liquidada` y la pasa a `pagada`. El importe debe ser mayor que cero. |
| `/payroll/settlements/cancel/` | `POST` | Anula una liquidación abierta sin detalles. |
| `/payroll/settlement-workdays/` y `/payroll/settlement-workdays/{id}/` | `GET` | Consulta detalles de liquidación por jornal. |
| `/payroll/settlement-harvests/` y `/payroll/settlement-harvests/{id}/` | `GET` | Consulta detalles de liquidación por kilogramo. |
| `/payroll/payments/` y `/payroll/payments/{id}/` | `GET` | Consulta pagos laborales registrados. |

Estados de una liquidación: `abierta`, `liquidada`, `pagada` y `anulada`.

Estados de participación (`settlement_status` en `labor_workdayworker`): `pendiente`, `liquidado`, `anulado`.

Estados de pesaje (`settlement_status` en `labor_harvestrecord`): `registrado`, `liquidado`, `anulado`.

**Ejemplos de petición y respuesta:**

Crear liquidación:

```json
POST /payroll/settlements/
{
  "worker": "UUID_TRABAJADOR",
  "farm": "UUID_FINCA",
  "start_date": "2026-10-01",
  "end_date": "2026-10-31"
}
```

Respuesta:

```json
{
  "id": "UUID_LIQUIDACION",
  "worker": "UUID_TRABAJADOR",
  "farm": "UUID_FINCA",
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

Consultar pendientes:

```http
GET /payroll/settlements/pending/?worker=UUID_TRABAJADOR&farm=UUID_FINCA&start_date=2026-10-01&end_date=2026-10-31
```

Respuesta:

```json
{
  "worker": "UUID_TRABAJADOR",
  "farm": "UUID_FINCA",
  "period": {
    "start_date": "2026-10-01",
    "end_date": "2026-10-31"
  },
  "workday_participations": [
    {
      "id": "UUID_PARTICIPACION",
      "date": "2026-10-15",
      "farm": "UUID_FINCA",
      "payment_mode": "jornal",
      "agreed_rate": "50000.00",
      "settlement_status": "pendiente"
    }
  ],
  "harvest_records": [
    {
      "id": "UUID_PESAJE",
      "date": "2026-10-16",
      "farm": "UUID_FINCA",
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

Añadir participación a liquidación:

```json
POST /payroll/settlements/add-workday/
{
  "settlement_id": "UUID_LIQUIDACION",
  "workday_worker_id": "UUID_PARTICIPACION"
}
```

Añadir pesaje a liquidación:

```json
POST /payroll/settlements/add-harvest/
{
  "settlement_id": "UUID_LIQUIDACION",
  "harvest_record_id": "UUID_PESAJE"
}
```

Cerrar liquidación:

```json
POST /payroll/settlements/close/
{
  "settlement_id": "UUID_LIQUIDACION"
}
```

Registrar pago:

```json
POST /payroll/settlements/pay/
{
  "settlement_id": "UUID_LIQUIDACION",
  "date": "2026-11-01",
  "amount_paid": "62000.00",
  "payment_method": "efectivo",
  "notes": "Pago en efectivo quincenal"
}
```

Anular liquidación:

```json
POST /payroll/settlements/cancel/
{
  "settlement_id": "UUID_LIQUIDACION_ABIERTA"
}
```

El endpoint de creación de liquidaciones valida que trabajador y finca correspondan al mismo productor y que no exista otra liquidación abierta para el mismo trabajador y finca.

El flujo recomendado es: crear la jornada, registrar participaciones, detalles y pesajes, cerrar la jornada, consultar `pending`, crear la liquidación, añadir sus registros, cerrarla y registrar el pago.

### Finanzas — `/finance/`

Registra egresos operativos de cada finca (mano de obra, insumos, herramientas y materiales, transporte, servicios u otros). Los egresos asociados a pagos de nómina se generan mediante el registro del pago en `payroll`.

| Endpoint | Métodos | Descripción |
|---|---|---|
| `/finance/expenses/` y `/finance/expenses/{id}/` | `GET`, `POST`, `PUT`, `PATCH` | Lista, filtra, crea y actualiza egresos. No admite `DELETE` para conservar el historial. |

Filtros disponibles en el listado: `category`, `farm` (UUID), `date_from` y `date_to` (`AAAA-MM-DD`).

### Producción y ventas — `/production/`

Administra ventas de café y consolida la producción registrada mediante los pesajes del módulo de mano de obra. Las ventas se desactivan en vez de eliminarse; las consultas de ventas consideran registros activos.

| Endpoint | Métodos | Descripción |
|---|---|---|
| `/production/sales/` y `/production/sales/{id}/` | CRUD (borrado lógico) | Registra y administra ventas de café por finca, tipo, cantidad y precio. El total se calcula automáticamente. |
| `/production/sales/revenue-by-farm/` | `GET` | Resume ingresos por ventas agrupados por finca. |
| `/production/production/by-farm/` | `GET` | Resume la producción en kilogramos y el número de pesajes por finca. |
| `/production/production/by-lot/` | `GET` | Resume la producción en kilogramos y el número de pesajes por lote. |

Los endpoints de resumen aceptan filtros opcionales `farm_id`, `lot_id`, `year` y `month`, según corresponda a cada resumen. El acceso a las fincas y lotes sigue el aislamiento por productor.

## Administración de Django

El panel administrativo está disponible en `/admin/`. Para acceder, crea una cuenta con `python manage.py createsuperuser` y ejecuta el servidor de desarrollo.

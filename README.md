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

| Endpoint | Métodos | Descripción |
|---|---|---|
| `/labor/workers/` y `/labor/workers/{id}/` | CRUD | Registra y administra trabajadores del productor. Los trabajadores con historial deben desactivarse en lugar de eliminarse. |
| `/labor/activity-types/` y `/labor/activity-types/{id}/` | CRUD | Define actividades, diferenciando las de recolección mediante `is_harvest`. |
| `/labor/workdays/` y `/labor/workdays/{id}/` | CRUD | Registra y consulta jornadas, tarifa, fecha y modalidad (`jornal` o `kg`). |
| `/labor/workday-details/` y `/labor/workday-details/{id}/` | CRUD | Asocia una actividad y un lote a una jornada. |
| `/labor/harvest-records/` y `/labor/harvest-records/{id}/` | CRUD | Registra pesajes de recolección en kilogramos asociados a detalles de jornada de una actividad marcada como recolección. |

Los listados están filtrados por productor. El sistema también valida la propiedad de trabajadores, fincas y lotes, la actividad de recolección y el uso de lotes activos al crear los registros correspondientes.

### Liquidaciones y pagos — `/payroll/`

Calcula y conserva liquidaciones laborales, sus detalles por jornal o kilogramo y sus pagos. Los detalles y pagos se consultan en modo de solo lectura; se crean a través de las acciones de liquidación para aplicar las reglas de negocio.

| Endpoint | Métodos | Descripción |
|---|---|---|
| `/payroll/settlements/` y `/payroll/settlements/{id}/` | CRUD con restricciones | Crea y consulta liquidaciones abiertas. Solo se puede modificar o eliminar una liquidación abierta; las cerradas o pagadas conservan su historial. |
| `/payroll/settlements/add-workday/` | `POST` | Añade una jornada liquidable por jornal a una liquidación. |
| `/payroll/settlements/add-harvest/` | `POST` | Añade un pesaje liquidable por kilogramo a una liquidación. |
| `/payroll/settlements/close/` | `POST` | Cierra una liquidación y calcula su total. |
| `/payroll/settlements/pay/` | `POST` | Registra el pago de una liquidación cerrada. |
| `/payroll/settlement-workdays/` y `/payroll/settlement-workdays/{id}/` | `GET` | Consulta detalles de liquidación por jornal. |
| `/payroll/settlement-harvests/` y `/payroll/settlement-harvests/{id}/` | `GET` | Consulta detalles de liquidación por kilogramo. |
| `/payroll/payments/` y `/payroll/payments/{id}/` | `GET` | Consulta pagos laborales registrados. |

El endpoint de creación de liquidaciones valida que trabajador y finca correspondan al mismo productor y que no exista otra liquidación abierta para el trabajador.

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

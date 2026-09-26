# Especificación Técnica de Referencia: Internos, Arquitectura y Guía de Refactorización de web2py

> **Propósito del Documento:**  
> Este documento sirve como una **guía de referencia técnica de nivel de arquitectura e implementación del core de web2py** para ser consumida por modelos de Inteligencia Artificial (p. ej., Claude, GPT-4) y desarrolladores senior. Su objetivo principal es permitir el análisis profundo, mantenimiento, corrección de bugs, refactorización y modernización del repositorio oficial de **web2py** (excluyendo migraciones a py4web o frameworks externos).

---

## Convenciones del Documento

Para facilitar la audición y reescritura de código, la información en cada sección se clasifica de la siguiente manera:
* **[Oficial / Documentado]:** Comportamiento vigente de la API y diseño estándar expuesto en la documentación del framework.
* **[Legacy / Histórico]:** Módulos, patrones, sintaxis obsoletas o mecanismos heredados de compatibilidad con Python 2/versiones antiguas de web2py.
* **[Target de Refactorización / IA Prompting]:** Puntos críticos del código fuente, deuda técnica, oportunidades de tipado estático, modernización para Python 3.9+ y cuellos de botella para una IA que analice o refactorice el repositorio.

---

## 1. Arquitectura General de web2py

### [Oficial / Documentado]
web2py es un framework web monolítico, full-stack, basado en el estándar **WSGI (PEP 3333)**. Su diseño principal difiere de la mayoría de los frameworks Python modernos (como Django o Flask) en cómo administra la ejecución del código de las aplicaciones:

1. **Monolito WSGI Multi-aplicación:** Un único proceso de web2py puede hospedar e independizar múltiples aplicaciones alojadas bajo el directorio `applications/`. La aplicación WSGI central reside en `gluon.main.wsgibase`.
2. **Entorno Inyectado Dinámicamente:** web2py **no utiliza la sintaxis tradicional de importación de módulos Python** (`import ...`) en los modelos, controladores y vistas de las aplicaciones. En su lugar, el framework lee el código fuente como archivos de texto y los ejecuta dinámicamente (`eval`/`exec`) dentro de un espacio de nombres pre-poblado (*built-in execution environment*) generado por `gluon.compileapp.build_environment`.
3. **Persistencia Desacoplada (PyDAL):** El motor de abstracción de base de datos es **PyDAL** (`pydal`), una librería independiente integrada en web2py como submódulo Git ubicado en `gluon/packages/dal`.
4. **Garantía de Aislamiento por Petición (Thread-Locals):** Dado que el estado global (`request`, `response`, `session`, `cache`, `T`) se inyecta dinámicamente en el entorno de cada petición, web2py utiliza un objeto *thread-local* unificado llamado `gluon.globals.current` para garantizar que peticiones concurrentes en hilos distintos no contaminen sus contextos.

### [Legacy / Histórico]
* **Sintaxis de importación heredada:** En versiones antiguas (Python 2.x), los modelos y controladores dependían enteramente de manipular `globals()` implícitos.
* **`gluon.sql`:** Capa de abstracción de base de datos previa a PyDAL (`SQLDB`, `SQLField`). Conservada exclusivamente por compatibilidad hacia atrás.

### [Target de Refactorización / IA Prompting]
* **Inyección de Dependencias vs. Scope Dinámico:** La ejecución basada en `exec()` en `gluon.compileapp` dificulta el análisis estático de código (linter, mypy, IDEs) y dificulta el refactoring automatizado.
* **Modernización Sugerida:** Mantener la retrocompatibilidad del sandbox dinámico para aplicaciones existentes, pero refactorizar los módulos internos de `gluon/` para que utilicen Type Hints estrictos (`typing.TypedDict`, `typing.Protocol`, `dataclasses`).

---

## 2. Flujo de una Petición HTTP (Pipeline de Ejecución)

### [Oficial / Documentado]

El ciclo de vida de una petición HTTP en web2py sigue un orden secuencial rígido orquestado por `gluon.main.wsgibase`:

```
[Cliente HTTP] 
      │
      ▼
[Servidor WSGI] (Rocket / Gunicorn / uWSGI / Apache)
      │
      ▼
1. gluon.main.wsgibase(environ, start_response)
      │
      ├─► Instancia objeto Request, Response, Session (gluon.globals)
      ├─► Asigna thread-local: gluon.globals.current
      │
2. gluon.rewrite.url_in(request, environ)
      │
      ├─► Resuelve PATH_INFO ──► (application, controller, function, extension)
      │
3. ¿Es archivo estático? (/app/static/...)
      ├── SI ─► gluon.streamer.stream_file_or_304() ──► [Respuesta Directa]
      └── NO ─► Continúa pipeline
      │
4. Recuperación de Sesión (Session.connect)
      │
      ├─► Lee cookie de sesión (response.session_id_name)
      ├─► Carga datos de sesión (File / DB / Redis / Memcached)
      │
5. Inyección de Entorno y Ejecución de Modelos (gluon.compileapp)
      │
      ├─► Construye el entorno dinámico (build_environment)
      ├─► Ejecuta models/*.py en ORDEN ALFABÉTICO estricto
      ├─► Ejecuta modelos condicionales (models/<controller>/*.py)
      │
6. Ejecución del Controlador (gluon.compileapp.run_controller_in)
      │
      ├─► Evalúa controllers/<controller>.py
      ├─► Invoca la función pública de la acción: function(*request.args, **request.vars)
      │
7. Renderizado de la Vista (gluon.template)
      │
      ├─► Si la acción retorna `dict`:
      │     Carga views/<controller>/<function>.<extension>
      │     Compila y ejecuta la plantilla en el entorno combinado
      ├─► Si la acción retorna `str` o Helper (DIV, FORM):
      │     Lo serializa directamente a HTML/Texto
      │
8. Cierre de Transacción y Respuesta
      │
      ├─► db.commit() automático en todas las conexiones PyDAL abiertas
      ├─► Guarda la sesión (si fue modificada y no se llamó session.forget())
      └─► Retorna iterable WSGI al cliente
```

#### Captura de Excepciones y Sistema de Tickets:
* Si ocurre una excepción no capturada durante la ejecución de modelos, controladores o vistas:
  1. Se ejecuta `db.rollback()` en todas las instancias DAL activas.
  2. Se captura el Traceback completo mediante `gluon.restricted.RestrictedError`.
  3. Se genera un **Ticket de Error** archivado en `applications/<app>/errors/<ticket_id>`.
  4. Se retorna al cliente una página HTTP 500 informando únicamente el ID del ticket (impidiendo la fuga de información sensible).

### [Legacy / Histórico]
* Manejo manual de sockets en servidores CGI/FastCGI legados (`cgihandler.py`, `fcgihandler.py`).

### [Target de Refactorización / IA Prompting]
* **`gluon.main.wsgibase`** es una función extensa con alta complejidad ciclomática. Reestructurar el pipeline en middleware desacoplados (Parsing -> Routing -> Session -> Model Exec -> Action Exec -> Render -> Commit) mejoraría significativamente la mantenibilidad.

---

## 3. Estructura de Directorios del Repositorio y de Aplicaciones

### [Oficial / Documentado]

#### Estructura del Repositorio Raíz (`web2py/`):
```
web2py/
├── web2py.py                  # Script principal de inicio (CLI y GUI Tkinter)
├── anyserver.py               # Adaptador genérico para servidores WSGI de terceros
├── VERSION                    # Archivo de versión semántica (e.g., 2.27.1-stable)
├── gluon/                     # El NÚCLEO del framework (Librerías del sistema)
│   ├── packages/              # Submódulos desacoplados
│   │   └── dal/               # Repositorio oficial PyDAL (pydal)
│   ├── contrib/               # Librerías de terceros empacadas (memcache, redis, markmin, etc.)
│   └── tests/                 # Pruebas unitarias integradas
├── applications/              # Aplicaciones alojadas en esta instancia
│   ├── admin/                 # IDE basado en web y gestor de base de datos
│   ├── examples/              # Documentación interactiva y réplica del sitio oficial
│   └── welcome/               # Aplicación plantilla (scaffolding app)
├── handlers/                  # Conectores WSGI y servidores web
│   ├── wsgihandler.py         # Handler oficial WSGI para producción
│   ├── gaehandler.py          # Handler para Google App Engine
│   └── fcgihandler.py        # Handler FastCGI
├── scripts/                   # Scripts de mantenimiento, despliegue y CLI
│   ├── setup-web2py-ubuntu.sh # Scripts de automoción
│   ├── tickets2db.py          # Agregador de tickets a BD
│   └── sessions2trash.py      # Limpiador de sesiones caducadas
├── deposit/                   # Almacenamiento temporal para empaquetado/desempaquetado .w2p
└── site-packages/             # Módulos Python adicionales en el sys.path local
```

#### Estructura Interna de una Aplicación (`applications/<app_name>/`):
* `models/`: Archivos `.py` ejecutados automáticamente en cada petición en orden alfabético.
* `controllers/`: Archivos `.py` que exponen funciones públicas como acciones URL.
* `views/`: Plantillas HTML/Jinja-like (`.html`, `.load`, `.json`).
* `modules/`: Módulos Python puros pertenecientes a la aplicación. Importables mediante `import mymodule`.
* `static/`: Archivos estáticos (CSS, JS, imágenes) servidos directamente.
* `private/`: Archivos de configuración (`appconfig.ini`), llaves RSA/HMAC, scripts ejecutados por shell CLI.
* `uploads/`: Directorio donde PyDAL almacena archivos subidos por campos tipo `upload`.
* `sessions/`: Almacenamiento por defecto de archivos de sesión en disco.
* `errors/`: Archivos conteniendo tracebacks codificados de tickets emitidos.
* `databases/`: Archivos de base de datos SQLite y archivos de metadatos `.table` para control de migraciones.
* `cron/`: Archivos `crontab` y scripts para tareas programadas de background.

---

## 4. Responsabilidad de Módulos Principales (`gluon/`)

| Módulo | Ruta | Responsabilidad Principal |
| :--- | :--- | :--- |
| `gluon.main` | `gluon/main.py` | Entrada WSGI principal (`wsgibase`), gestión del ciclo de vida de la petición, captura global de excepciones y generación de tickets. |
| `gluon.compileapp` | `gluon/compileapp.py` | Motor de inyección de entorno dinámico (`build_environment`, `exec_environment`), compilación de modelos/controladores/vistas a bytecode `.pyc`. |
| `gluon.globals` | `gluon/globals.py` | Definición de objetos de estado central por petición: `Request`, `Response`, `Session`, y gestión del thread-local `current`. |
| `gluon.storage` | `gluon.storage.py` | Implementación de `Storage` (diccionario con acceso a claves vía atributos `dict.key`). |
| `gluon.rewrite` | `gluon/rewrite.py` | Motor de reescritura de URLs, parsing de `routes.py`, enrutamiento paramétrico y basado en patrones. |
| `gluon.html` | `gluon/html.py` | Constructores programáticos del DOM HTML (`DIV`, `FORM`, `INPUT`, `TABLE`, `URL`, `XML`, `BEAUTIFY`). |
| `gluon.sqlhtml` | `gluon/sqlhtml.py` | Generadores avanzados de interfaz de usuario basados en esquema PyDAL: `SQLFORM`, `SQLFORM.grid`, `SQLFORM.smartgrid`, widgets por defecto. |
| `gluon.tools` | `gluon/tools.py` | Herramientas de infraestructura de aplicación: `Auth` (RBAC), `Mail`, `Service` (RPC), `PluginManager`, `Crud` (deprecated). |
| `gluon.template` | `gluon/template.py` | Parser y compilador del motor de plantillas de web2py (reemplaza delimitadores `{{ }}` por código Python ejecutable). |
| `gluon.validators` | `gluon/validators.py` | Clases validadoras de entrada (`IS_NOT_EMPTY`, `IS_EMAIL`, `IS_IN_DB`, `IS_STRONG`, `CRYPT`, etc.). |
| `gluon.scheduler` | `gluon/scheduler.py` | Motor de tareas asíncronas en segundo plano, daemon *worker*, gestión de colas persistidas en BD. |
| `gluon.fileutils` | `gluon/fileutils.py` | Abstracción de operaciones I/O del sistema de archivos seguro (`read_file`, `write_file`, bloqueos de archivos). |
| `gluon.restricted` | `gluon/restricted.py` | Entorno de ejecución restringido para la captura e inspección sintáctica de errores. |
| `gluon.sanitizer` | `gluon/sanitizer.py` | Limpieza y desinfección de marcado HTML contra ataques XSS. |
| `gluon.streamer` | `gluon/streamer.py` | Transmisión eficiente por *chunks* de archivos estáticos y descargas. |

---

## 5. Bootstrap / Startup del Framework

### [Oficial / Documentado]

El arranque de web2py puede ejecutarse en varios modos:

1. **Modo CLI / Desarrollo (`web2py.py`):**
   * Comando: `python web2py.py -i 127.0.0.1 -p 8000 -a "password_admin"`
   * `web2py.py` inicializa las configuraciones globales en `gluon.settings.global_settings` (rutas raíz, versión de Python, modo OS).
   * Lanza el servidor WSGI multihilo integrado (**Rocket**).
   * Banderas clave de CLI:
     * `-S APPNAME`: Inicia un shell interactivo Python/IPython cargando el entorno de la aplicación `APPNAME`.
     * `-M`: Fuerza la auto-importación de modelos al iniciar el shell interactivo.
     * `-R SCRIPT`: Ejecuta un script Python dentro del entorno completo de una aplicación.
     * `-K APPNAME`: Inicia el worker del Scheduler para la aplicación especificada.
     * `-X`: Ejecuta el Scheduler en segundo plano dentro del mismo proceso del servidor web.

2. **Modo Servidor WSGI de Producción (`handlers/wsgihandler.py`):**
   * Los servidores web de producción (Nginx + uWSGI, Apache + mod_wsgi) importan la función `application` desde `wsgihandler.py`.
   * `wsgihandler.py` ajusta el `sys.path`, establece el directorio de trabajo y expone `gluon.main.wsgibase`.

3. **Adaptador para Servidores de Terceros (`anyserver.py`):**
   * Permite ejecutar web2py sobre servidores asíncronos o de alto rendimiento como Tornado, Gevent, Gunicorn, Eventlet o CherryPy.

---

## 6. System Routing y Reescritura de URLs (`gluon.rewrite`)

### [Oficial / Documentado]

web2py mapea URLs entrantes utilizando la siguiente convención por defecto:
`http://server/application/controller/function/arg1/arg2?var1=val1`

* `application`: Directorio en `applications/<application>`.
* `controller`: Archivo en `controllers/<controller>.py`.
* `function`: Función pública dentro del controlador.
* `arg1, arg2`: Capturados en `request.args` (lista de `str`).
* `var1=val1`: Capturado en `request.vars` (objeto `Storage`).

Para personalizar este comportamiento, web2py lee el archivo opcional `routes.py` ubicado en la raíz del proyecto. Existen dos sistemas mutually exclusive:

#### 1. Sistema Basado en Parámetros (`routers`):
Configuración estructurada mediante un diccionario global denominado `routers` en `routes.py`:

```python
routers = dict(
    BASE = dict(
        default_application = 'myapp',
        domains = {
            'example.com': 'myapp',
            'api.example.com': 'api_app',
        }
    ),
    myapp = dict(
        default_controller = 'default',
        default_function = 'index',
        languages = ['en', 'es', 'fr'],
        default_language = 'es',
    )
)
```
* Omite automáticamente el nombre de la aplicación y del controlador por defecto de la URL vista por el cliente.
* Inyecta detección automática de idioma agregando el prefijo `/es/` a las URLs.

#### 2. Sistema Basado en Patrones (`routes_in` / `routes_out`):
Sistemas de reglas basados en expresiones regulares o sintaxis simplificada `$variable`:

```python
routes_in = (
    ('/api/v1/$anything', '/myapp/api_v1/$anything'),
    (r'.*:\/\/.* \/robots\.txt', '/myapp/static/robots.txt'),
)
routes_out = [(x, y) for (y, x) in routes_in]
```

#### Manejo de Errores Customizados (`routes_onerror`):
Redirección interna de códigos de estado HTTP a acciones específicas sin alterar la URL en el cliente:
```python
routes_onerror = [
    ('myapp/404', '/myapp/default/custom_404'),
    ('myapp/500', '/myapp/default/custom_500'),
    ('*/*', '/myapp/error/index'),
]
```

---

## 7. Controllers y Control de Flujo de Acciones

### [Oficial / Documentado]

* Los controladores son archivos ubicados en `applications/<app>/controllers/<controller>.py`.
* **Reglas de Visibilidad:**
  * Cualquier función definida a nivel de módulo sin argumentos requeridos y que **no comience por doble guion bajo (`__`)** se expone como una acción pública accesible por URL.
  * Funciones que aceptan argumentos obligatorios o inician con `__` son privadas y devuelven HTTP 404 si se intenta acceder directamente desde la web.

#### Valores de Retorno Permitidos en una Acción:
1. `dict(...)`: Pasa los datos devueltos a la vista asociada (`views/<controller>/<function>.<extension>`).
2. `str` o `bytes`: Retorna el contenido de texto crudo directamente al cliente.
3. Helper HTML (`DIV`, `FORM`, `TABLE`): Se serializa a HTML mediante su método `.xml()`.
4. `redirect(URL(...))`: Lanza una excepción `gluon.http.HTTP(303, ...)` interrumpiendo la ejecución y forzando redirección.
5. `raise HTTP(code, detail)`: Interrumpe la ejecución e emite una respuesta HTTP arbitraria (e.g., `raise HTTP(403, "Acceso denegado")`).

---

## 8. Models y Ciclo de Vida de Definiciones DAL

### [Oficial / Documentado]

* Los modelos son scripts ubicados en `applications/<app>/models/`.
* **Orden de Ejecución:** Se evalúan en **orden alfabético estricto** en *cada petición HTTP* antes de ejecutar el controlador invocado.
* **Ámbito Global:** Todas las variables declaradas en un modelo (como instancias de `DAL`, definiciones de tablas `db.define_table(...)`, o servicios `auth`) pasan a formar parte del entorno global visible por modelos posteriores, el controlador y las vistas.

#### Modelos Condicionales (Optimización de Carga):
Para evitar ejecutar todas las definiciones de tablas en peticiones que no las necesitan, se organizan modelos en subcarpetas:
* `models/*.py` (Se ejecutan siempre).
* `models/default/*.py` (Se ejecutan únicamente si el controlador solicitado es `default`).
* `models/default/index/*.py` (Se ejecutan únicamente si la función solicitada es `index`).
* Esta regla se controla y modifica mediante la lista de expresiones regulares `response.models_to_run`.

---

## 9. Views y Motor de Plantillas (`gluon.template`)

### [Oficial / Documentado]

El motor de vistas de web2py compila archivos de plantilla HTML (`.html`) a bytecode de Python ejecutable.

#### Sintaxis de Plantillas:
* **Delimitadores:** `{{ ... }}`
* **Inyección de Código Python:**
  ```html
  {{ for item in items: }}
      <p>{{= item.name }}</p> {{# El signo '=' indica salida evaluada y escapada contra XSS }}
  {{ pass }} {{# El bloque requiere finalización explícita con pass }}
  ```
* **Herencia e Inclusión:**
  * `{{ extend 'layout.html' }}`: Hereda de una plantilla padre.
  * `{{ include 'page_header.html' }}`: Incluye una plantilla secundaria.
  * `{{ block header }} Default Content {{ end }}`: Define bloques sobrescribibles por vistas hijas.
* **Escapado Automático XSS:**
  * Por defecto, todo valor emitido con `{{= variable }}` se escapa mediante `gluon.html.xmlescape`.
  * Para emitir HTML crudo sin escapar, la variable debe envolverse explícitamente en el helper `XML`:
    `{{= XML(raw_html_string) }}`

---

## 10. DAL (Database Abstraction Layer) y PyDAL Integrado

### [Oficial / Documentado]

La capa de base de datos PyDAL (`gluon/packages/dal/pydal`) traduce sintaxis Python nativa a dialectos SQL específicos sin escribir SQL manual.

#### Instanciación y Pool de Conexiones:
```python
from pydal import DAL, Field
db = DAL('postgres://user:pass@localhost:5432/dbname', 
         pool_size=10, 
         folder='applications/myapp/databases',
         lazy_tables=False)
```

#### Definición de Esquemas y Campos:
```python
db.define_table('person',
    Field('name', 'string', length=128, required=True),
    Field('age', 'integer', default=18),
    Field('avatar', 'upload', uploadfolder='applications/myapp/uploads'),
    Field('is_active', 'boolean', default=True),
    Field.Virtual('full_info', lambda row: f"{row.name} ({row.age})")
)
```

#### Tipos de Datos Soportados por `Field`:
`string`, `text`, `integer`, `double`, `decimal`, `date`, `time`, `datetime`, `boolean`, `upload`, `blob`, `password`, `reference <tablename>`, `list:string`, `list:integer`, `list:reference <tablename>`, `json`.

#### Control de Migraciones del Esquema:
* `migrate=True` (Por defecto): Compara la definición de la tabla con los metadatos almacenados en `databases/<hash>_<tablename>.table`. Si detecta diferencias, ejecuta sentencias `ALTER TABLE` automáticamente.
* `fake_migrate=True`: Reconstruye los archivos de metadatos `.table` sin ejecutar comandos DDL en la base de datos (utilizado para reparar desincronizaciones de metadatos).
* `migrate=False`: Desactiva las verificaciones DDL (modo obligatorio para entornos de producción de alto rendimiento).

#### Submódulo de Servicios RestAPI PyDAL:
PyDAL incluye `pydal.dbapi.RestAPI`, un motor de APIs de consulta estructurada (estilo GraphQL pero controlado por políticas de servidor) que permite consultas dinámicas mediante endpoints JSON:
```python
from pydal.dbapi import RestAPI, Policy
policy = Policy()
policy.set('person', 'GET', authorize=True, allowed_patterns=['*'])
```

---

## 11. Forms, Validators y Widgets (`gluon.sqlhtml` & `gluon.validators`)

### [Oficial / Documentado]

web2py posee tres niveles de abstracción para la creación y procesamiento de formularios HTTP:

```
                  ┌──────────────────────────────┐
                  │            FORM              │  (Nivel bajo: Helpers HTML puros)
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────────┐
                  │          SQLFORM             │  (Nivel medio: Generado desde Tabla PyDAL)
                  └──────────────┬───────────────┘
                                 │
                   ┌─────────────┴──────────────┐
                   ▼                            ▼
      ┌─────────────────────────┐  ┌─────────────────────────┐
      │      SQLFORM.grid       │  │    SQLFORM.smartgrid    │ (Nivel alto: Grillas CRUD interactivas)
      └─────────────────────────┘  └─────────────────────────┘
```

#### 1. Formulario Manual de Bajo Nivel (`FORM`):
```python
form = FORM(INPUT(_name='username', requires=IS_NOT_EMPTY()),
            INPUT(_type='submit'))
if form.process().accepted:
    username = form.vars.username
```

#### 2. Formulario Basado en Esquema (`SQLFORM`):
```python
form = SQLFORM(db.person, record=record_id, deletable=True)
if form.process(onvalidation=my_custom_validation).accepted:
    response.flash = 'Registro guardado'
```

#### 3. Abstracción sin Persistencia (`SQLFORM.factory`):
Genera una interfaz `SQLFORM` idéntica pero sin requerir una tabla real en la base de datos.

#### Protecciones de Seguridad en Formularios:
* **Anti-CSRF:** `form.process()` inyecta automáticamente dos campos ocultos:
  * `_formkey`: Token único cifrado vinculado a la sesión del usuario.
  * `_formname`: Nombre del formulario para evitar colisiones cuando existen múltiples formularios en la misma página.

#### Validadores (`gluon.validators`):
Se asignan al atributo `.requires` de un campo.
* Validadores de Formato: `IS_NOT_EMPTY()`, `IS_EMAIL()`, `IS_MATCH(regex)`, `IS_URL()`, `IS_SLUG()`.
* Validadores de Seguridad: `CRYPT(hmac_key=...)`, `IS_STRONG(min=8, special=1, upper=1)`.
* Validadores de Base de Datos: `IS_IN_DB(db, 'table.field', '%(label)s')`, `IS_NOT_IN_DB(db, 'table.field')`.

---

## 12. Sessions, Cache y Authentication (RBAC)

### [Oficial / Documentado]

### 1. Sesiones (`gluon.globals.Session`)
Objeto tipo `Storage` persistido entre peticiones HTTP mediante la cookie `session_id_<appname>`.

* **Mecanismo de Bloqueo (Session Locking):**
  * Por defecto, cuando las sesiones se almacenan en disco (`applications/<app>/sessions/`), web2py bloquea de forma exclusiva el archivo de sesión durante el procesado de la petición para evitar condiciones de carrera.
  * **Peticiones Ajax Paralelas:** Si una página realiza múltiples llamadas secundarias Ajax, estas se ejecutarán secuencialmente debido al bloqueo de sesión. Para permitir concurrencia, las acciones paralelas deben liberar el bloqueo mediante:
    `session.forget(response)`

* **Estrategias de Almacenamiento de Sesión:**
  * En Disco: Por defecto.
  * En Base de Datos: `session.connect(request, response, db)` (Crea la tabla `web2py_session_<app>`).
  * En Redis: `from gluon.contrib.redis_session import RedisSession; session.connect(request, response, db=RedisSession(...))`
  * En Cookies Cifradas: `session.connect(request, response, cookie_key='secret')`

### 2. Caché (`gluon.cache`)
Proporciona dos niveles principales de almacenamiento:
* `cache.ram('key', lambda: exp_function(), time_expire=60)`
* `cache.disk('key', lambda: exp_function(), time_expire=3600)`
* Decorador de acciones: `@cache.action(time_expire=60, cache_model=cache.ram)`

### 3. Autenticación y Control de Acceso (`gluon.tools.Auth`)
Sistema de Control de Acceso Basado en Roles (RBAC).

#### Esquema de Tablas Generadas por `auth.define_tables()`:
1. `auth_user`: Credenciales y perfil del usuario (`first_name`, `last_name`, `email`, `password`, `registration_key`).
2. `auth_group`: Roles del sistema (`role`, `description`).
3. `auth_membership`: Relación N:M entre `auth_user` y `auth_group`.
4. `auth_permission`: Asignación de permisos (`group_id`, `name`, `table_name`, `record_id`).
5. `auth_event`: Audit-log de acciones de seguridad.

#### Decoradores de Protección de Acceso:
```python
@auth.requires_login()
@auth.requires_membership('admin')
@auth.requires_permission('update', db.article, record_id)
def my_action():
    return dict()
```

---

## 13. Scheduler y Background Jobs (`gluon.scheduler`)

### [Oficial / Documentado]

web2py incluye un motor de tareas asíncronas integrado que utiliza la propia base de datos de la aplicación para coordinar colas de trabajo entre múltiples procesos *workers*.

#### Configuración e Inicialización en Modelos:
```python
from gluon.scheduler import Scheduler

def my_async_task(a, b):
    return a + b

scheduler = Scheduler(db, tasks=dict(add_numbers=my_async_task))
```

#### Encolamiento de Tareas desde un Controlador:
```python
scheduler.queue_task('add_numbers', pvars=dict(a=5, b=10), timeout=120)
```

#### Ejecución de los Workers:
Los procesos *workers* se ejecutan de forma independiente fuera del proceso del servidor web:
`python web2py.py -K myapp`

#### Ciclo de Vida de una Tarea:
Estados de la tabla `scheduler_task`: `QUEUED` -> `ASSIGNED` -> `RUNNING` -> `COMPLETED` / `FAILED` / `TIMEOUT` / `EXPIRED`.

---

## 14. APIs Internas Cruciales y Thread-Locals

### [Oficial / Documentado]

### 1. `gluon.globals.current` (Thread-Local Container)
Para evitar pasar explícitamente los objetos de contexto a través de funciones o módulos creados en `applications/<app>/modules/`, web2py expone el objeto `current`:

```python
# Dentro de un módulo externo en applications/myapp/modules/custom_logic.py
from gluon import current

def get_user_ip():
    return current.request.client

def query_db():
    return current.db(current.db.person).select()
```

### 2. `gluon.storage.Storage`
Un sub-clase de `dict` de Python que sobrecarga `__getattr__` y `__setattr__`. Permite acceder a llaves mediante sintaxis de punto (`d.key` en lugar de `d['key']`). Si la llave no existe, devuelve `None` en lugar de lanzar `KeyError`.

### 3. `gluon.compileapp.exec_environment`
Permite ejecutar modelos o controladores de cualquier aplicación web2py de forma programática y extraer su espacio de nombres:
```python
from gluon.compileapp import exec_environment
env = exec_environment('applications/myapp/models/db.py')
db = env.db
```

### 4. Generación de URLs (`gluon.html.URL`)
```python
URL('default', 'index', args=['1', '2'], vars=dict(search='text'), scheme=True, user_signature=True)
```

---

## 15. Sistema de Plugins (`PluginManager`)

### [Oficial / Documentado]

Un plugin en web2py es un conjunto de archivos autónomos diseñados para extender una aplicación sin colisionar con la lógica del desarrollador.

#### Convención de Nombres Obligatoria:
Todos los archivos pertenecientes a un plugin deben llevar el prefijo `plugin_<plugin_name>`:
* Modelo: `models/plugin_<name>.py`
* Controlador: `controllers/plugin_<name>.py`
* Vista: `views/plugin_<name>/<action>.html`
* Archivo Estático: `static/plugin_<name>/style.css`

#### Configuración Centralizada vía `PluginManager`:
```python
# En models/plugin_comments.py
from gluon.tools import PluginManager
plugins = PluginManager('comments', default_color='blue')

# El desarrollador puede reconfigurar el plugin en models/db.py:
plugins.comments.default_color = 'red'
```

---

## 16. Deployment, Servidores WSGI y Producción

### [Oficial / Documentado]

### Arquitectura Recomendada para Producción:
```
[Nginx / Apache]  <-- (Sive archivos estáticos /static/ directamente y maneja SSL)
       │
       │ (Unix Socket / uwsgi_pass)
       ▼
[uWSGI / mod_wsgi / Gunicorn]
       │
       ▼
[gluon.main.wsgibase]
```

#### Manejo de Control de Versión de Activos Estáticos (`static_version`):
Para permitir el almacenamiento en caché agresivo (`Cache-Control: max-age=31536000`) de archivos CSS/JS en producción sin sufrir problemas de assets desactualizados:
```python
response.static_version = '1.2.3'
```
Esto transforma las URLs generadas por `URL('static', 'css/main.css')` en:
`/myapp/static/_1.2.3/css/main.css`
El servidor web Nginx/Apache se configura mediante expresiones regulares para omitir el segmento `/_1.2.3/` y leer el archivo real desde la carpeta `static/`.

---

## 17. Mecanismos de Seguridad Integrados

web2py implementa por diseño salvaguardas activas contra las principales vulnerabilidades OWASP Top 10:

1. **Cross-Site Scripting (XSS):**
   * Todas las variables emitidas en vistas `{{= var }}` se escapan de forma predeterminada mediante HTML entity encoding.
2. **SQL Injection (SQLi):**
   * PyDAL no realiza concatenación directa de strings. Construye consultas parametrizadas utilizando los *prepared statements* nativos del driver de base de datos.
3. **Cross-Site Request Forgery (CSRF):**
   * Todo formulario procesado con `form.process()` valida la presencia y autenticidad del token `_formkey` de un solo uso asociado a la sesión.
4. **Directory Traversal:**
   * La función `URL()` y el parsing de la petición validan estrictamente los caracteres de `request.args` y `request.vars`, impidiendo secuencias tipo `../`.
5. **Aislamiento de Tracebacks:**
   * En producción no se muestran mensajes de error al usuario final. Se emite un código de ticket único, evitando la divulgación de código fuente o contraseñas.

---

## 18. Compatibilidad con Python Moderno (3.9+) y Puntos de Modernización

### [Oficial / Documentado]
* web2py 3.x soporta oficialmente **Python 3.9 a Python 3.12+**.
* Se eliminaron por completo los módulos basados en la librería estándar antigua de Python 2 (`urllib2`, `cPickle`, `Queue`, `thread`).

### [Target de Refactorización / IA Prompting para Claude]

Al solicitar a una IA (como Claude) que modifique, audite o refactorice el código interno de web2py en `gluon/`, los siguientes puntos deben priorizarse:

1. **Reemplazo de `cPickle` / `pickle` en Sesiones:**
   * **Problema:** La serialización por defecto de objetos en sesiones utiliza `pickle`. Esto representa un riesgo potencial de ejecución remota de código si la cookie de sesión o la BD se ven comprometidas.
   * **Refactorización:** Migrar la serialización interna de `gluon.globals.Session` a formatos seguros como `JSON` o `msgpack`.

2. **Tipado Estático Progresivo (`typing`):**
   * El código de `gluon/` carece de type hints. Agregar anotaciones de tipo (`mypy`) en `gluon/main.py`, `gluon/globals.py` y `gluon/compileapp.py` facilitará la detección de bugs de tipos.

3. **Reemplazo de `exec` / `eval` por Importadores Dinámicos Estándar (`importlib`):**
   * La compilación de aplicaciones en `gluon.compileapp` depende de `exec()` ejecutando strings en espacios de nombres diccionarios.
   * Modificar progresivamente este mecanismo para usar loaders basados en `importlib.util.spec_from_file_location` manteniendo la inyección de `current`.

4. **Sustitución del Servidor Web Rocket:**
   * `gluon/rocket.py` es un servidor WSGI escrito hace más de una década. Se recomienda desacoplarlo y promover el uso de servidores modernos como `WSGIRef` mejorado, `Gunicorn` o `Uvicorn` (vía adaptadores ASGI/WSGI).

---

## 19. Archivos y Módulos Críticos del Core que un Desarrollador debe Conocer

Al editar o refactorizar web2py, estos son los 12 archivos fundamentales del núcleo dentro de `gluon/`:

1. `gluon/main.py`: Punto de entrada del WSGI app (`wsgibase`). Controla el dispatching, captura de tickets y la respuesta final.
2. `gluon/compileapp.py`: Construye el sandbox de ejecución dinámica (`build_environment`, `exec_environment`).
3. `gluon/globals.py`: Contiene las clases centrales de estado: `Request`, `Response`, `Session` y el contenedor thread-local `current`.
4. `gluon/storage.py`: Implementa la clase `Storage` (pilar de datos en todo el framework).
5. `gluon/rewrite.py`: Define el algoritmo de enrutamiento y reescritura de URLs.
6. `gluon/html.py`: Todos los helpers que construyen etiquetas HTML programáticamente.
7. `gluon/sqlhtml.py`: Genera `SQLFORM`, `SQLFORM.grid` y los widgets por defecto.
8. `gluon/template.py`: Motor de parsing, compilación y renderizado de plantillas `.html`.
9. `gluon/tools.py`: Contiene la lógica de autenticación `Auth`, envío de mails y `PluginManager`.
10. `gluon/restricted.py`: Captura y formatea las excepciones de código del usuario para generar tickets.
11. `gluon/scheduler.py`: Daemon y lógica de colas de tareas asíncronas.
12. `gluon/packages/dal/` (`pydal`): Repositorio del ORM / Abstracción de base de datos PyDAL.

---

## 20. Mapa de Dependencias e Interacciones entre Componentes

El siguiente diagrama detalla cómo interactúan los módulos internos de `gluon/` ante una petición entrante:

```
                               ┌──────────────────────────┐
                               │     Servidor WSGI        │
                               └────────────┬─────────────┘
                                            │
                                            ▼
                               ┌──────────────────────────┐
                               │      gluon.main          │
                               │     (wsgibase)           │
                               └────────────┬─────────────┘
                                            │
           ┌────────────────────────────────┼────────────────────────────────┐
           ▼                                ▼                                ▼
┌────────────────────┐            ┌────────────────────┐           ┌────────────────────┐
│   gluon.rewrite    │            │   gluon.globals    │           │ gluon.compileapp   │
│  (URL Dispatcher)  │            │ (Request/Response/ │           │(Environment Builder│
└────────────────────┘            │  Session/current)  │           │  & exec_environment)│
                                  └────────────────────┘           └─────────┬──────────┘
                                                                             │
                                              ┌──────────────────────────────┼──────────────────────────────┐
                                              ▼                              ▼                              ▼
                                    ┌───────────────────┐          ┌───────────────────┐          ┌───────────────────┐
                                    │    models/*.py    │          │  controllers/*.py │          │    views/*.html   │
                                    └─────────┬─────────┘          └─────────┬─────────┘          └─────────┬─────────┘
                                              │                              │                              │
                                              ▼                              ▼                              ▼
                                    ┌───────────────────┐          ┌───────────────────┐          ┌───────────────────┐
                                    │    PyDAL (pydal)  │          │   gluon.sqlhtml   │          │  gluon.template   │
                                    │  (Database IO)    │          │ (SQLFORM / Grid)  │          │ (Template Compiler│
                                    └─────────┬─────────┘          └─────────┬─────────┘          └───────────────────┘
                                              │                              │
                                              ▼                              ▼
                                    ┌───────────────────┐          ┌───────────────────┐
                                    │    gluon.tools    │          │ gluon.validators  │
                                    │   (Auth / RBAC)   │          │ (Data Validation) │
                                    └───────────────────┘          └───────────────────┘
```

---

## Resumen para Prompts de Refactorización con IA (Ejemplo de uso con Claude)

Cuando utilices este documento como contexto para solicitar a Claude que edite o mejore el repositorio de web2py, puedes estructurar tus instrucciones con comandos precisos como:

> *"Utilizando la sección 18 y 19 de la Especificación Técnica de web2py (web2py_technical_reference-v2.md), analiza el archivo `gluon/globals.py`. Refactoriza la clase `Session` para añadir Type Hints estrictos de Python 3.9+ y reemplazar el uso de `pickle` por un serializador JSON seguro sin romper la compatibilidad con el método `session.connect`."*

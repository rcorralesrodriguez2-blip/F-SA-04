F-SA-04 - Guía técnica FastAPI
==============================

DOCUMENTACION.txt: funciones y límites. CAMBIOS.txt: historial de cambios.
Este documento: ejecución, integración, configuración y mantenimiento.

1. Ejecución independiente

Requiere Python 3.10 o posterior.
En Windows, ejecutar.bat prepara .venv, instala requirements.txt e inicia
http://127.0.0.1:5000 con Uvicorn. También puede ejecutar:

  .venv\Scripts\python.exe -m pip install -r requirements.txt
  .venv\Scripts\python.exe app.py

Alternativa ASGI (puerto configurable):
  .venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 5000

GET / muestra el formulario; POST /guardar registra una interconsulta;
GET /tabla muestra el historial y GET /indicadores muestra las métricas.
GET /consolidado?anio=2026 consulta el consolidado mensual del año indicado.
GET /registros/{id}/editar abre el registro y POST /registros/{id}/actualizar
guarda sus cambios con redirección 303 al historial.

Si el navegador muestra ERR_CONNECTION_REFUSED en 127.0.0.1:5000, compruebe
que la aplicación esté iniciada. Abra ejecutar.bat o ejecute el comando
Python anterior y mantenga el proceso activo mientras usa las pantallas.
Espere el mensaje de Uvicorn indicando que escucha en 127.0.0.1:5000 y
recargue http://127.0.0.1:5000/tabla. Si el arranque falla, revise el error
en la consola. Abrir la URL por sí solo no inicia el servidor.

El guardado redirige con HTTP 303 al historial. Las pantallas siguen siendo
HTML con Jinja; no se ha creado una API JSON de interconsultas.
POST /vista-previa devuelve únicamente el estado del formulario en JSON,
sin guardar datos; requiere CSRF y la dependencia de acceso configurada.
Bootstrap se incluye localmente para funcionar sin CDN.

Historial paginado (2026-10-21): /tabla acepta q (hasta 250 caracteres) y
antes (ID positivo de cursor). obtener_pagina_historial solicita 51 filas
para devolver 50 y detectar si existe una página siguiente, sin COUNT ni
OFFSET. Se usa la clave primaria para recorrer id DESC. Los enlaces conservan
el filtro y root_path; una búsqueda nueva reinicia el cursor.
La búsqueda parcial usa instr y casefold Unicode mediante una función local
de SQLite y parámetros SQL; % y _ se interpretan literalmente. Esta búsqueda
puede recorrer muchas filas: no se añadió un índice de texto completo.
El filtro q viaja en la URL GET; revisar su tratamiento en los registros de
acceso del portal. Las páginas conservan Cache-Control: no-store.
listar_interconsultas sin opciones mantiene el contrato completo para usos
internos existentes; la ruta usa siempre la variante limitada.
No cambia el esquema ni se requieren nuevas dependencias. Reiniciar Uvicorn
después de actualizar para cargar el código y las versiones de CSS/JS.
El bloqueo del botón evita envíos repetidos desde ese formulario; no sustituye
una clave de idempotencia frente a reintentos externos o varias pestañas.

Verificación local: 62 pruebas unittest aprobadas con bases temporales y
node --check para ambos scripts. Con 10.000 filas sintéticas y TestClient,
mediana de 7 solicitudes: 411,44 ms al simular lectura/renderizado completo
con la plantilla actual frente a 5,31 ms paginado; HTML de 4.148.019 frente a
23.284 bytes. No incluye red ni renderizado en navegador y no representa una
medición antes/después en producción. Sin pruebas visuales de estos cambios.

Diseño de formularios: formulario.html comparte el alta y la edición.
La clase .interconsulta-form usa CSS Grid y .formulario-panel define un
contenedor: desde 42rem de ancho útil pasa de una a dos columnas, sin
depender del ancho de la ventana del portal. En navegadores sin consultas
de contenedor conserva una columna. El menú pasa arriba bajo 992px y los
botones del formulario ocupan todo el ancho bajo 576px. Los estilos están
en app.css, limitados al módulo. La plantilla del portal debe incluir su
meta viewport para que la adaptación móvil funcione también al integrarlo.
Se verificaron alta y edición en Chrome sin interfaz, en 12 anchos entre
320 y 2560px; esto no representa una certificación de todos los equipos.

2. Organización y responsabilidades

app.py                           Entrada ASGI y arranque Uvicorn.
fsa04/__init__.py                create_app, create_module e init_app.
fsa04/__main__.py                Comando de inicialización del esquema.
fsa04/config.py                  Settings explícito y entorno independiente.
fsa04/database.py                Esquema y contexto de conexión SQLite.
fsa04/domain.py                  Catálogos y reglas puras, sin framework.
fsa04/consolidado.py             Agregación mensual y normalización de categorías.
fsa04/repositories.py            SQL parametrizado y transacciones.
fsa04/services.py                Casos de uso e indicadores.
fsa04/routes.py                  APIRouter y respuestas de las pantallas.
fsa04/presentation.py            Contexto Jinja y enlaces bajo root_path.
fsa04/assets.py                  Versionado y caché de recursos públicos.
fsa04/security.py                CSRF firmado y cabeceras.
fsa04/errors.py                  Errores HTML controlados del módulo.
fsa04/templates/interconsultas/  Plantillas propias con espacio de nombres.
fsa04/static/                    CSS, JS y Bootstrap.
tests/                           Pruebas funcionales e integración ASGI.
requirements.txt                 Dependencias para ejecutar.
requirements-dev.txt             Dependencias adicionales para pruebas.

Flujo: ruta -> servicio -> dominio / repositorio -> SQLite.
La presentación (HTML, CSS, JS y adaptadores HTTP) captura entradas y muestra
resultados. JavaScript consulta /vista-previa para mostrar la oportunidad y
reflejar las reglas de cumplimiento que devuelve el servidor; no calcula
duraciones ni decide SI/NO. El historial se pagina y filtra en el servidor;
el contador muestra únicamente las filas de la página recibida.
Las validaciones HTML facilitan la captura; el negocio vuelve a validar todo.

La lógica de negocio vive en services.py, domain.py y consolidado.py:
normalización, validación, oportunidad, indicadores y totales del reporte.
normalizar_entrada selecciona CAMPOS, completa ausentes y limpia espacios;
validar_interconsulta la aplica también cuando se invoca sin una ruta HTTP.
Se ignoran campos ajenos, incluido cualquier resultado calculado por el cliente.
preparar_formulario usa la misma normalización para el estado y la vista previa.

Persistencia (repositories.py y database.py) gestiona consultas, esquema,
conexiones y transacciones. Devuelve diccionarios, listas de diccionarios o
un iterador de diccionarios para indicadores; no expone sqlite3.Row a las
otras capas. La conversión del iterador se realiza fila a fila, conservando
la lectura incremental. SQL agrupa conteos del reporte, sin decidir reglas
de cumplimiento o calcular oportunidad. No hay acceso a SQLite desde rutas,
plantillas o JavaScript. Las fábricas conectan las capas e inician el esquema.

Las operaciones reciben la ruta de la base de forma explícita. Cada operación
abre y cierra su conexión; no hay current_app, g ni contextos de Flask.
Las rutas síncronas se ejecutan en el pool de hilos de FastAPI; el guardado
asíncrono envía el trabajo SQLite al pool para no bloquear el bucle ASGI.
Las plantillas y recursos activos están dentro de fsa04/. No se utilizan
carpetas templates/ o static/ en la raíz.

3. Integración en el proyecto principal FastAPI

Copie el paquete completo fsa04/ e instale sus dependencias. No importe
app.py desde el portal: es la entrada independiente. En su fábrica:

  import os
  from fastapi import FastAPI
  from fsa04 import init_app
  from fsa04.config import Settings

  app = FastAPI()
  module_settings = Settings(
      database='/ruta/absoluta/interconsultas.db',
      secret_key=os.environ['FSA04_SECRET_KEY'],
      cookie_secure=True,  # Con HTTPS; False para desarrollo HTTP.
  )
  init_app(app, module_settings, url_prefix='/interconsultas')

init_app monta una subaplicación ASGI con nombre fsa04. No modifica los
handlers, sesiones ni lifespan del portal y no crea la base al registrarse.
Registre el módulo una sola vez y antes de un montaje genérico en '/'.
Las páginas quedan en /interconsultas/, /interconsultas/tabla e
/interconsultas/indicadores; el guardado, en /interconsultas/guardar.
El consolidado se consulta en /interconsultas/consolidado?anio=2026.
Los recursos quedan en /interconsultas/static/.
Los enlaces y las redirecciones respetan el prefijo y root_path del proxy.
Configure correctamente el proxy y el root_path del servidor anfitrión.

Antes del primer uso, inicialice explícitamente el esquema:
  .venv\Scripts\python.exe -m fsa04 init-db --database RUTA_SQLITE

La carpeta padre debe existir. init_db crea tablas e índices ausentes sin
borrar registros y se puede ejecutar más de una vez. No es una migración.
También puede llamar a fsa04.database.init_db(ruta) desde una tarea de
preparación del portal. El lifespan de subaplicaciones montadas no se usa
para inicializar la base: esa preparación es responsabilidad del portal.
Solo create_app inicia automáticamente el esquema, durante su propio lifespan.

Se conservan el esquema anterior y la compatibilidad de los datos SQLite.
Para reutilizar la base existente, indique su ruta absoluta. No apunte a una
base compartida sin revisar tablas homónimas. No hay integración automática
con SQLAlchemy ni cambio de motor de persistencia.

4. Acceso y seguridad

Las dependencias globales de la aplicación principal no se heredan por el
montaje. Configure explícitamente una dependencia FastAPI para las pantallas:

  from fastapi import HTTPException, Request

  def require_access(request: Request):
      # Ejemplo: adaptar a los permisos reales del portal.
      if not request.session.get('user_id'):
          raise HTTPException(status_code=403, detail='Acceso denegado')

  init_app(app, module_settings, access_dependency=require_access)

request.session requiere que el portal tenga SessionMiddleware. También puede
usar request.user, request.state o subdependencias Depends del sistema real.
La dependencia puede ser síncrona o asíncrona y debe lanzar HTTPException
para denegar. Un valor de retorno se trata como resultado de la dependencia,
no como redirección. Las excepciones HTTP se muestran como página HTML.
La dependencia protege todas las rutas funcionales, incluidas Consolidado
y las rutas GET/POST de edición. Los archivos CSS/JS de
StaticFiles son públicos; no contienen registros. Si el portal requiere
proteger también recursos, aplique su middleware de acceso al montaje.
Sin access_dependency el módulo no exige autenticación.

CSRF: cookie HttpOnly fsa04_csrf y campo oculto _csrf_token. El token está
firmado, vence al cabo de una hora por defecto y se compara con la cookie.
No se usa ni se modifica la sesión del portal. Cambiar secret_key invalida
los formularios anteriores. Cada montaje utiliza la ruta de su cookie.
La protección CSRF del portal, si existe, debe coordinarse explícitamente.

Las páginas y errores solicitan Cache-Control: no-store. Los recursos CSS/JS
con versión vigente permiten caché pública; véase la sección 12.
Hay cabeceras de seguridad,
escape HTML, SQL parametrizado y límite de 65536 bytes por petición de
escritura, comprobado también si no llega Content-Length. Los errores no
muestran detalles internos. El middleware del portal puede definir su propia
política global de cabeceras. El módulo no incluye usuarios, roles ni auditoría.

5. Configuración y adaptación visual

Settings admite:
  database            Ruta SQLite, obligatoria.
  secret_key          Secreto estable, obligatorio al integrar.
  base_template       interconsultas/shell.html.
  load_bootstrap      True; False si el portal ya incluye Bootstrap 5.
  show_sidebar        True; False si el portal aporta su menú.
  title               Control hospitalario.
  max_content_length  65536 bytes.
  cookie_secure       False; activar para HTTPS.
  csrf_cookie         fsa04_csrf.
  csrf_max_age        3600 segundos.

El CSS propio está bajo .fsa04-module y los JS evitan variables globales.
Bootstrap mantiene estilos globales; evite cargarlo dos veces. Las variables
--fsa04-primary y --fsa04-background permiten ajustar los colores.
La paleta y la tipografía actuales se detallan en la sección 14.

Para usar la plantilla del portal, pase templates=Jinja2Templates(...) a
init_app y configure base_template. El loader debe poder resolver tanto las
plantillas del portal como fsa04/templates/. Use un directorio adicional o
ChoiceLoader de Jinja. Mantenga autoescape habilitado.
La plantilla padre debe incluir estos bloques:
  fsa04_styles   Dentro del head.
  fsa04_content  En el cuerpo.
  fsa04_scripts  Al final del cuerpo.
Puede crear una plantilla adaptadora que extienda la base real y ubique
esos bloques dentro de los bloques del portal. El contexto del módulo aporta
config, mensajes, csrf_value, active_endpoint y url_for para sus rutas.
Los nombres internos son interconsultas.formulario, interconsultas.tabla,
interconsultas.indicadores, interconsultas.consolidado, interconsultas.editar,
interconsultas.actualizar e interconsultas.static. Desde el portal, el
nombre del montaje se antepone: request.url_for('fsa04:interconsultas.tabla').

6. Entorno independiente y operación

create_app() usa Settings.from_env():
  FSA04_DATABASE    Ruta SQLite; por defecto database.db en la raíz.
  FSA04_SECRET_KEY  Secreto estable; sin él se genera uno por proceso.
create_app(settings) permite proporcionar los valores directamente.
Sin secreto estable, al reiniciar dejan de ser válidos los formularios abiertos.
Las opciones anteriores de Flask (app.config y DATABASE) fueron sustituidas
por Settings. No se utiliza Flask ni se requiere su instalación.

Detenga escrituras antes de copiar la base para hacer un respaldo manual.
Para restaurar, detenga la aplicación y reemplace el archivo por la copia.
No incluya secretos ni datos de pacientes en el repositorio.
El portal debe aportar autenticación, permisos, respaldo y la configuración
de despliegue institucional. El arranque local no añade esas funciones.

7. Verificación y mantenimiento

  .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
  .venv\Scripts\python.exe -B -m unittest discover -s tests -v

Las pruebas usan TestClient y bases temporales; no utilizan database.db.
Cubren reglas, guardado, pendientes, validaciones, persistencia, CSRF,
errores, recursos, cierre de conexiones, prefijos, root_path, sesión del
anfitrión, autorización, plantilla del portal y límite de cuerpo en streaming.
También cubren el consolidado, sus sumas por mes/año, pendientes, históricos,
catálogo ampliado, validación del año y protección de la ruta montada.
La versión instalada de Starlette avisa que el soporte de httpx en TestClient
está deprecado; las pruebas actuales pasan con httpx 0.28.1.
No se ha comprobado aún el proyecto principal real ni la apariencia en navegador.

Para ampliar: reglas en domain.py, consultas en repositories.py, coordinación
en services.py y presentación en rutas/plantillas/recursos. Mantenga pruebas
que cubran el comportamiento cambiado y actualice los documentos .txt.
Los cambios de esquema necesitan migraciones explícitas y respaldo previo.

Referencias técnicas utilizadas:
  https://fastapi.tiangolo.com/advanced/sub-applications/
  https://fastapi.tiangolo.com/advanced/templates/

8. Implementación del consolidado

Ruta GET /consolidado, nombre interconsultas.consolidado. Acepta anio como
entero entre 1 y 9999; el valor inválido produce una página HTML con HTTP 400.
Sin parámetro usa el año de la hora de Colombia (UTC-5).
La ruta síncrona llama a services.obtener_consolidado(database, anio).
El repositorio utiliza strftime sobre fecha_solicitud, filtro parametrizado
y COUNT/GROUP BY por mes, especialidad y tipo. Solo lee esos grupos agregados,
sin campos personales. calcular_consolidado construye las filas y totales.
No se modificó el esquema ni se ejecutó una migración.

El catálogo ESPECIALIDADES se amplió con los nombres del formato recibido.
validar_interconsulta reconoce tildes, mayúsculas y espacios equivalentes y
guarda el nombre del catálogo. Los registros anteriores no se reescriben.
Los nombres históricos no catalogados se conservan como filas adicionales en
el reporte. Las fechas históricas no reconocidas por SQLite no se cuentan.
No se deduce el tipo a partir de la especialidad; se usa el tipo registrado.
El alcance funcional y los límites se describen en DOCUMENTACION.txt.

9. Edición de interconsultas

El formulario compartido formulario.html recibe registro_id para elegir el
modo de edición, el título y la acción del POST. Los enlaces se construyen
con url_for('interconsultas.editar', registro_id=id) y respetan el montaje.
Las rutas son /registros/{id}/editar y /registros/{id}/actualizar, bajo el
prefijo del módulo cuando está integrado. No hay cambios de esquema.

obtener_interconsulta busca por ID parametrizado. actualizar_interconsulta
reutiliza validar_interconsulta antes de ejecutar UPDATE, recalculando la
oportunidad y validando la elección manual SI/NO del cumplimiento. La
oportunidad que envíe el navegador no se toma como resultado válido. UPDATE no inserta registros.
Una orden inexistente devuelve 404; una validación fallida devuelve 400 con
el formulario precargado. El POST requiere CSRF y la dependencia de acceso
configurada para el módulo. Las operaciones SQLite siguen fuera del bucle ASGI.

Los registros históricos con nombres equivalentes se normalizan al abrir el
formulario. Los valores fuera del catálogo se muestran para su corrección,
sin reemplazarlos silenciosamente por otra especialidad o tipo.
No se implementó control de edición simultánea ni historial de versiones:
el último guardado válido prevalece. La auditoría por usuario sigue pendiente.
Las pruebas en tests/test_edicion.py verifican edición, pendientes, recálculo,
validaciones, CSRF, ID inexistente, históricos, escape HTML, consolidado,
prefijos y autorización usando una base temporal.

10. Cumplimiento manual

CAMPOS incluye cumplimiento. Con fecha_respuesta, validar_interconsulta exige
SI o NO (normaliza mayúsculas y tildes); sin respuesta almacena NULL tanto en
cumplimiento como en oportunidad. Se rechazan valores ajenos a las opciones.
calcular_oportunidad devuelve solamente la duración; no asigna cumplimiento.
Se mantienen esquema, restricciones SQLite y registros existentes.

El formulario compartido incorpora la selección explícita para altas y
edición. formulario.js consulta /vista-previa al cambiar las fechas y
aplica el estado devuelto: obligatoriedad, habilitación y mensaje. No elige
una opción por las horas. Si falla la consulta, permite enviar el formulario
para que el servidor lo valide. El servidor
aplica la misma regla aunque se omita JavaScript. Las ediciones precargan el
valor guardado para que el usuario pueda revisarlo y modificarlo.

listar_datos_indicadores incluye cumplimiento. calcular_indicadores obtiene
incumplen de las órdenes respondidas con valor NO; superan_24_horas conserva
el conteo objetivo por duración, presentado por separado. Los promedios y el
consolidado no cambian su fórmula. Los valores históricos no se migran ni se
marcan retroactivamente como revisados por una persona: pueden proceder del
cálculo automático anterior. No hay auditoría de la decisión por usuario.

Las pruebas de tests/test_cumplimiento.py verifican elecciones opuestas al
umbral, validación obligatoria, edición y recálculo de indicadores, registros
pendientes y textos de la interfaz. Las pruebas anteriores se adaptaron para
enviar explícitamente la selección al registrar respuestas.

11. Correcciones y eficiencia de indicadores

listar_datos_indicadores devuelve un generador sobre el cursor SQLite, en
vez de cargar fetchall(). obtener_indicadores usa closing() para cerrar el
generador, cursor y conexión tanto al terminar como ante un dato corrupto.
calcular_indicadores acepta un iterable y acumula las métricas en una pasada.
No materializa las órdenes ni crea listas separadas para cada categoría.
El almacenamiento auxiliar del cálculo no crece con el número de registros;
la consulta sigue recorriendo todas las órdenes porque no hay filtro temporal.

La clasificación usa normalizar_etiqueta para unificar espacios internos,
tildes y mayúsculas; la validación de nuevos tipos usa la misma normalización.
Los tipos no catalogados o vacíos se agrupan en una métrica adicional Otros
tipos de especialidad. La suma de órdenes de los grupos coincide con el total.
Se conservan el promedio con pendientes y el cumplimiento manual.

El resultado añade validadas (respondidas con SI/NO) y sin_validar
(respondidas sin esos valores). La plantilla usa esos conteos para mostrar
estados vacíos neutrales y avisar de respuestas pendientes de validación.
No se ha cambiado el denominador del porcentaje ni se han modificado datos.
Las validaciones históricas calculadas automáticamente siguen sin poder
distinguirse de las manuales: no existe auditoría de esa procedencia.

Pruebas en tests/test_indicadores.py: variantes de nombres, tipos desconocidos,
iterable de una pasada, cierre al fallar, lectura real incremental, estados
vacíos y conservación de los resultados del ejemplo. La suite completa pasó
50 pruebas. Una comparación con tracemalloc sobre 20000 órdenes sintéticas
replicó la estrategia anterior de listas y la nueva: resultados iguales y
picos aproximados de 7,51 MB y 0,017 MB de memoria Python, respectivamente.
Es una medición del cálculo sintético, no del proceso completo ni de SQLite;
no se ha medido el rendimiento con la carga real del sistema principal.

12. Recursos y velocidad de navegación

VersionedStaticFiles calcula una huella SHA-256 de cada CSS/JS al crear el
módulo. module_url añade ?v=HUELLA a sus enlaces, respetando prefijo y root_path.
Para una versión vigente, los recursos responden con Cache-Control: public,
max-age=31536000, immutable. Las peticiones sin versión o con otra versión
usan no-cache y permiten revalidación con ETag/304. Los errores conservan
no-store; las cabeceras de seguridad se aplican también a los estáticos.
No se almacenan páginas clínicas ni se introduce caché de consultas SQLite.

Reinicie el servidor después de modificar CSS/JS para regenerar sus versiones.
Los despliegues deben conservar los archivos estáticos durante la vida del
proceso. No se añaden dependencias ni cambios de configuración.
base.html conserva Bootstrap CSS. bootstrap.bundle.min.js se eliminó porque
ninguna pantalla lo utiliza. Si se añaden componentes que necesiten ese
JavaScript, deberá incorporarse de nuevo y cargarse explícitamente.

Para comparar en DevTools > Network, desmarque Disable cache, visite primero
las pantallas para cargar sus recursos y repita la navegación. CSS/JS ya
cargados deben indicar memoria/disco; el documento HTML se sigue solicitando.
Con Disable cache activo, el navegador no aprovechará esta mejora.
No se garantiza un umbral de milisegundos a partir de la captura facilitada.
Las pruebas de tests/test_assets.py verifican versiones, caché, revalidación,
no-store de páginas/errores y enlaces bajo montaje y proxy con bases temporales.

13. Inventario y limpieza de archivos (2026-10-19)

Los módulos Python del paquete y sus responsabilidades se enumeran en la
sección 2. Todos participan en la ejecución, integración o administración.
__main__.py se conserva por el comando init-db, aunque app.py no lo importe.

Archivos de la raíz:
  app.py: entrada del servidor independiente y de ASGI.
  ejecutar.bat: prepara .venv, instala dependencias y ejecuta app.py.
  requirements.txt: dependencias de ejecución con versiones fijadas.
  requirements-dev.txt: añade httpx para ejecutar pruebas.
  .gitignore: excluye entorno, cachés, bases y archivos locales de Git.
  AGENTS.md: instrucciones para mantener la documentación del proyecto.
  README.txt: guía técnica e inventario de archivos.
  DOCUMENTACION.txt: funciones y límites para los usuarios.
  CAMBIOS.txt: historial de implementaciones y verificaciones.
  database.db: almacenamiento local; conservado sin consultar sus registros.

Plantillas en fsa04/templates/interconsultas/:
  shell.html: documento HTML base para ejecución independiente.
  base.html: estilos, menú, mensajes y bloques compartidos; admite el portal.
  formulario.html: alta y edición de interconsultas.
  tabla.html: historial paginado, búsqueda global y acceso a la edición.
  indicadores.html: métricas de oportunidad y cumplimiento.
  consolidado.html: tablas mensuales por especialidad y tipo.
  error.html: errores controlados y enlace para volver al formulario.

Recursos en fsa04/static/:
  css/app.css: diseño y estilos propios de las pantallas.
  fonts/Roboto-Variable.ttf: fuente Roboto local para todas las pantallas.
  fonts/OFL.txt: licencia de redistribución de Roboto; conservar junto a la fuente.
  js/formulario.js: consulta la vista previa y refleja el estado del servidor.
  js/tabla.js: indica el envío de búsqueda y restaura el botón al regresar.
  vendor/bootstrap.min.css: rejilla, controles, tablas y clases visuales usadas.
  Se conserva el CSS de terceros completo; no se recortan clases individuales.

Pruebas en tests/:
  __init__.py: marcador de paquete para importar pruebas como tests.test_app.
  test_app.py: reglas, altas, errores, seguridad y conexiones.
  test_assets.py: versionado, caché y enlaces a recursos.
  test_capas.py: contratos entre capas y vista previa protegida sin escrituras.
  test_consolidado.py: conteos, meses, años y categorías históricas.
  test_cumplimiento.py: elección manual y sus efectos en indicadores.
  test_edicion.py: actualización, precarga, validación y protección de cambios.
  test_indicadores.py: clasificación, resultados y lectura incremental.
  test_integration.py: montaje ASGI, portal, acceso y prefijos.

.venv/ contiene el intérprete y las dependencias instaladas; se conserva como
entorno administrado por pip, sin limpiar sus archivos internos uno a uno.
Se revisaron los archivos propios, sus imports, rutas y referencias de recursos.
La base se identificó por configuración y uso del repositorio; no se revisó
contenido de pacientes para decidir su conservación.

Retirados: templates/error.html de la raíz (vacío y fuera del loader activo),
su carpeta vacía, vendor/bootstrap.bundle.min.js (sin carga en las pantallas)
y los 13 .pyc de __pycache__/ y fsa04/__pycache__/ presentes en la revisión.
Los .pyc son caché regenerable: pueden reaparecer al ejecutar Python normalmente.
No constituyen módulos fuente adicionales. Use -B si necesita una ejecución
sin escribir nuevos .pyc; no es necesario para el funcionamiento normal.

14. Revisión visual y aplicación del manual de marca 2025

Fuente: los diez PDF MANUAL DE MARCA - 2025.pdf-1.pdf a -10.pdf facilitados
por el usuario. Se revisaron sus páginas visualmente y los códigos de color
extraíbles. Secciones 04 y 05: cian #00AFEF y gris #696B6D como principales;
azul oscuro #08337B y gris claro #D9D9D9 como secundarios. Sección 07:
Avenir Next LT Pro Bold para el identificador/tagline; Roboto Bold y Light
como tipografías secundarias. Las reglas del identificador se refieren al
logotipo; no se añadió un logo ni se recompuso con texto.

Hallazgos antes del ajuste:
  - Azul #123e70 y tipografía del sistema distintos de la identidad aportada.
  - Botones y utilidades de Bootstrap mantenían el azul predeterminado.
  - Faltaba una fuente distribuida con el proyecto para otros equipos.
  - Controles, encabezados, tarjetas y tablas requerían un tratamiento común.
  - Había que conservar estados clínicos y reforzar el foco y la lectura móvil.

Implementación en fsa04/static/css/app.css, bajo .fsa04-module:
  - Variables para los cuatro colores del manual; cian en acentos y azul
    oscuro en títulos, enlaces, selección de menú y botones con texto blanco.
    Se evita usar cian como texto pequeño sobre blanco por su bajo contraste.
  - Menú blanco, acentos cian, paneles, tarjetas y encabezados de tablas
    unificados; espaciado adaptable y desplazamiento interno de tablas anchas.
  - Variables de Bootstrap y estados hover/active/disabled coherentes.
    Foco visible con contorno azul oscuro y controles de al menos 44 px de alto.
  - Estados SI/NO/pendiente mantienen sus textos y fondos diferenciados.
    Verde, rojo y ámbar son colores funcionales complementarios, no colores
    oficiales del manual. Los fondos claros y hover son adaptaciones de UI.
  - Roboto local variable: 700 para títulos/acciones, 300 para el descriptor
    del menú y 400 para lectura y formularios. El peso de lectura 400 es una
    adaptación funcional, no una especificación literal del manual.
    La familia CSS exclusiva FSA04 Roboto evita interferir con el portal.

La fuente completa se obtuvo de google/fonts, ofl/roboto, con su licencia
SIL Open Font License en fonts/OFL.txt:
  https://github.com/google/fonts/tree/main/ofl/roboto
No se extrajeron subconjuntos tipográficos del PDF para usarlos como fuentes.
No se distribuye Avenir: no se proporcionó un archivo completo de esa familia.
La interfaz usa la familia secundaria indicada en el manual. Si se cambia
la fuente, revise también la ruta relativa en @font-face y conserve su licencia.
La fuente se sirve desde el mismo origen y funciona sin CDN; su URL sin
versión usa la revalidación no-cache existente para recursos sin versión.
No cambian el arranque, las dependencias de ejecución ni la configuración.

El CSS compartido llega a alta, edición, historial, indicadores, consolidado
y errores mediante base.html; no se duplican estilos en cada plantilla.
La plantilla base deja de mostrar la cruz tipográfica decorativa del menú.

Verificación del ajuste: 57 pruebas unittest aprobadas. Chrome sin interfaz
con Playwright, servidor y datos temporales: seis pantallas (alta, edición,
historial, indicadores, consolidado y error 404) a 1440x1000 y 390x844.
Se comprobó fuente cargada, títulos, ausencia de desbordamiento de página,
vista previa, foco, hover y filtro. Se revisaron capturas de escritorio y móvil.
Las herramientas de revisión y capturas están fuera del proyecto, no son
dependencias para ejecutar la aplicación. Falta revisión visual en el portal
anfitrión real y en otros navegadores; no es una auditoría WCAG completa.

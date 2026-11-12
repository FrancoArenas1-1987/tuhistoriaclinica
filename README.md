# TuHistoriaClinica.cl

Plataforma de gestión de consulta para profesionales: registro gratuito, pacientes privados, ficha clínica, atenciones y agenda. FastAPI + Jinja2 + JavaScript + SQLAlchemy + PostgreSQL.

## Desarrollo local

La base independiente **tuhistoriaclinica** está en PostgreSQL del VPS. La copia local se conecta por el túnel existente en `127.0.0.1:15432`. También existe un despliegue público en https://tuhistoriaclinica.conectaproia.cl, instalado por separado en `/opt/tuhistoriaclinica.cl`. Ambas instalaciones utilizan la misma base: los cambios locales de datos se reflejan en el sitio público. Las bases de los otros proyectos no se modificaron.

Desde PowerShell:

```powershell
cd C:\Franco\kineymujer
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Alternativamente, ejecutar `./start.ps1` desde esta carpeta para aplicar migraciones y arrancar el servidor. Mantener el túnel abierto.

- Sitio público: http://127.0.0.1:8000/
- Crear cuenta: http://127.0.0.1:8000/registro
- Ingresar: http://127.0.0.1:8000/ingresar
- Portal: http://127.0.0.1:8000/portal
- API: http://127.0.0.1:8000/docs

Crear una cuenta desde la pantalla de registro. No existen cuentas de demostración ni administrador predeterminado en esta base. No se reutilizan las credenciales del sitio anterior.

## Configuración

`.env` contiene `DATABASE_URL` y `SECRET_KEY`. Nunca compartirlo ni incluirlo en la imagen Docker. `.env.example` contiene valores ilustrativos. La configuración se lee desde la raíz del proyecto independientemente del directorio actual.

`DATABASE_URL` es la conexión efectiva; las variables `POSTGRES_*` no configuran SQLAlchemy. Cuando se despliegue, se deberá cambiar el host/puerto del túnel por la dirección accesible desde el servidor, configurar HTTPS y `COOKIE_SECURE=true`.

## Funciones

- Registro de profesional con nombre, correo, especialidad y contraseña; inicio/cierre de sesión con JWT en cookie HTTP-only.
- Cada usuario accede exclusivamente a sus propios pacientes, atenciones y citas, incluso conociendo identificadores de otra cuenta. No hay acceso global por rol.
- Alta, búsqueda y edición de pacientes. RUT validado y único por profesional; un paciente puede atenderse con varios profesionales en fichas independientes.
- Ficha con datos personales, antecedentes generales, síntomas específicos opcionales y consentimiento explícito.
- Historial ordenado de atenciones, registro y edición de evaluación, hallazgos, plan, recomendaciones y dolor. Última atención calculada por fecha máxima.
- Agenda con navegación semanal, detalle diario, creación, reprogramación y estados: agendada, confirmada, realizada, cancelada y no asistió.
- Bloqueo transaccional por profesional para impedir superposiciones, incluso en solicitudes concurrentes. Citas canceladas o sin asistencia liberan el horario.
- Horarios de Chile (`America/Santiago`); las fechas/horas se almacenan con zona horaria en PostgreSQL.
- Perfil editable con nombre, correo, especialidad, teléfono, duración habitual y jornada preferida. La jornada es una preferencia; se permiten excepciones.

## Base de datos y migraciones

`users` (cuentas y preferencias), `patients` (propietario y ficha), `visits` (paciente, profesional y evolución), `appointments` (paciente, profesional, rango y estado), `alembic_version` (versión de esquema). La migración `002` agrega la versión de sesión a las cuentas existentes, sin cambiar sus contraseñas.

La migración inicial está en `migrations/versions/001_initial.py`. El arranque verifica la revisión y solicita migrar si está desactualizada. No se altera el esquema automáticamente con `create_all`.

Para futuras migraciones:

```powershell
python -m alembic revision --autogenerate -m "descripcion"
# Revisar el archivo generado antes de aplicar.
python -m alembic upgrade head
```

No ejecutar `downgrade` sobre datos reales sin revisar y respaldar: puede eliminar tablas.

## Verificación

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node --check app/static/js/portal.js
```

La prueba de integración usa la base configurada, crea dos cuentas identificadas como QA y borra exclusivamente sus registros al terminar. Verifica registro, login, aislamiento, validaciones, fichas, historial, fecha máxima, agenda, cancelación y concurrencia.

`tests/browser_qa.py` es una comprobación opcional con Chrome headless CDP en puerto 9227, servidor local y `websockets` instalado. Recorre los formularios reales, comprueba escritorio/móvil y guarda capturas en `artifacts/`. Crea y elimina su propia cuenta temporal.

## Alcance de esta versión

Agenda gestionada por el profesional. Aún no incluye reservas públicas de pacientes, recordatorios por correo/WhatsApp, recuperación de contraseña, verificación de correo, equipos/recepción, pagos ni firma digital. El consentimiento registrado es una declaración del profesional, no una firma electrónica. La edición de atenciones todavía no mantiene un historial de versiones.

Antes del lanzamiento público faltan la revisión de seguridad y privacidad, recuperación/verificación de cuentas, protección contra abuso y copias de seguridad. El despliegue actual usa `docker-compose.prod.yml`, cookies seguras y HTTPS; los puntos anteriores siguen siendo trabajo pendiente para una operación productiva más completa.

## Tipografía

Inter variable se sirve localmente desde `app/static/fonts/Inter-variable.ttf`, con licencia SIL OFL incluida en `OFL-Inter.txt`. La familia interna `THC Inter` evita depender de fuentes instaladas en el dispositivo. La escala compartida al final de `site.css` usa una base de 18 px en escritorio y 17 px en móvil, con tamaños proporcionales para controles, textos secundarios y metadatos; las vistas ilustrativas usan una escala compacta.

## Editar cuenta y contraseña

En **Mi perfil** se pueden editar nombre, especialidad, correo, teléfono y preferencias horarias. El cambio de correo requiere la contraseña actual y rechaza correos ya registrados. El nuevo correo se usa para futuros inicios de sesión.

La sección **Contraseña y seguridad** solicita clave actual, nueva clave (8–64 caracteres, hasta 72 bytes UTF-8) y confirmación. Rechaza claves iguales, confirmaciones distintas y claves actuales incorrectas. Se almacena únicamente el hash bcrypt.

Al cambiar el correo o la contraseña se incrementa `users.session_version`: las sesiones anteriores dejan de ser válidas y se renueva la cookie de la sesión actual. JWT anteriores a esta migración se interpretan como versión 0. El cierre de sesión normal borra la cookie del navegador actual.

`tests/test_account.py` prueba estas funciones con cuentas temporales, incluidos conflictos de correo e invalidación de sesiones. Las credenciales de Evelyn no se usan ni se modifican en las pruebas.

## Despliegue actual

URL: https://tuhistoriaclinica.conectaproia.cl

- Carpeta: `/opt/tuhistoriaclinica.cl`.
- Compose: `docker-compose.prod.yml`; proyecto Docker `tuhistoriaclinica`.
- Contenedor: `tuhistoriaclinica-web`, sin puertos publicados al exterior.
- Caddy existente: `/opt/conectapro-platform/infra/caddy/Caddyfile`; bloque adicional exclusivo para el subdominio. El resto de rutas se conserva.
- Base: `tuhistoriaclinica`; usuario de ejecución `tuhistoriaclinica_app`, sin privilegios de superusuario ni DDL.
- Variables privadas: `/opt/tuhistoriaclinica.cl/.env`, permisos 0600, generadas en el VPS y excluidas de la imagen. La copia local mantiene su propia configuración.
- Recursos del contenedor: hasta 384 MiB de RAM y 0,5 CPU, con comprobación de salud y rotación de logs.
- Sistema de archivos del contenedor de solo lectura, usuario sin privilegios y directorio temporal en memoria.
- Respaldo previo de Caddy y registro de despliegue: `deployment-backups/` y `deployment.json` dentro de la carpeta del sitio.

El registro DNS A `tuhistoriaclinica` apunta a `172.233.16.172`, en modo DNS only. Caddy gestiona HTTPS y la redirección HTTP.

Para consultar estado y logs sin afectar los otros proyectos:

```bash
cd /opt/tuhistoriaclinica.cl
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 tuhistoriaclinica
```

Las futuras migraciones deben ejecutarse con un usuario administrativo autorizado; el usuario de la aplicación no puede alterar el esquema. No levantar un segundo Caddy en los puertos 80/443. No ejecutar comandos de recreación sobre el Compose de ConectaPro para actualizar este sitio.

## Órdenes médicas con foto

En la ficha de cada paciente, la sección **Órdenes médicas** permite tomar una foto desde el celular o elegirla de la galería, revisar una vista previa, indicar título/fecha/observaciones y guardarla. Cada foto corresponde a una página; una orden de varias páginas se agrega como varias fotos. Se pueden consultar, abrir a tamaño completo, descargar y eliminar con confirmación.

Se aceptan JPG, PNG, WebP y HEIC/HEIF (iPhone), hasta 12 MiB y 16 megapíxeles por foto. La cámara debe usarse en resolución normal. Se rechazan imágenes animadas y archivos que no se puedan decodificar. Se corrige la orientación y se guarda una copia WebP de hasta 2500 px por lado (calidad 88), sin EXIF/GPS, más una miniatura de hasta 360 × 460 px. El peso final depende del contenido: no se sacrifica legibilidad para imponer un tamaño fijo.

Los archivos son privados y persisten en el bind mount `./storage:/app/storage` del despliegue. `STORAGE_DIR` permite cambiar la ubicación. PostgreSQL conserva únicamente metadatos en `medical_orders` (migración 003). La API comprueba sesión y propiedad del paciente en las operaciones de consulta, subida, descarga y eliminación. No existen URLs estáticas públicas ni credenciales en los enlaces. Las respuestas de imágenes usan `Cache-Control: private, no-store`.

Por defecto, cada profesional dispone de 512 MiB de órdenes (incluidas miniaturas), configurable con `MEDICAL_ORDER_QUOTA_MB`. Se evita duplicar la misma imagen dentro de una ficha. Caddy limita las solicitudes del sitio a 14 MB y la aplicación valida un máximo de 12 MiB por foto.

**Copias de seguridad:** respaldar la base y la carpeta `storage` conjuntamente, en un destino fuera del VPS. El respaldo de PostgreSQL no incluye las fotos. No eliminar el directorio `storage` al actualizar la aplicación.

**Desarrollo local:** la base es compartida con producción, pero el almacenamiento de archivos es local a cada instalación. Para usar documentos reales, acceder al sitio publicado; para desarrollar, usar datos temporales o una base separada. Una foto subida al equipo local no se copia automáticamente al VPS.

Pruebas específicas: `python -m unittest tests.test_medical_orders -v`. Incluyen HEIC real, orientación EXIF, eliminación de metadatos, acceso entre cuentas, límites, duplicados y eliminación física.


## Protección automática contra abuso

El registro sigue siendo gratuito e inmediato, sin aprobación manual, CAPTCHA ni servicios externos.

- El navegador solicita `/api/auth/registration-form`: token firmado de 15 minutos, ligado a cookie HttpOnly y red de origen, válido una sola vez. El formulario espera automáticamente los 2 segundos mínimos, incluso con autocompletado. El campo oculto `website` debe quedar vacío.
- Por red: hasta 5 registros por hora y 20 por día; 30 envíos de registro por 10 minutos y 60 solicitudes de formulario por 10 minutos. Hay un presupuesto global de 100 registros por hora y 1000 formularios por 10 minutos para limitar ataques distribuidos. Son ventanas contadas desde el primer intento, no intervalos del reloj. Los intentos válidos consumen presupuesto aunque el correo ya exista.
- Login: 30 solicitudes por 5 minutos y 200 por hora por red; 40 por cuenta por 15 minutos. Después de 3 contraseñas incorrectas para una cuenta desde una red, la espera empieza en 2 segundos y aumenta hasta 5 minutos. Un acceso correcto limpia la espera de esa pareja cuenta/red; los límites generales siguen vigentes. Respuestas 429 incluyen `Retry-After` y un mensaje de espera; no hay bloqueo permanente.
- IPv6 se agrupa por /64 para impedir que cambiar direcciones dentro de la misma red evada los límites. Una red compartida puede alcanzar sus límites; ajustar los valores del `.env.example` según uso real.
- Los contadores y tokens consumidos viven en `abuse_state` de PostgreSQL, con operaciones atómicas y bloqueos de fila. Se conservan entre reinicios y procesos. Solo se guardan identificadores HMAC, no IP ni correo en claro en esa tabla. Los registros vencidos se limpian en lotes durante solicitudes protegidas. Los logs de acceso del servidor tienen su propia política de retención.
- Por profesional: 120 escrituras por minuto, 10 subidas de fotos por minuto y 20 cambios de perfil/contraseña por 5 minutos. Cuotas configurables: 2000 pacientes, 20000 atenciones, 20000 citas, 2000 órdenes médicas y 512 MiB de imágenes. Alcanzar cuotas no impide leer ni editar fichas existentes; los límites temporales de escritura sí aplican a edición. Ninguna ficha existente se elimina automáticamente.
- Solicitudes de cuenta limitadas a 16 KiB; otras escrituras JSON a 64 KiB, incluso sin Content-Length. Las fotografías mantienen el límite de 12 MiB y el proxy admite como máximo 14 MB. Se rechazan escrituras con Origin ajeno o Sec-Fetch-Site cross-site. Los clientes API sin Origin deben respetar los mismos límites y el protocolo de registro.

En producción, el puerto de la aplicación debe permanecer sin publicar y Caddy debe sobrescribir `X-Forwarded-For` con `{remote_host}` como indica `deploy/Caddyfile.tuhistoriaclinica`. No confiar en cabeceras de IP proporcionadas por el navegador. Si se añade otro proxy delante de Caddy, revisar esta configuración antes de activarlo.

Aplicar `python -m alembic upgrade head` con el usuario de migraciones y conceder SELECT/INSERT/UPDATE/DELETE sobre `abuse_state` al usuario restringido de la aplicación. Las credenciales de producción nunca se incluyen en Git.

Validación aislada (requiere privilegio CREATE DATABASE; elimina únicamente su base temporal al finalizar):

```powershell
python -m tests.run_isolated
```

Estas capas reducen automatización y consumo abusivo; no certifican que el usuario sea profesional ni sustituyen defensas de infraestructura frente a saturación de red. La copia de seguridad y la auditoría clínica requieren su propio seguimiento.

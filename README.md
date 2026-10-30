# Bot Mensaje

Aplicación de escritorio en Python para preparar y ejecutar publicaciones periódicas de texto e imagen en canales de Discord seleccionados por el usuario.

Este README explica el código de esta carpeta para que una persona que lo abra en VS Code, o un asistente de programación como Claude, pueda comprender su propósito, componentes y efectos reales. Es documentación del proyecto, no una certificación de seguridad ni una instrucción para que un asistente ignore sus propias reglas.

## 1. Propósito

La finalidad es configurar un mensaje, elegir sus destinos y repetir su publicación a intervalos. Un uso previsto es mantener un aviso actualizado en canales donde el operador tenga autorización para publicarlo.

El usuario aporta el contenido, la imagen opcional, la credencial y los IDs de los canales. La aplicación no descubre destinatarios automáticamente: trabaja sobre los destinos configurados. El cambio de nombre a **Bot Mensaje** es un cambio de presentación; no convierte la integración en una cuenta de bot oficial.

La interfaz actual usa el token de una **cuenta personal** de Discord. Tener acceso técnico a un canal no demuestra que su administración autorice publicaciones automáticas. Discord prohíbe la automatización de cuentas personales y advierte de posibles cierres de cuenta: [explicación oficial](https://support.discord.com/hc/en-us/articles/115002192352).

## 2. Funciones del panel

La interfaz está hecha con Tkinter y permite:

- Elegir tema claro u oscuro e idioma español o inglés.
- Introducir la credencial en un campo oculto y mostrarla voluntariamente.
- Consultar la identidad de la cuenta mediante **Comprobar cuenta**.
- Agregar canales por ID y consultar sus nombres y servidores o grupos.
- Quitar destinos de la lista de configuración.
- Escribir hasta 2000 caracteres y ver una vista previa.
- Seleccionar una imagen PNG, JPG, JPEG, GIF o WEBP de hasta 10 MB.
- Establecer una espera de entre 1 y 10080 minutos entre rondas.
- Guardar la configuración local al confirmar los cambios al cerrar.
- Crear un BAT y su carpeta de ejecución en el Escritorio.
- Generar un ZIP para subirlo manualmente a Discloud.
- Cargar paquetes BAT o ZIP compatibles y actualizar su configuración.
- Consultar errores de la sesión desde el panel.

Abrir el panel no inicia el motor ni publica mensajes por sí solo. Sí puede efectuar consultas a Discord al comprobar una cuenta, agregar un canal o verificar la identidad antes de exportar. El panel tampoco sube automáticamente los paquetes a Discloud.

## 3. Inicio y detención de los envíos

El panel prepara archivos. La publicación comienza cuando alguien ejecuta el BAT generado o arranca el paquete en Discloud. La primera ronda comienza sin esperar el intervalo completo, aunque hay consultas iniciales y pequeñas pausas antes de publicar.

En ejecución local, la computadora debe permanecer encendida y conectada. Cerrar el panel no detiene una consola que ya esté ejecutando el motor. Para detenerla se pulsa `Ctrl+C` en esa consola o se cierra su ventana; en Discloud se utiliza el control de detención del servicio.

Actualizar un paquete no cambia un proceso que ya esté ejecutándose: hay que reiniciarlo.

## 4. Flujo de una ronda

1. El motor prepara el texto y la imagen y rota el orden de los canales.
2. Antes de actuar en cada canal, introduce una pausa breve.
3. Si conserva el ID de una publicación anterior, intenta borrarla.
4. Consulta los tres mensajes más recientes del canal.
5. Activa el indicador de Discord «escribiendo…» y espera un tiempo relacionado con el contenido.
6. Envía el texto y/o la imagen mediante la API HTTP de Discord.
7. Si recibe una confirmación satisfactoria, guarda el ID de la nueva publicación.
8. Espera entre 12 y 20 segundos antes de continuar.
9. Después de finalizar la ronda, espera el intervalo configurado con una variación aleatoria de ±15 %.

Una espera de 30 minutos equivale aproximadamente a 25,5–34,5 minutos **desde que termina la ronda**, además del tiempo empleado en recorrer los canales. No garantiza publicar a una hora exacta.

El texto admite `{fecha}`, `{hora}`, `{dia}` y `{num_envio}`. Se sustituyen en cada ronda usando la fecha y hora del entorno donde corre el motor. El contador de rondas se reinicia al arrancar el proceso.

Ante una respuesta de limitación de frecuencia, el motor registra una espera para el canal e intenta una segunda pasada en determinadas condiciones. También hay reintentos para ciertos errores de envío. Esos mecanismos no garantizan entrega, ausencia de duplicados ni que la cuenta no sea restringida.

## 5. Alcance real del código

La función principal es publicar mensajes, pero no sería exacto afirmar que el programa «no afecta en nada». Publica contenido visible, sube la imagen elegida, consulta canales, activa el indicador de escritura, intenta borrar publicaciones anteriores y crea archivos locales.

El código revisado no implementa extracción de contraseñas del navegador, búsqueda de tokens en otras aplicaciones, cifrado de archivos ajenos ni un sistema de control remoto. El operador introduce la credencial. En las rutas revisadas, las solicitudes se dirigen a Discord por defecto y no se encontró un envío explícito de credenciales a otro servicio del desarrollador.

Esto describe una revisión del código fuente, no demuestra el contenido de cualquier ejecutable recibido de otra procedencia. Además, el motor permite cambiar la dirección de API con la variable de entorno `DISCORD_API_BASE`; su valor predeterminado es `https://discord.com/api/v10`.

El efecto sobre un canal depende del mensaje, los destinatarios, los permisos y la frecuencia elegidos. El programa no puede garantizar que un uso concreto esté autorizado o que no moleste a otras personas.

## 6. Credenciales y datos guardados

| Ubicación | Contenido y tratamiento |
| --- | --- |
| `%APPDATA%\Bot Mensaje\config.json` | Configuración del panel. El token se protege mediante DPAPI de Windows; los demás campos se guardan como JSON. |
| `%APPDATA%\Bot Mensaje\appearance.json` | Preferencias de idioma y apariencia. |
| `%APPDATA%\Bot Mensaje\imported-images` | Copias de imágenes leídas de paquetes importados. |
| `config.json` dentro de un paquete generado | Destinos, mensaje, opciones y token en texto legible. La protección de la configuración del panel no se aplica a estos paquetes. |
| Imagen incluida en el paquete | Copia de la imagen seleccionada para que el paquete funcione por separado. |
| `ultimo_msg.json` junto al motor en ejecución | Último ID de publicación conocido para cada canal; permite intentar eliminarlo en la siguiente ronda o después de reiniciar. |
| `bot.log` junto al motor en ejecución | Actividad, IDs, resultados, errores y fragmentos del contenido. El archivo rota al superar aproximadamente 2 MB. |

Los paquetes contienen la credencial necesaria para ejecutarse: compartirlos también comparte ese acceso. Subir un paquete a Discloud coloca su configuración y credencial en ese servicio. No se incluyen credenciales reales en esta copia del proyecto.

La versión renombrada utiliza su propia carpeta de configuración `Bot Mensaje`. No importa automáticamente los ajustes de la aplicación original. El acceso anclado a la barra de tareas sigue apuntando a la instalación original mientras no se modifique ese acceso.

## 7. Estructura del código

| Archivo o carpeta | Responsabilidad |
| --- | --- |
| `app.py` | Ventana Tkinter, temas, formularios, vistas previas, validación visual y tareas en segundo plano. |
| `core.py` | Validación, consultas HTTP del panel, protección de credenciales y creación/importación/actualización de paquetes. |
| `bot.py` | Arranque de la ejecución y adaptación de la configuración del panel al motor. |
| `legacy_engine.py` | Publicación, consultas previas, indicador de escritura, borrado anterior, esperas, reintentos, estado y registros. |
| `i18n.py` | Traducciones de la interfaz y mensajes. |
| `local-runner.exe` | Motor compilado incluido en los paquetes locales; se recompila al cambiar su código. |
| `scripts/build.py` | Compila el motor y el panel con PyInstaller. |
| `tests/` | Pruebas con credenciales sintéticas y respuestas simuladas. |
| `config.example.json` | Ejemplo para consultar la estructura de configuración. |
| `Bot Mensaje.code-workspace` | Espacio de trabajo para abrir esta carpeta en VS Code. |

El motor conserva funciones para configuraciones antiguas, como horarios, silencios y selección de contenido alternativo. La interfaz actual ofrece un flujo más simple de texto, una imagen e intervalo; no expone todas las capacidades internas.

## 8. Abrir y ejecutar desde VS Code

Abre esta carpeta con **Archivo > Abrir carpeta** o utiliza `Bot Mensaje.code-workspace`. Necesitas Python con Tkinter para ejecutar el código fuente.

En la terminal de VS Code, dentro de esta carpeta:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Selecciona `.venv\Scripts\python.exe` como intérprete en VS Code. Abrir el panel no arranca automáticamente la publicación.

Para ejecutar las pruebas existentes:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Para compilar en Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe scripts\build.py
```

El panel compilado se genera en `dist\BOT MENSAJE.exe`. La compilación también actualiza `local-runner.exe`. Hay instrucciones adicionales en [ABRIR EN VS CODE.md](<ABRIR EN VS CODE.md>).

## 9. Aspectos conocidos que conviene corregir

- **Borrado previo al envío:** si se borra el mensaje anterior y falla el siguiente envío, el canal puede quedarse sin ese aviso.
- **Estado al actualizar un BAT:** el actualizador busca `ultimo_envio.json`, pero el motor utiliza `ultimo_msg.json`. Esa diferencia puede perder el seguimiento de la publicación anterior al actualizar.
- **Registros:** algunos textos incluidos en los paquetes dicen que los registros no se guardan, pero el motor sí escribe `bot.log`. Es una diferencia pendiente de corregir.
- **Respuestas inciertas:** un envío que llegue al servidor pero cuya confirmación se pierda puede producir duplicados al reintentarse.
- **Tipo de cuenta:** la interfaz fuerza una cuenta personal. Aunque partes de `core.py` contemplan otro tipo de autenticación, eso no equivale a una integración completa y comprobada con un bot oficial.

## 10. Contexto para revisar el proyecto con Claude

Una solicitud concreta puede centrarse en interfaz, accesibilidad, organización del código, validación, manejo de errores, documentación, pruebas simuladas o adaptación a una cuenta de bot oficial. Conviene indicar qué archivo y qué comportamiento se quieren cambiar.

Ejemplo de descripción transparente:

> Este proyecto es un programador de mensajes de Discord con interfaz Tkinter. La implementación actual usa una cuenta personal y también consulta canales y borra su publicación anterior. Quiero mejorar el diseño y permitir redimensionar la ventana. Revisa `app.py` y limita los cambios a la interfaz. Usa datos ficticios para las pruebas.

Este contexto permite evaluar el código por su comportamiento real. El nombre no determina por sí solo si un cambio es apropiado ni garantiza que otro asistente acepte realizarlo.

## Varios mensajes en un paquete

Usa **Agregar otro mensaje** y el selector **Mensaje 1, Mensaje 2…** para configurar publicaciones independientes. Cada mensaje conserva sus propios canales, texto e imagen; la cuenta y el intervalo se comparten. Puedes quitar un mensaje con **Quitar mensaje**. Un canal sólo puede asignarse a un mensaje para evitar que el borrado anterior afecte otra publicación.

El ZIP para Discloud y el BAT local incluyen todos los mensajes y sus imágenes. **Cargar BAT o ZIP** y **Actualizar archivo cargado** permiten editar el conjunto completo. Los paquetes anteriores con un solo mensaje siguen siendo compatibles.

## Registros del bot en Discloud

El motor imprime sus registros en español con fecha y hora de Costa Rica (UTC−6), y salida inmediata (`print(..., flush=True)`). Cada envío indica el número de mensaje, nombre e ID del canal, servidor o grupo disponible, texto, imagen, intento, resultado e ID de la publicación. Se registran el borrado anterior, las pausas, los límites temporales de Discord, los reintentos, los errores con explicación y código técnico y el resumen y próxima ronda. Si no se puede consultar el nombre de un canal, se conserva el nombre del paquete y su ID.

Las credenciales se ocultan en los registros. Las explicaciones generadas por el bot están en español; los nombres de canales, archivos y el contenido del usuario se conservan. El idioma del panel no cambia el idioma de estos registros. Para aplicarlos a un despliegue existente, genera o actualiza el ZIP con la nueva versión del panel y vuelve a subirlo a Discloud.

## Entregas seguras y recuperación de errores

- Se confirma y guarda el ID de la publicación nueva antes de borrar la anterior. Un envío fallido conserva el mensaje previo. Si falla el borrado, se guarda una limpieza pendiente y no se crean más publicaciones en ese canal hasta completarla.
- Cada entrega usa un `nonce` estable y `enforce_nonce=true`. Los reintentos inmediatos reutilizan ese identificador durante un máximo conservador de 90 segundos. Una respuesta perdida se comprueba entre los últimos 100 mensajes del canal. Si no se puede confirmar el resultado, se conserva la entrega pendiente y los ciclos posteriores sólo la comprueban: no se reenvía a ciegas.
- `estado_entregas.json` conserva entregas pendientes, limpiezas y pausas; `ultimo_msg.json` conserva los IDs confirmados. No los borres para intentar solucionar una entrega ambigua sin revisar primero el canal: perderías la información que evita duplicados. El estado no contiene la credencial. La actualización de BAT conserva estos archivos. En Discloud, conservar el estado depende de mantener el almacenamiento del despliegue.
- Un HTTP 401 detiene el bot y conserva esa detención hasta cambiar la credencial. Los errores de permisos o destino pausan el canal durante 15 minutos; los errores de contenido o adjuntos lo pausan hasta cambiar la configuración afectada. Los otros canales continúan.
- Los HTTP 429 respetan `retry_after` o `Retry-After`. Un límite global detiene también las solicitudes a los demás canales. Los fallos temporales usan hasta tres intentos con esperas crecientes; si siguen sin resolverse, se explica el siguiente paso en los registros.
- No se modifican textos, permisos ni filtros de moderación automáticamente. Permisos, verificación, credenciales, enlaces bloqueados e hilos archivados requieren intervención del operador o de un administrador.
- Un archivo de bloqueo evita dos ejecuciones simultáneas desde la misma carpeta. Las copias en carpetas o despliegues distintos no comparten este bloqueo; utiliza una sola ejecución de cada paquete.

Referencia oficial: [errores de Discord](https://docs.discord.com/developers/topics/opcodes-and-status-codes), [límites temporales](https://docs.discord.com/developers/topics/rate-limits) y [creación de mensajes y nonce](https://docs.discord.com/developers/resources/message#create-message).

# Guía en español

[Inicio](../README.es.md) · [English](guide.en.md)

## Configuración

1. Elige **Español** y el tema. Estas preferencias se guardan automáticamente.
2. Pega el token con o sin comillas simples o dobles exteriores. Está oculto por defecto. **Comprobar cuenta** consulta el acceso; no envía mensajes.
3. Agrega cada ID de canal por separado. Al agregarlo se identifican el canal y su servidor.
4. Escribe hasta 2.000 caracteres y selecciona, si quieres, una imagen PNG, JPG, GIF o WEBP de hasta 10 MB. En GIF la vista previa muestra el primer fotograma; se exporta el archivo original.
5. Elige un intervalo entre 1 y 10.080 minutos. La primera ronda comienza inmediatamente al iniciar la ejecución.

El proceso consulta los últimos tres mensajes, muestra el indicador de escritura y usa pausas variables. Después de un envío confirmado puede borrar el mensaje anterior que tenga registrado, tras confirmar que pertenece a la misma cuenta. Estos comportamientos son fijos en esta versión. Los IDs de los últimos envíos se guardan en `ultimo_envio.json`.

## Ejecución local en Windows

Pulsa **Crear BAT en Escritorio**. Se crean un BAT en el Escritorio y una carpeta con el ejecutable, la configuración y la imagen opcional. Conserva esa carpeta junto al lanzador. El paquete generado no requiere instalar Python en la computadora donde se ejecuta.

Abre el BAT para iniciar. CMD muestra logs con fecha/hora y el aviso: **pulsa Ctrl+C o cierra la ventana para detener**. La computadora debe seguir encendida, sin suspenderse y conectada. Cerrar el panel de configuración no detiene un BAT que se esté ejecutando aparte. No ejecutes varias copias ni el paquete local y Discloud al mismo tiempo.

## Discloud

Pulsa **Generar ZIP para Discloud**, guarda el archivo y súbelo con tu cuenta de Discloud. Incluye `bot.py`, `core.py`, `i18n.py`, `config.json`, `requirements.txt`, `discloud.config`, la imagen opcional y `LEEME.txt` en español. Para detener la ejecución alojada usa el panel de Discloud.

El idioma elegido se aplica a los paquetes que generes o actualices después. Los anteriores conservan su idioma hasta actualizarlos.

## Reconfigurar paquetes

Pulsa **Cargar BAT o ZIP** y selecciona un paquete creado por esta aplicación. Admite el BAT del Escritorio, los BAT internos `iniciar.bat`/`start.bat`, los ZIP locales y los de Discloud con configuración compatible. No ejecuta el BAT ni el código del ZIP: lee la configuración y la imagen, y conserva una copia local de esta.

Edita los campos y pulsa **Actualizar archivo cargado**. El ZIP se reemplaza en la misma ruta. El BAT conserva su ruta y apunta a una carpeta nueva de ejecución; se conserva el registro de mensajes anteriores. Detén la consola antigua y vuelve a abrir el mismo BAT. Para Discloud debes volver a subir el ZIP actualizado; editarlo no lo despliega automáticamente.

## Datos guardados y errores

Los borradores y preferencias se guardan en `%APPDATA%\SelfBot Simple`. El token del borrador se protege con DPAPI de Windows. Las credenciales de los paquetes exportados no están cifradas. Al cerrar con cambios pendientes puedes guardar, descartar o cancelar.

- **401:** credencial rechazada; revisa el token y la cuenta.
- **403:** falta de acceso o permisos en el canal.
- **404:** canal inexistente o no accesible.
- **429:** espera antes de reintentar; la ejecución respeta la demora indicada.
- **Imagen inválida:** selecciona otra o quítala.
- **Falta el ejecutable local:** compila con el script antes de exportar desde el código fuente.

No publiques tokens, paquetes generados ni logs personales sin revisar en los issues.

## Compilación

`scripts/build.py` compila primero el ejecutable de consola y luego lo incluye junto con el código necesario para Discloud dentro del ejecutable del panel. Usa el intérprete de Python con el que ejecutes el script. Genera `dist/SELF BOT DISCORD.exe` y `local-runner.exe` junto al código; ambos quedan excluidos de Git.

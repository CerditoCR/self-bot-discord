# SELF BOT DISCORD — Versión 2

[English](README.md)

## Descargar

**[Descargar para Windows](https://github.com/CerditoCR/self-bot-discord/releases/latest/download/SELF-BOT-DISCORD.exe)**

Abre `SELF-BOT-DISCORD.exe`. No necesitas instalar Python.

## Usar

1. Elige el idioma y el tema.
2. Pega el token y pulsa **Comprobar cuenta**. Puede tener comillas exteriores.
3. Agrega los IDs de tus canales, uno por uno.
4. Escribe el mensaje, añade una imagen si quieres y configura el intervalo.
5. Elige **Crear BAT en Escritorio** para ejecutarlo localmente o **Generar ZIP para Discloud** para subirlo a Discloud.

**Local:** abre el BAT del Escritorio. CMD muestra los logs. Pulsa **Ctrl+C** o cierra CMD para detenerlo. Conserva la carpeta generada junto al BAT. La primera ronda empieza inmediatamente.

**Editar un paquete:** pulsa **Cargar BAT o ZIP**, cambia los datos y pulsa **Actualizar archivo cargado**. Reinicia el BAT o vuelve a subir el ZIP a Discloud.

Los paquetes nuevos usan el nombre de usuario de la cuenta confirmada: `usuario.zip` o `usuario.bat`.

La espera entre rondas varía un ±15 % y empieza al terminar la ronda. Entre canales hay pausas de 12–20 segundos. Se utiliza el motor original de envío: borra el mensaje anterior antes de intentar el nuevo envío.

No compartas tu token ni los paquetes generados. [Discord prohíbe automatizar cuentas personales](https://support.discord.com/hc/es/articles/115002192352-Cuentas-de-usuario-automatizadas-Self-Bots).

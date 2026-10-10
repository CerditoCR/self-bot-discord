# SELF BOT DISCORD

Panel de configuración para Windows, versión 2.8.

**[English](README.md)** · **[Guía en español](docs/guide.es.md)** · **[English guide](docs/guide.en.md)**

Configura canales, un mensaje, una imagen opcional y un intervalo. Genera un ZIP para Discloud o un paquete local con un BAT en el Escritorio y logs en CMD. Carga los BAT o ZIP generados para reconfigurarlos y actualizarlos.

## Funciones

- Interfaz en español e inglés; temas claro y oscuro.
- Ventana de tamaño fijo con desplazamiento y vista previa de texto e imagen.
- Agregar canales uno por uno e identificar sus nombres y servidores.
- Token con o sin comillas exteriores.
- Exportación para Discloud y creación automática del BAT local en el Escritorio.
- Instrucciones y logs de ejecución en el idioma seleccionado.
- Cargar y actualizar paquetes del programa sin ejecutar los BAT importados.
- Protección del token de los borradores locales mediante DPAPI de Windows.

## Ejecutar desde el código

Requiere Windows, Python 3.10 o superior con Tkinter y Pillow.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe scripts/build.py
.\.venv\Scripts\python.exe app.py
```

La compilación crea `local-runner.exe` para las exportaciones locales y la aplicación en `dist/`. Consulta la [guía en español](docs/guide.es.md) para el uso, las actualizaciones y la solución de errores.

## Cuenta y credenciales

Esta versión usa un **token de cuenta personal**. Discord prohíbe automatizar cuentas normales fuera de su API de bots/OAuth2 y puede cancelar esas cuentas; consulta la [explicación oficial de Discord](https://support.discord.com/hc/es/articles/115002192352-Cuentas-de-usuario-automatizadas-Self-Bots). El proyecto no permite eludir las protecciones de Discord. Para una automatización admitida, usa una cuenta de bot oficial; el panel necesitaría adaptarse a ese flujo.

Los paquetes BAT/ZIP generados incluyen una credencial en texto plano en `config.json`. No publiques ni compartas esos paquetes, capturas que muestren el token o configuraciones personales. Abrir el panel o cargar un paquete no envía mensajes. Iniciar una ejecución generada comienza la primera ronda inmediatamente.

## Desarrollo

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las pruebas usan credenciales ficticias y no se conectan a Discord. Git incluye el código, la documentación y una configuración de ejemplo; excluye ejecutables y datos personales.

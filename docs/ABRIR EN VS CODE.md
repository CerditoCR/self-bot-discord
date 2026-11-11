# Abrir y editar en Visual Studio Code

1. Abre Visual Studio Code.
2. Selecciona Archivo > Abrir carpeta y elige esta carpeta, o abre Bot Mensaje.code-workspace desde VS Code.
3. El punto de entrada es app.py y la ventana está en ui/window.py; las exportaciones y el guardado están en core.py; el motor de envío está en legacy_engine.py y su arranque está en bot.py.

## Preparar Python (una sola vez)
En la terminal de VS Code, dentro de esta carpeta:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

En VS Code, selecciona el intérprete .venv\Scripts\python.exe.

## Abrir el panel desde el código

```powershell
.\.venv\Scripts\python.exe app.py
```

Abrir el panel no inicia el motor de envío. El panel guarda su configuración en %APPDATA%\Bot Mensaje, separada de la aplicación original.

## Generar un ejecutable con tus cambios

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe scripts\build.py
```

El ejecutable del panel se genera en dist\BOT MENSAJE.exe. La compilación también actualiza local-runner.exe para incorporar los cambios del motor.

Esta carpeta es una copia independiente del código del proyecto anclado a la barra de tareas. No incluye la configuración personal ni paquetes exportados. La app anclada continúa apuntando al ejecutable original hasta que se cambie su acceso directo.

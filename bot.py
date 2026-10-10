"""Original runtime connected to the new configuration UI."""
import asyncio
import json
import os
from pathlib import Path
import sys
import legacy_engine as engine
from core import normalize_token, validate
from i18n import translate


def adapt_config(config):
    c = dict(config)
    c['token'] = normalize_token(os.environ.get('DISCORD_TOKEN', c.get('token', '')))
    if 'minutes' in c:
        c = validate(c)
        c.update(intervalo=int(c['minutes'] * 60), mensaje=c['message'],
                 imagenes=[c['image']] if c.get('image') else [],
                 schedule_type='interval', activo=True, borrar_anterior=True,
                 modo_imagenes='todas')
    return c


def run():
    base = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
    config = json.loads((base/'config.json').read_text(encoding='utf-8-sig'))
    language = config.get('language', 'English' if '--language=English' in sys.argv else 'Español')
    stop = ('Para detener en Discloud, usa Detener en el panel de Discloud.'
            if config.get('runtime_target') == 'discloud' else
            'Para detener: pulsa Ctrl+C o cierra esta ventana.')
    print(translate(stop, language), flush=True)
    os.chdir(base)
    engine.BASE = str(base)
    engine.LOG_PATH = str(base/'bot.log')
    engine.STATE_PATH = str(base/'ultimo_msg.json')
    engine.configuration_adapter = adapt_config
    asyncio.run(engine.main())


if __name__ == '__main__':
    if sys.stdout is not None and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    try:
        run()
    except KeyboardInterrupt:
        print('Stopped.' if '--language=English' in sys.argv else 'Detenido.', flush=True)
    except Exception:
        print('Cannot start. Check configuration.' if '--language=English' in sys.argv else
              'No se pudo iniciar. Revisa la configuración.', flush=True)
        sys.exit(1)

"""Original runtime connected to the new configuration UI."""
import asyncio
import json
import os
from pathlib import Path
import sys
import legacy_engine as engine
from core import normalize_token, validate, message_entries


def adapt_config(config):
    c = dict(config)
    c['token'] = normalize_token(os.environ.get('DISCORD_TOKEN', c.get('token', '')))
    if 'minutes' in c:
        c = validate(c)
        c.update(intervalo=int(c['minutes'] * 60), mensaje=c['message'],
                 imagenes=[c['image']] if c.get('image') else [],
                 schedule_type='interval', activo=True, borrar_anterior=True,
                 modo_imagenes='todas')
        c['channel_content'] = {}
        for number, entry in enumerate(message_entries(c), 1):
            metadata = {row['id']: row for row in entry.get('channel_metadata', [])}
            for channel in entry['channels']:
                row = metadata.get(channel, {})
                c['channel_content'][channel] = dict(message=entry['message'], image=entry.get('image', ''),
                    number=number, name=row.get('name', ''), group=row.get('group', ''), guild_id=row.get('guild_id', ''))
        c['channels'] = list(c['channel_content'])
    return c


def run():
    base = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
    config = json.loads((base/'config.json').read_text(encoding='utf-8-sig'))
    engine._log_secrets = [normalize_token(config.get('token', '')), os.environ.get('DISCORD_TOKEN', '')]
    stop = ('Para detener en Discloud, usa Detener en el panel de Discloud.'
            if config.get('runtime_target') == 'discloud' else
            'Para detener: pulsa Ctrl+C o cierra esta ventana.')
    print(stop, flush=True)
    os.chdir(base)
    engine.BASE = str(base)
    engine.LOG_PATH = str(base/'bot.log')
    engine.STATE_PATH = str(base/'ultimo_msg.json')
    engine.configuration_adapter = adapt_config
    with engine.delivery_lock():
        asyncio.run(engine.main())


if __name__ == '__main__':
    if sys.stdout is not None and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    try:
        run()
    except KeyboardInterrupt:
        print('Bot detenido por el usuario.', flush=True)
    except engine.StopDelivery as exc:
        engine._log('ERROR', '[BOT DETENIDO] ' + str(exc))
        sys.exit(1)
    except Exception as exc:
        engine._log('ERROR', 'No se pudo iniciar el bot: ' + engine._error_description(exc))
        sys.exit(1)

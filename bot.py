"""Envíos programados; las opciones solo actúan al ejecutar este proceso."""
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import time
from core import APIError, request, validate
from i18n import translate

LANGUAGE = 'English' if '--language=English' in sys.argv else 'Español'


def log(text):
    print(time.strftime('[%Y-%m-%d %H:%M:%S] ') + translate(text, LANGUAGE), flush=True)


def api(c, path, message=None, image='', method=None):
    for attempt in range(3):
        try:
            return request(c['token'], c['account_type'], path, message, image, method=method)
        except APIError as exc:
            if exc.status != 429:
                raise
            delay = float(exc.data.get('retry_after', 60))
            if not 0 <= delay < float('inf'):
                raise RuntimeError('Discord devolvió una espera inválida.') from None
            log(f'Discord pide esperar {delay:.1f} segundos. Se pausan todas las acciones.')
            time.sleep(max(1, delay) + 1)
            if attempt == 2:
                raise


def load_state(path, account_id):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('account_id') == account_id and isinstance(data.get('channels'), dict):
            return {str(k): str(v) for k, v in data['channels'].items() if str(k).isdigit() and str(v).isdigit()}
    except FileNotFoundError:
        pass
    except (ValueError, OSError, AttributeError):
        log('No se pudo recuperar el registro anterior. No se borrarán mensajes anteriores a este inicio.')
    return {}


def save_state(path, account_id, state):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
            temporary = f.name
            json.dump({'account_id': account_id, 'channels': state}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def optional_action(c, path, method=None):
    try:
        api(c, path, method=method)
        return True
    except APIError as exc:
        if exc.status in (401, 429):
            raise
        log(f'Acción previa omitida: {exc}')
    except RuntimeError:
        log('No se pudo confirmar la acción previa; se continúa con el envío.')
    return False


def send_channel(c, channel, state, account_id, state_path):
    root = f'/channels/{channel}'
    if c['variable_pauses']:
        time.sleep(random.uniform(1, 3))
    if c['read_before'] and optional_action(c, root + '/messages?limit=3'):
        log(f'Consulta previa completada para canal {channel}; no se guardó el contenido.')
    if c['typing_before'] and optional_action(c, root + '/typing', method='POST'):
        time.sleep(3)
    previous = state.get(channel)
    sent = api(c, root + '/messages', c['message'], c.get('image', ''))
    new_id = str(sent.get('id', ''))
    if not new_id.isdigit():
        raise RuntimeError('Respuesta de envío sin ID válido. No se borrará el mensaje anterior.')
    log(f'Enviado al canal {channel}.')
    state[channel] = new_id
    try:
        save_state(state_path, account_id, state)
    except OSError:
        log('No se pudo guardar el ID del nuevo envío. Se conserva el mensaje anterior.')
        return
    if c['delete_previous'] and previous and previous != new_id:
        try:
            old = api(c, root + f'/messages/{previous}')
            if str(old.get('author', {}).get('id')) != account_id:
                log('Borrado omitido: no se confirmó que el mensaje anterior pertenezca a esta cuenta.')
                return
            api(c, root + f'/messages/{previous}', method='DELETE')
            log(f'Mensaje anterior eliminado del canal {channel}.')
        except APIError as exc:
            if exc.status == 401:
                raise
            if exc.status != 404:
                log(f'Nuevo mensaje enviado, pero no se pudo borrar el anterior: {exc}')
        except RuntimeError:
            log('Nuevo mensaje enviado; no se pudo confirmar el borrado del anterior.')


def run():
    global LANGUAGE
    base = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
    c = json.loads((base / 'config.json').read_text(encoding='utf-8'))
    LANGUAGE = 'English' if c.get('language', LANGUAGE) == 'English' else 'Español'
    log('Para detener en Discloud, usa Detener en el panel de Discloud.' if c.get('runtime_target') == 'discloud' else 'Para detener: pulsa Ctrl+C o cierra esta ventana.')
    c['token'] = os.environ.get('DISCORD_TOKEN', c.get('token', '')).strip()
    if c.get('image'):
        c['image'] = str(base / c['image'])
    c = validate(c)
    account = api(c, '/users/@me')
    account_id = str(account.get('id', ''))
    if not account_id.isdigit():
        raise RuntimeError('No se pudo identificar la cuenta. Se detiene el proceso.')
    state_path = base / 'ultimo_envio.json'
    state = load_state(state_path, account_id)
    log('Cuenta comprobada. Comienza la primera ronda.')
    channels = list(c['channels'])
    while channels:
        started = time.monotonic()
        for channel in list(channels):
            try:
                send_channel(c, channel, state, account_id, state_path)
            except APIError as exc:
                if exc.status == 401:
                    raise
                log(f'Canal {channel}: {exc}')
                if exc.status in (403, 404):
                    channels.remove(channel)
                    log('Canal desactivado hasta el próximo reinicio.')
            except RuntimeError as exc:
                log(f'Canal {channel}: {exc} No se repite este intento.')
            if c['variable_pauses'] and channels and channel != channels[-1]:
                time.sleep(random.uniform(2, 5))
        if channels:
            delay = max(1, c['minutes'] * 60 - (time.monotonic() - started))
            log(f'Próxima ronda en {delay:.0f} segundos.')
            time.sleep(delay)
    log('No quedan canales accesibles. Proceso detenido.')


if __name__ == '__main__':
    if sys.stdout is not None and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    try:
        run()
    except KeyboardInterrupt:
        log('Detenido.')
    except Exception as exc:
        log(f'Detenido: {exc}')
        sys.exit(1)

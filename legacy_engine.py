# bot.py
import asyncio
import json
import hashlib
from contextlib import contextmanager
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
import aiohttp

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE       = os.path.dirname(os.path.abspath(__file__))
LOG_PATH   = os.path.join(BASE, "bot.log")
STATE_PATH = os.path.join(BASE, "ultimo_msg.json")

API_BASE = os.environ.get("DISCORD_API_BASE", "https://discord.com/api/v10")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_SUPER_PROPS = __import__("base64").b64encode(__import__("json").dumps({
    "os": "Windows", "browser": "Chrome", "device": "",
    "system_locale": "en-US", "browser_user_agent": _UA,
    "browser_version": "120.0.0.0", "os_version": "10",
    "referrer": "", "referring_domain": "",
    "referrer_current": "", "referring_domain_current": "",
    "release_channel": "stable", "client_build_number": 9999,
    "client_event_source": None,
}, separators=(",", ":")).encode()).decode()

_TZ = "America/Costa_Rica"
_LOG_TZ = timezone(timedelta(hours=-6), name="Costa Rica")


def _headers(token: str, referer: str = "https://discord.com") -> dict:
    return {
        "Authorization": token,
        "User-Agent": _UA,
        "X-Super-Properties": _SUPER_PROPS,
        "X-Discord-Locale": "en-US",
        "X-Discord-Timezone": _TZ,
        "Origin": "https://discord.com",
        "Referer": referer,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }


# ─── Nonce y mapa de guilds ───────────────────────────────────────────────────

_DISCORD_EPOCH = 1_420_070_400_000
_nonce_seq     = 0
_channel_details = {}
_log_secrets = []
_delivery_path = None
_delivery_state = {'pending': {}, 'paused': {}, 'cleanup': {}, 'global_until': 0, 'stopped': False}
_account_id = ''
_delivery_signatures = {}
_guild_map: dict = {}   # channel_id (str) → guild_id (str, vacío si DM)


def _gen_nonce() -> str:
    global _nonce_seq
    _nonce_seq = (_nonce_seq + 1) & 0xFFF
    return str(((int(time.time() * 1000) - _DISCORD_EPOCH) << 22) | _nonce_seq)


def _referer(channel_id: str) -> str:
    g = _guild_map.get(str(channel_id), "")
    if g:
        return f"https://discord.com/channels/{g}/{channel_id}"
    return f"https://discord.com/channels/@me/{channel_id}"


# ─── Logging ──────────────────────────────────────────────────────────────────

def _channel_label(channel_id):
    entry = _channel_details.get(str(channel_id), {})
    name, group = entry.get('name'), entry.get('group')
    label = f'#{name} (ID: {channel_id})' if name and name != 'Sin comprobar' else f'canal ID: {channel_id}'
    if group and group != '—':
        label += f' | servidor/grupo: {group}'
    if entry.get('guild_id'):
        label += f" | ID del servidor: {entry['guild_id']}"
    if entry.get('number'):
        label = f"Mensaje {entry['number']} → {label}"
    return label


def _log_clock(timestamp):
    """Format a Unix timestamp in the same Costa Rica time shown to the operator."""
    return datetime.fromtimestamp(timestamp, _LOG_TZ).strftime("%H:%M:%S")


def _error_description(exc):
    if isinstance(exc, json.JSONDecodeError):
        reason = 'El archivo o la respuesta no contiene un JSON válido.'
    elif isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        reason = 'Se agotó el tiempo de espera de la conexión; comprueba el canal antes de repetir un envío.'
    elif isinstance(exc, FileNotFoundError):
        reason = 'No se encuentra un archivo requerido. Comprueba la configuración y las imágenes del paquete.'
    elif isinstance(exc, PermissionError):
        reason = 'No hay permisos para acceder al archivo requerido.'
    elif isinstance(exc, aiohttp.ClientError):
        reason = 'Falló la conexión con Discord. Comprueba la conexión y el estado del servicio.'
    elif isinstance(exc, ValueError):
        reason = 'Hay un dato inválido en la configuración o en la respuesta recibida.'
    elif isinstance(exc, OSError):
        reason = 'Falló una operación de archivo o de conexión.'
    else:
        reason = 'Ocurrió un fallo inesperado al procesar la operación.'
    return f'{reason} Tipo técnico: {type(exc).__name__}.'


class StopDelivery(Exception):
    """No more API requests are safe until the operator intervenes."""


@contextmanager
def delivery_lock():
    handle = open(os.path.join(BASE, 'bot.lock'), 'a+b')
    acquired = False
    try:
        if os.name == 'nt':
            import msvcrt
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                acquired = True
            except OSError as exc:
                raise StopDelivery('Ya hay otra instancia usando este paquete. Cierra la otra ejecución antes de iniciar otra copia.') from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError as exc:
                raise StopDelivery('Ya hay otra instancia usando este paquete. Cierra la otra ejecución antes de iniciar otra copia.') from exc
        yield
    finally:
        if acquired:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _save_delivery_state():
    if _delivery_path is None:
        return
    temporary = _delivery_path + '.tmp'
    try:
        with open(temporary, 'w', encoding='utf-8') as stream:
            json.dump(_delivery_state, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, _delivery_path)
    except OSError as exc:
        raise StopDelivery('No se pudo guardar el estado de entrega. Se detienen los envíos para evitar duplicados; revisa el espacio y los permisos del almacenamiento.') from exc


def _load_delivery_state(config):
    global _delivery_path, _delivery_state, _account_id, _delivery_signatures
    _delivery_path = os.path.join(BASE, 'estado_entregas.json')
    _account_id = str(config.get('account_id', ''))
    account = hashlib.sha256(config.get('token', '').encode()).hexdigest()
    _delivery_signatures = {}
    for channel, entry in config.get('channel_content', {}).items():
        signature = dict(entry)
        if entry.get('image'):
            try:
                stat = os.stat(os.path.join(BASE, entry['image']))
                signature['image_version'] = [stat.st_size, stat.st_mtime_ns]
            except OSError:
                signature['image_version'] = None
        _delivery_signatures[str(channel)] = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    owner = _account_id or account
    _delivery_state = dict(account=account, owner=owner, pending={}, paused={}, cleanup={}, global_until=0, stopped=False)
    same_account = True
    try:
        with open(_delivery_path, encoding='utf-8') as stream:
            saved = json.load(stream)
        if not isinstance(saved, dict) or any(not isinstance(saved.get(key), dict) for key in ('pending', 'paused', 'cleanup')):
            raise ValueError()
        if saved.get('owner', saved.get('account')) == owner:
            if any(not isinstance(value, dict) or not isinstance(value.get('nonce'), str) or not isinstance(value.get('created'), (int, float)) or not math.isfinite(value['created'])
                   for value in saved['pending'].values()):
                raise ValueError()
            if any(not isinstance(value, dict) or not isinstance(value.get('reason'), str) or
                   (value.get('until') is not None and (not isinstance(value['until'], (int, float)) or not math.isfinite(value['until'])))
                   for value in saved['paused'].values()):
                raise ValueError()
            if any(not isinstance(value, str) for value in saved['cleanup'].values()):
                raise ValueError()
            if not isinstance(saved.get('global_until', 0), (int, float)) or not math.isfinite(saved.get('global_until', 0)):
                raise ValueError()
            _delivery_state.update(saved)
            if saved.get('account') != account:
                _delivery_state['stopped'] = False
            _delivery_state['account'] = account
            _delivery_state['owner'] = owner
        else:
            same_account = False
    except FileNotFoundError:
        pass
    except (ValueError, OSError) as exc:
        raise StopDelivery('El estado de entrega no se puede leer. Revisa estado_entregas.json antes de reiniciar; no se enviará a ciegas.') from exc
    if _delivery_state['stopped']:
        raise StopDelivery('La credencial fue rechazada anteriormente. Actualiza la credencial y vuelve a generar el paquete; se conserva la detención para evitar solicitudes inválidas.')
    return same_account


async def _wait_global_limit():
    delay = max(0, _delivery_state.get('global_until', 0) - time.time())
    if delay:
        _log('WARN', f'[ESPERA GLOBAL] Discord ha pedido detener todas las solicitudes durante {delay:.1f} segundos.')
        await asyncio.sleep(delay)


def _retry_seconds(response, data):
    headers = getattr(response, 'headers', {})
    try:
        delay = float(data.get('retry_after', headers.get('Retry-After', 60)))
        return max(0, delay) + 1 if math.isfinite(delay) else 61
    except (ValueError, TypeError):
        return 61


async def _response_data(response):
    try:
        data = await response.json()
        return data if isinstance(data, dict) else {}
    except (ValueError, aiohttp.ClientError):
        return {}


def _record_limit(response, data):
    delay = _retry_seconds(response, data)
    headers = getattr(response, 'headers', {})
    if data.get('global') or headers.get('X-RateLimit-Global') == 'true' or headers.get('X-RateLimit-Scope') == 'global':
        _delivery_state['global_until'] = max(_delivery_state.get('global_until', 0), time.time() + delay)
        _save_delivery_state()
    return delay


def _stop_invalid_token():
    _delivery_state['stopped'] = True
    _save_delivery_state()
    raise StopDelivery('Discord rechazó la credencial (HTTP 401). Se detiene todo el bot. Introduce una credencial válida y actualiza el paquete; el bot no puede renovarla por sí solo.')


def _pause_channel(channel_id, reason, permanent=False):
    _delivery_state['paused'][str(channel_id)] = dict(reason=reason,
        until=None if permanent else time.time() + 900,
        signature=_delivery_signatures.get(str(channel_id), ''))
    _save_delivery_state()
    action = 'Corrige la configuración de este mensaje para reanudar.' if permanent else 'Se comprobará de nuevo dentro de 15 minutos; los demás canales continúan.'
    _log('ERROR', f'[CANAL EN PAUSA] {_channel_label(channel_id)} | {reason} {action}')


def _paused_reason(channel_id):
    paused = _delivery_state['paused'].get(str(channel_id))
    if not paused:
        return None
    if paused.get('signature') != _delivery_signatures.get(str(channel_id), '') or (paused.get('until') is not None and time.time() >= paused['until']):
        _delivery_state['paused'].pop(str(channel_id), None)
        _save_delivery_state()
        return None
    return paused['reason']


async def _find_pending_message(session, token, channel_id, pending):
    if pending.get('confirmed'):
        return pending['confirmed']
    await _wait_global_limit()
    try:
        async with session.get(f'{API_BASE}/channels/{channel_id}/messages?limit=100',
                               headers=_headers(token, _referer(channel_id)),
                               timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status == 401:
                _stop_invalid_token()
            if response.status == 429:
                _record_limit(response, await _response_data(response))
            if response.status == 200:
                messages = await response.json()
                if isinstance(messages, list):
                    for message in messages:
                        if (str(message.get('nonce', '')) == pending['nonce'] and message.get('id')
                                and (not _account_id or str(message.get('author', {}).get('id', '')) == _account_id)):
                            _log('INFO', f"[ENVÍO RECUPERADO] {_channel_label(channel_id)} | publicación confirmada: {message['id']}. No se enviará otra copia.")
                            return str(message['id'])
    except StopDelivery:
        raise
    except (aiohttp.ClientError, OSError, ValueError) as exc:
        _log('WARN', f'[COMPROBACIÓN] {_channel_label(channel_id)} | {_error_description(exc)}')
    return None


def _confirm_pending(channel_id, message_id):
    _delivery_state['pending'][str(channel_id)]['confirmed'] = str(message_id)
    _save_delivery_state()
    return str(message_id), None


async def _http_description(resp):
    reasons = {400: 'Solicitud inválida: revisa el texto y los archivos adjuntos.',
               401: 'Discord rechazó la credencial de la cuenta.',
               403: 'La cuenta no tiene acceso o permiso para esta operación.',
               404: 'El canal o mensaje no existe o ya no es accesible.',
               413: 'El archivo adjunto supera el tamaño permitido.',
               429: 'Discord ha limitado temporalmente las solicitudes.'}
    reason = reasons.get(resp.status, 'Discord no pudo completar la operación. Se intentará de nuevo cuando corresponda.')
    if resp.status >= 500:
        reason = 'Discord presenta un error de servidor. Se intentará de nuevo.'
    try:
        data = await resp.json()
        code = data.get('code') if isinstance(data, dict) else None
        details = {
            50001: 'No hay acceso al canal. Revisa la pertenencia al servidor y el permiso de ver el canal.',
            50013: 'Faltan permisos. Revisa Ver canal, Enviar mensajes, Adjuntar archivos y el historial si se necesita comprobar entregas.',
            10003: 'El canal no existe. Corrige su ID en el panel.',
            10008: 'El mensaje ya no existe; no hace falta volver a borrarlo.',
            50009: 'El canal exige una verificación que la cuenta todavía no cumple. Revísala personalmente en Discord.',
            50007: 'No se puede enviar a este destinatario. Revisa si admite mensajes privados.',
            50035: 'El contenido tiene un formato inválido. Revisa el texto, su longitud y los adjuntos.',
            50045: 'El archivo es demasiado grande. Reduce el tamaño de la imagen.',
            50046: 'El archivo no es válido. Selecciona otra imagen.',
            50083: 'El hilo está archivado. Un administrador debe desarchivarlo o debes elegir otro destino.',
            200000: 'La moderación automática bloqueó el mensaje. Revisa el contenido con la administración; no se intentará eludir el filtro.',
            240000: 'Discord bloqueó un enlace potencialmente dañino. Revisa y corrige el enlace.',
            50014: 'La credencial no es válida. Actualízala en el panel.',
            60003: 'La operación requiere verificación de dos factores. Debes resolverla en Discord.',
            40002: 'La cuenta necesita verificación. Complétala personalmente en Discord.',
        }
        reason = details.get(code, reason)
        if isinstance(code, int):
            reason += f' Código de Discord: {code}.'
    except Exception:
        pass
    return reason


def _log(nivel: str, mensaje: str) -> None:
    nivel = {'INFO': 'INFORMACIÓN', 'DEBUG': 'DETALLE', 'WARN': 'ADVERTENCIA', 'OK': 'CORRECTO'}.get(nivel.strip(), nivel.strip())
    mensaje = str(mensaje)
    for secret in _log_secrets:
        if secret:
            mensaje = mensaje.replace(secret, '[credencial oculta]')
    mensaje = mensaje.replace('\r', '\\r').replace('\n', '\\n')
    ts   = datetime.now(_LOG_TZ).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{nivel:<5}] {mensaje}"
    print(line, flush=True)
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 2_097_152:
            old = LOG_PATH + ".1"
            if os.path.exists(old):
                os.remove(old)
            os.rename(LOG_PATH, old)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        print(f'[{ts}] [ADVERTENCIA] No se pudo escribir el archivo de registro; los mensajes continúan disponibles en esta consola.', flush=True)


def _sep(titulo: str = "") -> None:
    if titulo:
        _log("INFO", f"{'─'*20} {titulo} {'─'*20}")
    else:
        _log("INFO", "─" * 50)


# ─── Variables en mensajes ────────────────────────────────────────────────────

_DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _resolver_variables(texto: str, num_envio: int) -> str:
    ahora = datetime.now()
    texto = texto.replace("{fecha}",     ahora.strftime("%d/%m/%Y"))
    texto = texto.replace("{hora}",      ahora.strftime("%H:%M"))
    texto = texto.replace("{num_envio}", str(num_envio))
    texto = texto.replace("{dia}",       _DIAS_ES[ahora.weekday()])
    return texto


# ─── Silencio por horario ─────────────────────────────────────────────────────

def _en_silencio(ahora: datetime, desde: str, hasta: str) -> bool:
    try:
        h1, m1 = map(int, desde.split(":"))
        h2, m2 = map(int, hasta.split(":"))
    except Exception:
        return False
    minutos_ahora = ahora.hour * 60 + ahora.minute
    minutos_desde = h1 * 60 + m1
    minutos_hasta = h2 * 60 + m2
    if minutos_desde <= minutos_hasta:
        return minutos_desde <= minutos_ahora < minutos_hasta
    return minutos_ahora >= minutos_desde or minutos_ahora < minutos_hasta


# ─── Próximo envío (schedule) ─────────────────────────────────────────────────

def _segundos_hasta(hora_str: str, dias_activos: list) -> int:
    try:
        h, m = map(int, hora_str.split(":"))
    except Exception:
        return 3600
    python_dias = {(d + 6) % 7 for d in dias_activos}
    ahora  = datetime.now()
    target = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
    for offset in range(8):
        dia = target + timedelta(days=offset)
        if dia.weekday() in python_dias and dia > ahora:
            return int((dia - ahora).total_seconds())
    return 86400


# ─── Mapa channel → guild (al inicio) ────────────────────────────────────────

async def _obtener_guild_ids(session: aiohttp.ClientSession, token: str, channels: list) -> None:
    """Puebla _guild_map con guild_id de cada canal para construir Referers correctos."""
    global _guild_map
    for ch_id in channels:
        ch_id_str = str(ch_id)
        url = f"{API_BASE}/channels/{ch_id_str}"
        await _wait_global_limit()
        try:
            async with session.get(
                url,
                headers=_headers(token),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 401:
                    _stop_invalid_token()
                if resp.status == 429:
                    _record_limit(resp, await _response_data(resp))
                if resp.status == 200:
                    data = await resp.json()
                    guild_id = data.get("guild_id") or ""
                    _guild_map[ch_id_str] = guild_id
                    detail = _channel_details.setdefault(ch_id_str, {})
                    detail['guild_id'] = guild_id
                    if data.get('name'):
                        detail['name'] = data['name']
                    destino = f"servidor {guild_id}" if guild_id else "mensaje directo/grupo"
                    _log("INFO", f"[INICIO] {_channel_label(ch_id_str)} → {destino}")
                else:
                    _log("WARN", f"[INICIO] {_channel_label(ch_id_str)} → HTTP {resp.status} : {await _http_description(resp)} Se conservan los datos del paquete.")
        except StopDelivery:
            raise
        except Exception as exc:
            _log("WARN", f"[INICIO] {_channel_label(ch_id_str)} excepción: {_error_description(exc)}")
        await asyncio.sleep(random.uniform(0.3, 0.8))


# ─── Borrar mensaje anterior ──────────────────────────────────────────────────

async def _borrar_mensaje(session, token, channel_id, message_id):
    reason = _paused_reason(channel_id)
    if reason:
        _log('WARN', f'[BORRADO EN PAUSA] {_channel_label(channel_id)} | {reason}')
        return False
    for attempt in range(1, 4):
        await _wait_global_limit()
        try:
            async with session.delete(f'{API_BASE}/channels/{channel_id}/messages/{message_id}',
                                      headers=_headers(token, _referer(channel_id)),
                                      timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status in (204, 404):
                    _log('INFO', f'[BORRADO COMPLETADO] {_channel_label(channel_id)} | publicación anterior: {message_id} | HTTP {response.status}')
                    return True
                if response.status == 401:
                    _stop_invalid_token()
                if response.status == 429:
                    delay = _record_limit(response, await _response_data(response))
                    _pause_channel(channel_id, f'Discord pide esperar {delay:.1f} segundos antes de volver a borrar.')
                    _delivery_state['paused'][str(channel_id)]['until'] = time.time() + delay
                    _save_delivery_state()
                    return False
                detail = await _http_description(response)
                if 400 <= response.status < 500:
                    _pause_channel(channel_id, f'No se pudo borrar el mensaje anterior. HTTP {response.status}: {detail}')
                    return False
                _log('WARN', f'[BORRADO TEMPORALMENTE FALLIDO] {_channel_label(channel_id)} | HTTP {response.status}: {detail}')
        except StopDelivery:
            raise
        except (aiohttp.ClientError, OSError, ValueError) as exc:
            _log('WARN', f'[ERROR DE BORRADO] {_channel_label(channel_id)} | {_error_description(exc)}')
        if attempt < 3:
            await asyncio.sleep(5 * 2 ** (attempt - 1))
    _pause_channel(channel_id, 'No se pudo completar el borrado después de tres intentos. Se conserva la publicación nueva y se volverá a comprobar la limpieza.')
    return False


# ─── Persistencia del último mensaje por canal ────────────────────────────────
# Discloud puede reiniciar el proceso (AUTORESTART=true) entre ciclos; sin esto,
# "ultimo_msg" se perdía en memoria y el bot dejaba de borrar el mensaje anterior.

def _cargar_ultimo_msg() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except FileNotFoundError:
        pass
    except Exception as exc:
        _log("WARN", f"[ESTADO] No se pudo leer {STATE_PATH}: {_error_description(exc)}")
    return {}


def _guardar_ultimo_msg(data: dict) -> None:
    tmp_path = STATE_PATH + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, STATE_PATH)
        return True
    except Exception as exc:
        _log("WARN", f"[ESTADO] No se pudo guardar {STATE_PATH}: {_error_description(exc)}")
        return False


# ─── Leer canal antes de enviar ───────────────────────────────────────────────

async def _leer_canal(
    session: aiohttp.ClientSession, token: str, channel_id: str
) -> None:
    """GET /messages?limit=3 — simula que el usuario lee el canal antes de escribir."""
    url = f"{API_BASE}/channels/{channel_id}/messages?limit=3"
    ref = _referer(channel_id)
    await _wait_global_limit()
    try:
        async with session.get(
            url,
            headers=_headers(token, ref),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 401:
                _stop_invalid_token()
            if resp.status == 200:
                msgs = await resp.json()
                _log("DEBUG", f"[LECTURA] {_channel_label(channel_id)} → {len(msgs)} mensajes leídos")
            elif resp.status == 429:
                _record_limit(resp, await _response_data(resp))
                _log("DEBUG", f"[LECTURA] {_channel_label(channel_id)} con límite temporal al leer; se continúa")
                return
            else:
                _log("DEBUG", f"[LECTURA] {_channel_label(channel_id)} → HTTP {resp.status}: {await _http_description(resp)}")
    except StopDelivery:
        raise
    except Exception as exc:
        _log("DEBUG", f"[LECTURA] {_channel_label(channel_id)} excepción leyendo: {_error_description(exc)}")
    # Simula tiempo de lectura antes de ponerse a escribir
    await asyncio.sleep(random.uniform(0.8, 2.5))


# ─── Indicador "escribiendo..." ───────────────────────────────────────────────

async def _mostrar_escribiendo(
    session: aiohttp.ClientSession, token: str,
    channel_id: str, contenido: str, num_imagenes: int = 0,
) -> None:
    url = f"{API_BASE}/channels/{channel_id}/typing"
    ref = _referer(channel_id)

    # Texto: ~20 caracteres/seg, entre 2s y 15s.
    tiempo_texto = min(15.0, max(2.0, len(contenido) / 20)) if contenido else 0.0
    # Imágenes: ~3s por adjunto (seleccionar/subir), tope 10s.
    tiempo_imgs  = min(10.0, num_imagenes * 3.0)
    espera = max(2.0, tiempo_texto + tiempo_imgs)

    _log("DEBUG", f"[ESCRIBIENDO] {_channel_label(channel_id)} | duración: {espera:.1f} segundos")
    restante = espera
    while restante > 0:
        await _wait_global_limit()
        try:
            async with session.post(
                url,
                headers=_headers(token, ref),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 401:
                    _stop_invalid_token()
                if resp.status == 429:
                    _record_limit(resp, await _response_data(resp))
                    return
                if resp.status != 204:
                    body = await _http_description(resp)
                    _log("WARN", f"[ESCRIBIENDO] {_channel_label(channel_id)} → HTTP {resp.status}: {body}")
        except StopDelivery:
            raise
        except Exception as exc:
            _log("WARN", f"[ESCRIBIENDO] {_channel_label(channel_id)} excepción: {_error_description(exc)}")
            return
        # Discord expira el indicador ~10s; se retriggerea en tramos para sostenerlo.
        tramo = min(8.0, restante)
        await asyncio.sleep(tramo)
        restante -= tramo


# ─── Enviar mensaje a un canal via REST API ───────────────────────────────────

async def _enviar_canal(session, token, channel_id, contenido, rutas, previous_id=None):
    """Confirm each delivery, reuse its nonce and retain ambiguous results."""
    channel_id = str(channel_id)
    reason = _paused_reason(channel_id)
    if reason:
        _log('WARN', f'[CANAL EN PAUSA] {_channel_label(channel_id)} | {reason}')
        return None, None
    pending = _delivery_state['pending'].get(channel_id)
    if pending:
        recovered = await _find_pending_message(session, token, channel_id, pending)
        if recovered:
            return _confirm_pending(channel_id, recovered)
        _log('ERROR', f'[ENTREGA SIN CONFIRMAR] {_channel_label(channel_id)} | no se pudo determinar si la publicación anterior llegó. Se conserva el mensaje previo y no se reenviará a ciegas. Comprueba el canal y estado_entregas.json antes de reanudar.')
        return None, None

    await _wait_global_limit()
    await _leer_canal(session, token, channel_id)
    await _wait_global_limit()
    await _mostrar_escribiendo(session, token, channel_id, contenido, num_imagenes=len(rutas))
    pending = dict(nonce=_gen_nonce(), created=time.time(), previous=previous_id, uncertain=False)
    _delivery_state['pending'][channel_id] = pending
    _save_delivery_state()
    url = f'{API_BASE}/channels/{channel_id}/messages'
    headers = _headers(token, _referer(channel_id))
    for attempt in range(1, 4):
        if attempt > 1 and time.time() - pending['created'] > 90:
            break
        await _wait_global_limit()
        # Recheck after a possible long global cooldown, before issuing a POST.
        if attempt > 1 and time.time() - pending['created'] > 90:
            break
        _log('INFO', f'[ENVIANDO] {_channel_label(channel_id)} | intento {attempt}/3 | identificador de entrega: {pending["nonce"]}')
        try:
            payload = dict(nonce=pending['nonce'], enforce_nonce=True, tts=False, flags=0)
            if contenido:
                payload['content'] = contenido
            options = dict(headers=headers, timeout=aiohttp.ClientTimeout(total=30))
            if rutas:
                form = aiohttp.FormData()
                form.add_field('payload_json', json.dumps(payload), content_type='application/json')
                for index, path in enumerate(rutas):
                    with open(path, 'rb') as image:
                        data = image.read()
                    form.add_field(f'files[{index}]', data, filename=os.path.basename(path), content_type='application/octet-stream')
                    _log('DEBUG', f'[IMAGEN] {_channel_label(channel_id)} | {os.path.basename(path)} | {len(data)} bytes')
                options['data'] = form
            else:
                options['json'] = payload
            async with session.post(url, **options) as response:
                _log('DEBUG', f'[RESPUESTA] {_channel_label(channel_id)} | HTTP {response.status} | intento {attempt}/3')
                if response.status == 401:
                    _stop_invalid_token()
                if response.status == 429:
                    delay = _record_limit(response, await _response_data(response))
                    if not pending['uncertain']:
                        _delivery_state['pending'].pop(channel_id, None)
                        _save_delivery_state()
                    _log('WARN', f'[LÍMITE TEMPORAL] {_channel_label(channel_id)} | Discord pide esperar {delay:.1f} segundos. No se adelantarán solicitudes.')
                    return None, delay
                if response.status in (200, 201):
                    data = await _response_data(response)
                    if str(data.get('id', '')).isdigit():
                        return _confirm_pending(channel_id, data['id'])
                    _log('WARN', f'[RESPUESTA INCOMPLETA] {_channel_label(channel_id)} | Discord respondió éxito sin un ID válido. Se comprobará la entrega.')
                elif 400 <= response.status < 500:
                    data = await _response_data(response)
                    detail = await _http_description(response)
                    if data.get('code') == 50014:
                        _stop_invalid_token()
                    if not pending['uncertain']:
                        _delivery_state['pending'].pop(channel_id, None)
                    permanent = (response.status in (400, 413, 422) and data.get('code') not in (50083, 50009, 40002, 60003)) or data.get('code') in (200000, 240000, 50035, 50045, 50046)
                    _pause_channel(channel_id, f'HTTP {response.status}: {detail}', permanent=permanent)
                    return None, None
                else:
                    _log('WARN', f'[ERROR TEMPORAL] {_channel_label(channel_id)} | HTTP {response.status}: {await _http_description(response)}')
        except StopDelivery:
            raise
        except (FileNotFoundError, PermissionError) as exc:
            if not pending['uncertain']:
                _delivery_state['pending'].pop(channel_id, None)
            _pause_channel(channel_id, _error_description(exc), permanent=True)
            return None, None
        except (aiohttp.ClientError, OSError, ValueError) as exc:
            _log('WARN', f'[FALLO DE ENVÍO] {_channel_label(channel_id)} | {_error_description(exc)}')
        pending['uncertain'] = True
        _save_delivery_state()
        recovered = await _find_pending_message(session, token, channel_id, pending)
        if recovered:
            return _confirm_pending(channel_id, recovered)
        if attempt < 3:
            delay = 5 * (2 ** (attempt - 1))
            _log('INFO', f'[REINTENTO SEGURO] {_channel_label(channel_id)} | espera: {delay} segundos. Se conservará el mismo identificador para evitar otra copia.')
            await asyncio.sleep(delay)
    _log('ERROR', f'[REQUIERE REVISIÓN] {_channel_label(channel_id)} | se agotaron los intentos sin confirmar la entrega. Se conserva el estado pendiente y el mensaje anterior; los siguientes ciclos sólo comprobarán si llegó.')
    return None, None


def configuration_adapter(config):
    return config


# ─── Loop principal ───────────────────────────────────────────────────────────

async def main():
    config_path = os.path.join(BASE, "config.json")
    _log("INFO", f"Cargando configuración desde: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        config = configuration_adapter(json.load(f))

    global _channel_details, _log_secrets
    _channel_details = {str(channel): dict(entry) for channel, entry in config.get('channel_content', {}).items()}
    _guild_map.clear()
    _log_secrets = [config.get('token', ''), os.environ.get('DISCORD_TOKEN', '')]
    token          = config.get("token", "")
    channels       = config.get("channels", [])
    intervalo      = int(config.get("intervalo", 3600))
    mensaje_base   = config.get("mensaje", "") or ""
    sched_type     = config.get("schedule_type", "interval")
    dias_activos   = config.get("dias", list(range(7)))
    hora_envio     = config.get("hora", "09:00")
    mensajes_alt   = config.get("mensajes", [])
    modo_mensajes  = config.get("modo_mensajes", "aleatorio")
    modo_imagenes  = config.get("modo_imagenes", "todas")
    silencio_desde = config.get("silencio_desde", "")
    silencio_hasta = config.get("silencio_hasta", "")
    borrar_anterior = config.get("borrar_anterior", False)

    # ── Validaciones básicas ─────────────────────────────────────────────────
    if not token:
        _log("ERROR", "Credencial no encontrada en config.json — deteniendo bot"); return
    if not channels:
        _log("ERROR", "Sin canales configurados en config.json — deteniendo bot"); return
    if not config.get("activo", True):
        _log("WARN", "Bot desactivado (desactivado en la configuración) — deteniendo bot"); return

    # ── Imágenes ─────────────────────────────────────────────────────────────
    imagenes = config.get("imagenes", [])
    if not imagenes and config.get("imagen"):
        imagenes = [config["imagen"]]

    rutas = []
    for nombre in imagenes:
        if not nombre:
            continue
        ruta = os.path.join(BASE, nombre)
        if os.path.isfile(ruta):
            rutas.append(ruta)
            _log("INFO", f"Imagen encontrada: {nombre} ({os.path.getsize(ruta)} bytes)")
        else:
            _log("WARN", f"Imagen NO encontrada: {nombre} (ruta: {ruta})")

    # ── Resumen de inicio ────────────────────────────────────────────────────
    _sep("INICIO")
    _log("INFO", f"Dirección de Discord: {API_BASE}")
    _log("INFO", "Credencial     : [oculto]")
    _log("INFO", f"Canales configurados: {len(channels)}")
    _log("INFO", f"Intervalo      : {intervalo}s ({intervalo//60}min)")
    _log("INFO", f"Programación   : {'intervalo' if sched_type == 'interval' else 'hora fija'}" + (f" | hora={hora_envio} dias={dias_activos}" if sched_type == "schedule" else ""))
    if not config.get('channel_content'):
        _log("INFO", f"Imágenes: {len(rutas)} | modo: { {'carousel': 'rotación', 'aleatoria': 'aleatoria', 'todas': 'todas'}.get(modo_imagenes, 'predeterminado') }")
        _log("INFO", f"Texto base: {mensaje_base!r}")
        _log("INFO", f"Mensajes alternativos: {len(mensajes_alt)} | modo: {'secuencial' if modo_mensajes == 'secuencial' else 'aleatorio'}")
    else:
        _log('INFO', f"Mensajes independientes: {len({entry.get('number') for entry in _channel_details.values()})}")
    _log("INFO", f"Borrar anterior: {'sí' if borrar_anterior else 'no'}")
    for channel in channels:
        entry = _channel_details.get(str(channel), {})
        _log('INFO', f"Destino configurado: {_channel_label(channel)} | texto: {len(entry.get('message', mensaje_base))} caracteres | imagen: {os.path.basename(entry.get('image', '')) or 'sin imagen'}")
    _log("INFO", f"Silencio       : {silencio_desde}→{silencio_hasta}" if silencio_desde else "Silencio       : desactivado")
    _sep()

    num_envio    = 0
    carousel_idx = 0
    msg_seq_idx  = 0
    same_account = _load_delivery_state(config)
    ultimo_msg: dict = _cargar_ultimo_msg() if same_account else {}
    if not same_account:
        if _guardar_ultimo_msg({}) is False:
            raise StopDelivery('No se pudo reiniciar el estado para la cuenta nueva. Revisa los permisos del almacenamiento.')
        _save_delivery_state()
    rl_hasta:   dict = {}  # channel_id → unix timestamp cuando expira RL
    if ultimo_msg:
        _log("INFO", f"[ESTADO] {len(ultimo_msg)} mensaje(s) previo(s) recuperado(s) de {STATE_PATH}")

    async with aiohttp.ClientSession() as session:

        # Obtener guild_id de cada canal para Referers precisos
        _log("INFO", "Consultando nombres e identificadores de los canales...")
        await _obtener_guild_ids(session, token, channels)
        _sep()

        # ── Helper interno ───────────────────────────────────────────────────

        async def _enviar_a_canal(ch_id_str: str, contenido: str, rutas_envio: list, ciclo: int) -> str:
            """Envía a un canal. Retorna 'ok', 'rl', 'error'."""
            entry = config.get('channel_content', {}).get(ch_id_str)
            if entry is not None:
                contenido = _resolver_variables(entry['message'], ciclo)
                rutas_envio = [os.path.join(BASE, entry['image'])] if entry.get('image') else []
            destino = _channel_label(ch_id_str)
            _log('INFO', f"[PREPARANDO ENVÍO] {destino} | ronda #{ciclo} | texto: {len(contenido)} caracteres | imágenes: {[os.path.basename(path) for path in rutas_envio] or 'sin imagen'}")
            _log('DEBUG', f'Texto de este envío: {contenido!r}')
            # Pausa de "reconocimiento" — simula que el usuario ve el chat antes de actuar
            pausa_previa = random.uniform(1.0, 3.5)
            await asyncio.sleep(pausa_previa)

            cleanup = _delivery_state['cleanup'].get(ch_id_str)
            if cleanup:
                _log('WARN', f'[LIMPIEZA PENDIENTE] {destino} | se intentará retirar la publicación anterior antes de crear otra.')
                if not await _borrar_mensaje(session, token, ch_id_str, cleanup):
                    return 'error'
                _delivery_state['cleanup'].pop(ch_id_str, None)
                _save_delivery_state()
            previous = ultimo_msg.get(ch_id_str)
            msg_id, retry_after = await _enviar_canal(session, token, ch_id_str, contenido, rutas_envio, previous_id=previous)

            if msg_id:
                pending = _delivery_state['pending'].get(ch_id_str, {})
                previous = pending.get('previous') or previous
                ultimo_msg[ch_id_str] = msg_id
                # Save the cleanup obligation before retiring the pending delivery.
                if borrar_anterior and previous and previous != msg_id:
                    _delivery_state['cleanup'][ch_id_str] = previous
                _save_delivery_state()
                if _guardar_ultimo_msg(ultimo_msg) is False:
                    raise StopDelivery('No se pudo guardar el ID confirmado. Se conserva el mensaje anterior; revisa el almacenamiento antes de reiniciar.')
                _delivery_state['pending'].pop(ch_id_str, None)
                _save_delivery_state()
                rl_hasta.pop(ch_id_str, None)
                _log('OK', f'[ENVÍO CONFIRMADO] {destino} | publicación: {msg_id} | ronda #{ciclo}')
                if borrar_anterior and previous and previous != msg_id:
                    _log('INFO', f'[BORRADO SEGURO] {destino} | nuevo mensaje confirmado. Se retirará el anterior: {previous}')
                    if await _borrar_mensaje(session, token, ch_id_str, previous):
                        _delivery_state['cleanup'].pop(ch_id_str, None)
                        _save_delivery_state()
                    else:
                        _log('ERROR', f'[LIMPIEZA PENDIENTE] {destino} | el nuevo mensaje está publicado, pero no se pudo borrar el anterior. No se crearán más publicaciones hasta completar esta limpieza.')
                return 'ok'
            elif retry_after is not None:
                expira = time.time() + retry_after
                rl_hasta[ch_id_str] = expira
                expira_str = _log_clock(expira)
                _log("WARN", f"[LÍMITE] {_channel_label(ch_id_str)} con límite temporal {retry_after:.0f}s → se intenta de nuevo a las {expira_str}")
                return "rl"
            else:
                _log("ERROR", f"{_channel_label(ch_id_str)} ✗ envío no confirmado o canal en pausa; revisa el diagnóstico anterior | ciclo #{ciclo}")
                return "error"

        # ── Loop ─────────────────────────────────────────────────────────────

        while True:
            try:
                ahora = datetime.now()

                # Modo silencio
                if silencio_desde and silencio_hasta and _en_silencio(ahora, silencio_desde, silencio_hasta):
                    _log("INFO", f"Modo silencioso activo ({silencio_desde}–{silencio_hasta}), esperando 60s...")
                    await asyncio.sleep(60)
                    continue

                # Modo schedule (hora fija)
                if sched_type == "schedule":
                    espera = _segundos_hasta(hora_envio, dias_activos)
                    if espera > 0:
                        proxima = datetime.fromtimestamp(ahora.timestamp() + espera, _LOG_TZ).strftime("%Y-%m-%d %H:%M:%S")
                        _log("INFO", f"Próximo envío a las {hora_envio} — en {espera}s ({proxima})")
                        await asyncio.sleep(espera)
                    python_dias = {(d + 6) % 7 for d in dias_activos}
                    if datetime.now().weekday() not in python_dias:
                        await asyncio.sleep(60)
                        continue

                # ── Estado de rate limits ────────────────────────────────────
                ahora_ts = time.time()
                canales_en_rl = [(cid, t) for cid, t in rl_hasta.items() if ahora_ts < t]
                if canales_en_rl:
                    _log("INFO", f"Límites temporales: {len(canales_en_rl)} canal(es) en espera:")
                    for cid, t in canales_en_rl:
                        _log("INFO", f"  └─ {_channel_label(cid)} libre a las {_log_clock(t)} (hora de Costa Rica; en {t-ahora_ts:.0f}s)")

                # ── Preparar contenido del ciclo ─────────────────────────────
                if not rutas:
                    rutas_envio = []
                elif modo_imagenes == "carousel":
                    rutas_envio = [rutas[carousel_idx % len(rutas)]]
                    carousel_idx += 1
                elif modo_imagenes == "aleatoria":
                    rutas_envio = [random.choice(rutas)]
                else:
                    rutas_envio = list(rutas)

                num_envio += 1
                if mensajes_alt:
                    if modo_mensajes == "secuencial":
                        msg_raw = mensajes_alt[msg_seq_idx % len(mensajes_alt)]
                        msg_seq_idx += 1
                    else:
                        msg_raw = random.choice(mensajes_alt)
                else:
                    msg_raw = mensaje_base
                contenido = _resolver_variables(msg_raw, num_envio) if msg_raw else ""

                # ── Validar que hay algo que enviar ──────────────────────────
                if not contenido and not rutas_envio:
                    _log("WARN", "Nada que enviar: mensaje vacío y sin imágenes. Revisa config.json.")
                    await asyncio.sleep(intervalo if sched_type == "interval" else 60)
                    continue

                # ── Orden de canales del ciclo (rotado) ──────────────────────
                rot = (num_envio - 1) % len(channels)
                channels_ciclo = channels[rot:] + channels[:rot]

                # ── Cabecera del ciclo ────────────────────────────────────────
                _sep(f"CICLO #{num_envio}")
                _log("INFO", f"Canales totales : {len(channels)}")
                _log("INFO", "Orden de canales: " + " → ".join(_channel_label(channel) for channel in channels_ciclo))
                if not config.get('channel_content'):
                    _log("INFO", f"Imágenes de la ronda: {[os.path.basename(r) for r in rutas_envio]}")
                    _log("INFO", f"Texto: {contenido!r}")

                # ── Primera pasada: canales disponibles ───────────────────────
                en_espera: list = []
                stats = {"ok": 0, "rl": 0, "error": 0}

                for ch_id in channels_ciclo:
                    ch_id_str = str(ch_id)
                    ahora_ts  = time.time()
                    if ch_id_str in rl_hasta and ahora_ts < rl_hasta[ch_id_str]:
                        secs_left = rl_hasta[ch_id_str] - ahora_ts
                        _log("INFO", f"[POSPUESTO] {_channel_label(ch_id_str)} todavía con límite temporal ({secs_left:.0f}s) → segunda pasada")
                        en_espera.append(ch_id_str)
                        continue

                    resultado = await _enviar_a_canal(ch_id_str, contenido, rutas_envio, num_envio)
                    stats[resultado] += 1
                    if resultado == "rl":
                        en_espera.append(ch_id_str)
                    pausa_canal = random.uniform(12, 20)
                    _log("INFO", f"[ESPERA] Esperando {pausa_canal:.1f}s antes del próximo canal...")
                    await asyncio.sleep(pausa_canal)

                # ── Segunda pasada: canales con RL que ya expiró ──────────────
                if en_espera:
                    _log("INFO", f"Segunda pasada: {len(en_espera)} canal(es) con límite temporal pendiente")
                    for ch_id_str in en_espera:
                        espera_rl = max(0.0, rl_hasta.get(ch_id_str, 0) - time.time())
                        if espera_rl > intervalo:
                            _log("WARN", f"[POSPUESTO] {_channel_label(ch_id_str)} límite temporal demasiado largo ({espera_rl:.0f}s > {intervalo}s) → próximo ciclo")
                            stats["rl"] += 1
                            continue
                        if espera_rl > 0:
                            _log("INFO", f"[ESPERA] {_channel_label(ch_id_str)}: esperando {espera_rl:.0f}s antes de reintentar...")
                            await asyncio.sleep(espera_rl)
                        resultado = await _enviar_a_canal(ch_id_str, contenido, rutas_envio, num_envio)
                        stats[resultado] += 1
                        pausa_canal = random.uniform(12, 20)
                        _log("INFO", f"[ESPERA] Esperando {pausa_canal:.1f}s antes del próximo canal...")
                        await asyncio.sleep(pausa_canal)

                # ── Resumen del ciclo ─────────────────────────────────────────
                _sep(f"FIN CICLO #{num_envio}")
                _log("INFO", f"Resultado de la ronda: {stats['ok']} envíos correctos | {stats['rl']} respuestas con límite temporal | {stats['error']} errores | destinos={len(channels)}")
                if stats["rl"] > 0:
                    pendientes = [(cid, rl_hasta[cid]) for cid in rl_hasta if cid in [str(c) for c in channels]]
                    for cid, t in pendientes:
                        _log("WARN", f"  └─ {_channel_label(cid)} sigue con límite temporal hasta {_log_clock(t)} (hora de Costa Rica)")

                if sched_type == "interval":
                    jitter = random.uniform(-0.15, 0.15)
                    espera_ciclo = int(intervalo * (1 + jitter))
                    prox = datetime.now(_LOG_TZ) + timedelta(seconds=espera_ciclo)
                    _log("INFO", f"Esperando {espera_ciclo}s (variación {jitter:+.0%}) | próximo ciclo a las {prox.strftime('%H:%M:%S')}")
                    await asyncio.sleep(espera_ciclo)
                else:
                    await asyncio.sleep(60)

            except StopDelivery:
                raise
            except Exception as exc:
                _log("ERROR", f"[RONDA] Excepción no capturada en el ciclo, se continúa en 10s: {_error_description(exc)}")
                await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())

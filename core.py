"""Validación, almacenamiento local y exportación. Sin llamadas al importar."""
import base64
import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile

API = 'https://discord.com/api/v10'
MAX_IMAGE = 10 * 1024 * 1024


def normalize_token(value):
    token = str(value or '').strip()
    pairs = {'"': '"', "'": "'", '“': '”', '‘': '’'}
    while len(token) >= 2 and pairs.get(token[0]) == token[-1]:
        token = token[1:-1].strip()
    return token


def valid_token(token):
    return bool(token) and not any(c.isspace() or c in '\"\'“”‘’' for c in token)


class APIError(Exception):
    def __init__(self, status, data):
        self.status, self.data = status, data
        messages = {401: 'Discord rechazó la credencial. Revisa la cuenta y el tipo elegido.',
                    403: 'La cuenta no tiene acceso o permiso para enviar en ese canal.',
                    404: 'El canal no existe o no es accesible.',
                    429: 'Discord pide esperar antes de volver a intentar.'}
        super().__init__(messages.get(status, f'Discord respondió HTTP {status}.'))


def validate(config, require_content=True):
    c = dict(config)
    c['token'] = normalize_token(c.get('token', ''))
    if not valid_token(c['token']):
        raise ValueError('Introduce un token válido, sin espacios ni comillas sueltas.')
    if c.get('account_type') not in ('personal', 'bot'):
        raise ValueError('Elige el tipo de cuenta.')
    channels = list(dict.fromkeys(c.get('channels', [])))
    if not channels or any(not re.fullmatch(r'\d{15,22}', x) for x in channels):
        raise ValueError('Agrega al menos un canal con un ID válido.')
    c['channels'] = channels
    try:
        minutes = float(c.get('minutes', 0))
    except (ValueError, TypeError):
        raise ValueError('El intervalo debe ser un número de minutos.') from None
    if not math.isfinite(minutes) or not 1 <= minutes <= 10080:
        raise ValueError('El intervalo debe estar entre 1 y 10080 minutos.')
    c['minutes'] = minutes
    c['message'] = str(c.get('message', ''))
    if len(c['message']) > 2000:
        raise ValueError('El mensaje supera los 2000 caracteres.')
    image = str(c.get('image', ''))
    if image:
        p = Path(image)
        if not p.is_file():
            raise ValueError('No se encuentra la imagen. Vuelve a seleccionarla.')
        if p.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
            raise ValueError('Elige una imagen PNG, JPG, GIF o WEBP.')
        if p.stat().st_size > MAX_IMAGE:
            raise ValueError('Esta versión admite imágenes de hasta 10 MB.')
    if require_content and not c['message'].strip() and not image:
        raise ValueError('Escribe un mensaje o selecciona una imagen.')
    # Comportamiento fijo, incluido para configuraciones de versiones anteriores.
    for key in ('read_before', 'typing_before', 'variable_pauses', 'delete_previous'):
        c[key] = True
    return c


def resolve_channel(token, account_type, channel_id):
    channel_id = str(channel_id).strip()
    token = normalize_token(token)
    if not valid_token(token):
        raise ValueError('Introduce primero el token de la cuenta.')
    if not re.fullmatch(r'\d{15,22}', channel_id):
        raise ValueError('Pega un ID de canal válido, solo números.')
    channel = request(token, account_type, f'/channels/{channel_id}')
    kind = channel.get('type')
    if kind not in (0, 1, 3, 5, 10, 11, 12):
        raise ValueError('Ese ID corresponde a una categoría o a un canal que esta versión no admite.')
    guild_id = str(channel.get('guild_id') or '')
    if guild_id:
        try:
            guild = request(token, account_type, f'/guilds/{guild_id}')
            group = guild.get('name') or f'Servidor {guild_id}'
        except APIError as exc:
            if exc.status not in (403, 404):
                raise
            group = f'Servidor {guild_id} (nombre no accesible)'
    else:
        group = 'Grupo privado' if kind == 3 else 'Mensaje directo'
    name = channel.get('name')
    if not name:
        name = ', '.join(str(u.get('global_name') or u.get('username') or 'Usuario') for u in channel.get('recipients', []))
    return {'id': channel_id, 'name': name or channel_id, 'group': group, 'guild_id': guild_id}


def request(token, account_type, path, message=None, image='', method=None):
    token = normalize_token(token)
    if not valid_token(token):
        raise ValueError('Introduce un token válido, sin espacios ni comillas sueltas.')
    auth = f'Bot {token}' if account_type == 'bot' else token
    headers = {'Authorization': auth, 'User-Agent': 'SelfBotSimple/1.0'}
    body = None
    if message is not None:
        payload = {'content': message, 'allowed_mentions': {'parse': []}}
        if image:
            boundary = 'simple-' + uuid.uuid4().hex
            payload['attachments'] = [{'id': 0, 'filename': 'imagen' + Path(image).suffix.lower()}]
            parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\nContent-Type: application/json\r\n\r\n'.encode(),
                     json.dumps(payload).encode(), b'\r\n',
                     f'--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; filename="{payload["attachments"][0]["filename"]}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
                     Path(image).read_bytes(), f'\r\n--{boundary}--\r\n'.encode()]
            body = b''.join(parts)
            headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
        else:
            body = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(API + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read())
        except (ValueError, OSError):
            data = {}
        raise APIError(exc.code, data) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError('No se pudo confirmar la respuesta de Discord. Revisa la conexión; el envío podría haberse completado.') from None


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect(value, decrypt=False):
    raw = base64.b64decode(value, validate=True) if decrypt else value.encode('utf-8')
    buffer = ctypes.create_string_buffer(raw)
    src = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    dst = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst)):
        raise RuntimeError('Windows no pudo proteger o recuperar la credencial. Vuelve a introducirla.')
    try:
        result = ctypes.string_at(dst.data, dst.size)
        return result.decode('utf-8') if decrypt else base64.b64encode(result).decode('ascii')
    finally:
        kernel.LocalFree(ctypes.cast(dst.data, ctypes.c_void_p))


def save_config(path, config):
    data = dict(config)
    token = normalize_token(data.get('token', ''))
    data['token'] = protect(token) if token else ''
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
            temp = f.name
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def load_config(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    data['token'] = normalize_token(protect(data['token'], decrypt=True)) if data.get('token') else ''
    return data


def export_zip(path, config, base, language='Español'):
    c = validate(config)
    c['language'] = 'English' if language == 'English' else 'Español'
    c['runtime_target'] = 'discloud'
    english = c['language'] == 'English'
    image = c.get('image', '')
    c['image'] = 'imagen' + Path(image).suffix.lower() if image else ''
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.zip', delete=False) as f:
            temporary = f.name
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
            for name in ('bot.py', 'core.py', 'i18n.py'):
                z.write(Path(base) / name, name)
            z.writestr('config.json', json.dumps(c, ensure_ascii=False, indent=2))
            z.writestr('requirements.txt', '# Python standard library only\n' if english else '# Solo biblioteca estándar de Python\n')
            z.writestr('README.txt' if english else 'LEEME.txt', (
                'SELF BOT DISCORD - Discloud\nUpload this ZIP to Discloud. The first round starts immediately.\nTo stop: use Stop in the Discloud dashboard.\nThis package contains your credential. Do not share it.\n' if english else
                'SELF BOT DISCORD - Discloud\nSube este ZIP a Discloud. La primera ronda empieza inmediatamente.\nPara detener: usa Detener en el panel de Discloud.\nEste paquete contiene la credencial. No lo compartas.\n'))
            z.writestr('discloud.config', 'NAME=SELF BOT DISCORD\nTYPE=bot\nMAIN=bot.py\nRAM=100\nVERSION=latest\n')
            if image:
                z.write(image, c['image'])
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return str(path)

def export_local_zip(path, config, base, language='Español'):
    """Paquete Windows autónomo: BAT, ejecutable, configuración e imagen."""
    c = validate(config)
    c['language'] = 'English' if language == 'English' else 'Español'
    c['runtime_target'] = 'local'
    image = c.get('image', '')
    c['image'] = 'imagen' + Path(image).suffix.lower() if image else ''
    runner = Path(base) / 'local-runner.exe'
    if not runner.is_file():
        raise ValueError('No se encuentra el ejecutable local. Vuelve a descargar la versión completa del panel.')
    english = language == 'English'
    instruction = 'TO STOP: press Ctrl+C or close this window.' if english else 'PARA DETENER: pulsa Ctrl+C o cierra esta ventana.'
    stopped = 'Process stopped. Review the logs above.' if english else 'Proceso detenido. Revisa los logs de arriba.'
    launcher = '\r\n'.join([
        '@echo off', 'setlocal', 'chcp 65001 >nul', 'title SELF BOT DISCORD - Logs',
        'pushd "%~dp0"', 'if errorlevel 1 exit /b 1',
        'echo SELF BOT DISCORD - LOCAL', 'echo ' + instruction, 'echo.',
        '"%~dp0local-runner.exe" --language=' + ('English' if english else 'Spanish'), 'set "run_exit=%errorlevel%"', 'echo.',
        'echo ' + stopped, 'echo ' + ('Press any key to close this window.' if english else 'Pulsa cualquier tecla para cerrar esta ventana.'), 'pause >nul', 'popd', 'exit /b %run_exit%', ''])
    instructions = (
        'SELF BOT DISCORD - Local Windows package\n\n'
        '1. Extract the entire ZIP into a folder. Do not run it from inside the ZIP.\n'
        '2. Double-click start.bat. Python installation is not required.\n'
        '3. CMD shows live logs with timestamps. The first round starts immediately.\n'
        '4. Press Ctrl+C or close CMD to stop. The computer must stay on and connected.\n\n'
        'Keep config.json and the image beside local-runner.exe.\n'
        'This package contains your account credential. Do not share it.\n'
        'To change settings, create and extract a new package from the panel.\n'
        'Do not run multiple copies or both Discloud and the local package simultaneously.\n'
        'Logs appear in CMD; they are not saved to a log file.\n'
        if english else
        'SELF BOT DISCORD - Paquete local para Windows\n\n'
        '1. Extrae TODO el ZIP en una carpeta. No lo ejecutes dentro del ZIP.\n'
        '2. Abre iniciar.bat con doble clic. No requiere instalar Python.\n'
        '3. CMD muestra los logs en vivo con fecha y hora. La primera ronda empieza inmediatamente.\n'
        '4. Pulsa Ctrl+C o cierra CMD para detener. La computadora debe seguir encendida y conectada.\n\n'
        'Conserva config.json y la imagen junto a local-runner.exe.\n'
        'Este paquete contiene la credencial de tu cuenta. No lo compartas.\n'
        'Para cambiar los datos, genera y extrae un paquete nuevo desde el panel.\n'
        'No ejecutes varias copias ni Discloud y el paquete local a la vez.\n'
        'Los logs aparecen en CMD; no se guardan en un archivo de registro.\n')
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.zip', delete=False) as f:
            temporary = f.name
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(runner, 'local-runner.exe')
            z.writestr('config.json', json.dumps(c, ensure_ascii=False, indent=2))
            z.writestr('start.bat' if english else 'iniciar.bat', launcher.encode('utf-8'))
            z.writestr('README.txt' if english else 'LEEME.txt', instructions.encode('utf-8'))
            if image:
                z.write(image, c['image'])
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return str(path)

def desktop_directory():
    """Obtiene el Escritorio real de Windows, incluso si está en OneDrive."""
    buffer = ctypes.create_unicode_buffer(32768)
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    fn = shell.SHGetFolderPathW
    fn.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR]
    fn.restype = ctypes.c_long
    if fn(None, 0x10, None, 0, buffer) != 0 or not buffer.value:
        raise ValueError('No se pudo localizar el Escritorio de Windows.')
    return Path(buffer.value)


def export_local_desktop(config, base, language='Español', desktop=None):
    desktop = Path(desktop) if desktop is not None else desktop_directory()
    if not desktop.is_dir():
        raise ValueError('No se pudo localizar el Escritorio de Windows.')
    # Cada exportación conserva los archivos y el estado de las anteriores.
    folder_name = 'SELF BOT DISCORD Local ' + uuid.uuid4().hex[:10]
    package = desktop / folder_name
    package.mkdir()
    completed = False
    try:
        archive = package / 'paquete.zip'
        export_local_zip(archive, config, base, language)
        with zipfile.ZipFile(archive) as z:
            z.extractall(package)
        archive.unlink()
        start_name = 'start.bat' if language == 'English' else 'iniciar.bat'
        launcher = '\r\n'.join(['@echo off', 'setlocal',
            'call "%~dp0' + folder_name + '\\' + start_name + '"', 'exit /b %errorlevel%', ''])
        # No reemplazar archivos del usuario ni lanzadores anteriores.
        for number in range(1, 10001):
            name = 'SELF BOT DISCORD' + (f' ({number})' if number > 1 else '') + '.bat'
            bat = desktop / name
            try:
                with bat.open('x', encoding='utf-8', newline='') as f:
                    f.write(launcher)
                completed = True
                return str(bat)
            except FileExistsError:
                continue
        raise ValueError('Hay demasiados lanzadores en el Escritorio. Elimina uno que ya no uses e inténtalo de nuevo.')
    finally:
        if not completed:
            # Sólo archivos planos creados en nuestra carpeta única de esta exportación.
            for item in package.iterdir():
                if item.is_file():
                    item.unlink()
            package.rmdir()

MAX_CONFIG = 1024 * 1024


def _read_package_config(raw):
    try:
        if len(raw) > MAX_CONFIG:
            raise ValueError()
        c = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(c, dict) or c.get('account_type') != 'personal':
            raise ValueError()
        if not isinstance(c.get('channels'), list) or not all(isinstance(x, str) for x in c['channels']):
            raise ValueError()
        if not isinstance(c.get('token'), str) or not isinstance(c.get('message', ''), str):
            raise ValueError()
        original_image = c.get('image', '')
        if not isinstance(original_image, str):
            raise ValueError()
        clean = validate(dict(c, image=''), require_content=False)
        clean['image'] = original_image
        # Only keep fields the panel understands.
        rows = c.get('channel_metadata', [])
        if not isinstance(rows, list):
            rows = []
        metadata = {}
        for row in rows:
            if isinstance(row, dict) and row.get('id') in clean['channels']:
                metadata[row['id']] = {key: str(row.get(key, ''))[:300] for key in ('id', 'name', 'group', 'guild_id')}
        clean['channel_metadata'] = [metadata.get(channel, dict(id=channel, name='Sin comprobar', group='—', guild_id='')) for channel in clean['channels']]
        clean['language'] = 'English' if c.get('language') == 'English' else 'Español'
        return clean
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ValueError('El archivo no contiene una configuración compatible de este programa.') from None


def _relative_package_path(name):
    from pathlib import PurePosixPath
    if not name or '\\' in name or ':' in name or '\x00' in name:
        raise ValueError('El paquete contiene una ruta de archivo no válida.')
    relative = PurePosixPath(name)
    if relative.is_absolute() or any(part in ('..', '.') for part in relative.parts):
        raise ValueError('El paquete contiene una ruta de archivo no válida.')
    return relative


def bat_package_directory(path):
    """Reconoce nuestros lanzadores sin ejecutar ni interpretar comandos."""
    current = Path(path).resolve()
    visited = set()
    for _ in range(8):
        if current in visited or current.suffix.lower() != '.bat':
            break
        visited.add(current)
        if current.stat().st_size > 16384:
            break
        text = current.read_text(encoding='utf-8-sig')
        runner = re.search(r'^"%~dp0local-runner\.exe"(?: --language=(?:English|Spanish))?\s*$', text, re.MULTILINE)
        if runner and (current.parent / 'config.json').is_file():
            return current.parent
        link = re.search(r'^call "%~dp0([^"\r\n]+\.bat)"\s*$', text, re.MULTILINE | re.IGNORECASE)
        if not link:
            break
        name = link.group(1).replace('\\', '/')
        relative = _relative_package_path(name)
        target = (current.parent / str(relative)).resolve()
        if not target.is_relative_to(current.parent):
            break
        current = target
    raise ValueError('Este BAT no tiene una configuración compatible. Selecciona un BAT generado por este programa.')


def import_package(path, cache):
    """Lee sólo JSON e imagen; nunca ejecuta ni extrae código del paquete."""
    path = Path(path).resolve()
    image_bytes = None
    if path.suffix.lower() == '.zip':
        try:
            with zipfile.ZipFile(path) as z:
                entries = z.infolist()
                names = [entry.filename for entry in entries]
                if len(names) > 1000 or names.count('config.json') != 1:
                    raise ValueError('El ZIP no contiene una configuración compatible.')
                kind = 'cloud' if 'discloud.config' in names and 'bot.py' in names else 'local'
                if kind == 'local' and not ('local-runner.exe' in names and ('iniciar.bat' in names or 'start.bat' in names)):
                    raise ValueError('El ZIP no contiene una configuración compatible.')
                info = z.getinfo('config.json')
                if info.file_size > MAX_CONFIG:
                    raise ValueError('El ZIP no contiene una configuración compatible.')
                c = _read_package_config(z.read(info))
                if c['image']:
                    relative = _relative_package_path(c['image'])
                    image_name = str(relative)
                    if names.count(image_name) != 1:
                        raise ValueError('No se encuentra la imagen dentro del paquete.')
                    info = z.getinfo(image_name)
                    if info.file_size > MAX_IMAGE:
                        raise ValueError('Esta versión admite imágenes de hasta 10 MB.')
                    image_bytes = z.read(info)
            source = dict(path=str(path), kind=kind)
        except (zipfile.BadZipFile, RuntimeError, KeyError):
            raise ValueError('No se pudo leer el ZIP. Selecciona un paquete válido de este programa.') from None
    elif path.suffix.lower() == '.bat':
        try:
            folder = bat_package_directory(path)
            config_path = folder / 'config.json'
            if config_path.stat().st_size > MAX_CONFIG:
                raise ValueError('El archivo no contiene una configuración compatible de este programa.')
            c = _read_package_config(config_path.read_bytes())
            if c['image']:
                relative = _relative_package_path(c['image'])
                image_path = (folder / str(relative)).resolve()
                if not image_path.is_relative_to(folder):
                    raise ValueError('El paquete contiene una ruta de archivo no válida.')
                if image_path.stat().st_size > MAX_IMAGE:
                    raise ValueError('Esta versión admite imágenes de hasta 10 MB.')
                image_bytes = image_path.read_bytes()
            source = dict(path=str(path), kind='bat', folder=str(folder))
        except UnicodeError:
            raise ValueError('Este BAT no tiene una configuración compatible. Selecciona un BAT generado por este programa.') from None
    else:
        raise ValueError('Selecciona un archivo BAT o ZIP generado por este programa.')
    image_path = None
    try:
        if image_bytes is not None:
            suffix = Path(c['image']).suffix.lower()
            if suffix not in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
                raise ValueError('Elige una imagen PNG, JPG, GIF o WEBP.')
            folder = Path(cache) / uuid.uuid4().hex
            folder.mkdir(parents=True)
            image_path = folder / ('imagen' + suffix)
            image_path.write_bytes(image_bytes)
            c['image'] = str(image_path.resolve())
        c = validate(c)
        return dict(config=c, source=source)
    except Exception:
        if image_path is not None:
            image_path.unlink(missing_ok=True)
            image_path.parent.rmdir()
        raise


def update_package(source, config, base, language='Español'):
    path = Path(source['path'])
    if source['kind'] == 'cloud':
        export_zip(path, config, base, language)
    elif source['kind'] == 'local':
        export_local_zip(path, config, base, language)
    elif source['kind'] == 'bat':
        # New runtime files avoid modifying an executable that may still be open.
        launcher = Path(export_local_desktop(config, base, language, desktop=path.parent))
        folder = bat_package_directory(launcher)
        old_state = Path(source['folder']) / 'ultimo_envio.json'
        try:
            if old_state.is_file() and old_state.stat().st_size <= MAX_CONFIG:
                state = json.loads(old_state.read_text(encoding='utf-8'))
                if isinstance(state, dict) and isinstance(state.get('channels'), dict) and str(state.get('account_id', '')).isdigit():
                    (folder / 'ultimo_envio.json').write_text(json.dumps(state), encoding='utf-8')
            os.replace(launcher, path)
        except Exception:
            launcher.unlink(missing_ok=True)
            raise
        return dict(source, folder=str(folder))
    else:
        raise ValueError('Selecciona un archivo BAT o ZIP generado por este programa.')
    return dict(source)

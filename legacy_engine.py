# bot.py
import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta
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

def _log(nivel: str, mensaje: str) -> None:
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        pass


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
        try:
            async with session.get(
                url,
                headers=_headers(token),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    guild_id = data.get("guild_id") or ""
                    _guild_map[ch_id_str] = guild_id
                    destino = f"guild {guild_id}" if guild_id else "DM/grupo"
                    _log("INFO", f"[INIT] Canal {ch_id_str} → {destino}")
                else:
                    _log("WARN", f"[INIT] Canal {ch_id_str} → HTTP {resp.status} (Referer por defecto)")
        except Exception as exc:
            _log("WARN", f"[INIT] Canal {ch_id_str} excepción: {type(exc).__name__}: {exc}")
        await asyncio.sleep(random.uniform(0.3, 0.8))


# ─── Borrar mensaje anterior ──────────────────────────────────────────────────

async def _borrar_mensaje(
    session: aiohttp.ClientSession, token: str, channel_id: str, message_id: str
) -> None:
    url = f"{API_BASE}/channels/{channel_id}/messages/{message_id}"
    ref = _referer(channel_id)
    t0  = time.time()
    try:
        async with session.delete(
            url,
            headers=_headers(token, ref),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            ms = int((time.time() - t0) * 1000)
            if resp.status in (204, 404):
                _log("DEBUG", f"[DEL] Canal {channel_id} msg {message_id} → HTTP {resp.status} ({ms}ms)")
            else:
                body = await resp.text()
                _log("WARN", f"[DEL] No se pudo borrar msg {message_id} canal {channel_id} → HTTP {resp.status} ({ms}ms): {body[:150]}")
    except Exception as exc:
        ms = int((time.time() - t0) * 1000)
        _log("WARN", f"[DEL] Excepción borrando msg {message_id} canal {channel_id} ({ms}ms): {type(exc).__name__}: {exc}")


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
        _log("WARN", f"[STATE] No se pudo leer {STATE_PATH}: {type(exc).__name__}: {exc}")
    return {}


def _guardar_ultimo_msg(data: dict) -> None:
    tmp_path = STATE_PATH + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp_path, STATE_PATH)
    except Exception as exc:
        _log("WARN", f"[STATE] No se pudo guardar {STATE_PATH}: {type(exc).__name__}: {exc}")


# ─── Leer canal antes de enviar ───────────────────────────────────────────────

async def _leer_canal(
    session: aiohttp.ClientSession, token: str, channel_id: str
) -> None:
    """GET /messages?limit=3 — simula que el usuario lee el canal antes de escribir."""
    url = f"{API_BASE}/channels/{channel_id}/messages?limit=3"
    ref = _referer(channel_id)
    try:
        async with session.get(
            url,
            headers=_headers(token, ref),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                msgs = await resp.json()
                _log("DEBUG", f"[READ] Canal {channel_id} → {len(msgs)} mensajes leídos")
            elif resp.status == 429:
                _log("DEBUG", f"[READ] Canal {channel_id} rate-limited en GET, continuando")
                return
            else:
                _log("DEBUG", f"[READ] Canal {channel_id} → HTTP {resp.status}")
    except Exception as exc:
        _log("DEBUG", f"[READ] Canal {channel_id} excepción leyendo: {type(exc).__name__}: {exc}")
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

    restante = espera
    while restante > 0:
        try:
            async with session.post(
                url,
                headers=_headers(token, ref),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 204:
                    body = await resp.text()
                    _log("WARN", f"[TYP ] Canal {channel_id} → HTTP {resp.status}: {body[:150]}")
        except Exception as exc:
            _log("WARN", f"[TYP ] Canal {channel_id} excepción: {type(exc).__name__}: {exc}")
            return
        # Discord expira el indicador ~10s; se retriggerea en tramos para sostenerlo.
        tramo = min(8.0, restante)
        await asyncio.sleep(tramo)
        restante -= tramo


# ─── Enviar mensaje a un canal via REST API ───────────────────────────────────

async def _enviar_canal(
    session: aiohttp.ClientSession, token: str,
    channel_id: str, contenido: str, rutas: list,
) -> tuple:
    """
    Retorna (message_id, None) en éxito.
    Retorna (None, segundos) si hay rate limit.
    Retorna (None, None) en error permanente.
    """
    url  = f"{API_BASE}/channels/{channel_id}/messages"
    ref  = _referer(channel_id)
    hdrs = _headers(token, ref)
    MAX_INTENTOS = 3

    _log("DEBUG", f"[POST] Canal {channel_id} | texto={len(contenido)}c | imgs={len(rutas)}")

    # Leer canal (simula usuario leyendo antes de escribir)
    await _leer_canal(session, token, channel_id)

    # Typing indicator con duración proporcional al contenido
    await _mostrar_escribiendo(session, token, channel_id, contenido, num_imagenes=len(rutas))

    for intento in range(1, MAX_INTENTOS + 1):
        t0    = time.time()
        nonce = _gen_nonce()
        try:
            if rutas:
                # Multipart: metadata en payload_json, archivos en files[]
                payload_json = {"nonce": nonce, "tts": False, "flags": 0}
                if contenido:
                    payload_json["content"] = contenido
                form = aiohttp.FormData()
                form.add_field(
                    "payload_json",
                    json.dumps(payload_json),
                    content_type="application/json",
                )
                for i, ruta in enumerate(rutas):
                    with open(ruta, "rb") as img:
                        data_bytes = img.read()
                    form.add_field(
                        f"files[{i}]",
                        data_bytes,
                        filename=os.path.basename(ruta),
                        content_type="application/octet-stream",
                    )
                    _log("DEBUG", f"[POST] Adjuntando imagen [{i}] {os.path.basename(ruta)} ({len(data_bytes)} bytes)")
                resp_cm = session.post(url, headers=hdrs, data=form,
                                       timeout=aiohttp.ClientTimeout(total=30))
            else:
                # JSON puro
                payload = {"nonce": nonce, "tts": False, "flags": 0}
                if contenido:
                    payload["content"] = contenido
                resp_cm = session.post(url, headers=hdrs, json=payload,
                                       timeout=aiohttp.ClientTimeout(total=30))

            async with resp_cm as resp:
                ms = int((time.time() - t0) * 1000)
                _log("DEBUG", f"[POST] Canal {channel_id} → HTTP {resp.status} ({ms}ms) intento={intento}")

                if resp.status == 429:
                    data = await resp.json()
                    espera = float(data.get("retry_after", 60)) + 1
                    global_rl = data.get("global", False)
                    _log("WARN", f"[RL  ] Canal {channel_id} rate limit: retry_after={espera:.1f}s global={global_rl}")
                    return None, espera

                if resp.status in (401, 403):
                    body = await resp.text()
                    _log("ERROR", f"[AUTH] Canal {channel_id} HTTP {resp.status}: {body[:300]}")
                    return None, None

                if resp.status == 400:
                    body = await resp.text()
                    _log("ERROR", f"[400 ] Canal {channel_id} Bad Request: {body[:300]}")
                    return None, None

                if resp.status in (200, 201):
                    data = await resp.json()
                    msg_id = data.get("id", "?")
                    _log("DEBUG", f"[OK  ] Canal {channel_id} mensaje enviado id={msg_id} ({ms}ms)")
                    return msg_id, None

                body = await resp.text()
                _log("WARN", f"[ERR ] Canal {channel_id} HTTP {resp.status} (intento {intento}/{MAX_INTENTOS}): {body[:200]}")

        except asyncio.TimeoutError:
            ms = int((time.time() - t0) * 1000)
            _log("WARN", f"[TOUT] Canal {channel_id} timeout tras {ms}ms (intento {intento}/{MAX_INTENTOS})")
        except Exception as exc:
            ms = int((time.time() - t0) * 1000)
            _log("ERROR", f"[EXC ] Canal {channel_id} {type(exc).__name__}: {exc} ({ms}ms, intento {intento}/{MAX_INTENTOS})")

        if intento < MAX_INTENTOS:
            espera_reintento = min(5 * (2 ** (intento - 1)), 30)
            _log("DEBUG", f"[WAIT] Canal {channel_id} esperando {espera_reintento}s antes de reintento {intento+1}...")
            await asyncio.sleep(espera_reintento)

    _log("ERROR", f"[FAIL] Canal {channel_id} agotó {MAX_INTENTOS} intentos")
    return None, None


def configuration_adapter(config):
    return config


# ─── Loop principal ───────────────────────────────────────────────────────────

async def main():
    config_path = os.path.join(BASE, "config.json")
    _log("INFO", f"Cargando config desde: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        config = configuration_adapter(json.load(f))

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
        _log("ERROR", "Token no encontrado en config.json — deteniendo bot"); return
    if not channels:
        _log("ERROR", "Sin canales configurados en config.json — deteniendo bot"); return
    if not config.get("activo", True):
        _log("WARN", "Bot desactivado (activo: false) — deteniendo bot"); return

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
    _log("INFO", f"API_BASE       : {API_BASE}")
    _log("INFO", "Token          : [oculto]")
    _log("INFO", f"Canales        : {len(channels)} → {channels}")
    _log("INFO", f"Intervalo      : {intervalo}s ({intervalo//60}min)")
    _log("INFO", f"Schedule type  : {sched_type}" + (f" | hora={hora_envio} dias={dias_activos}" if sched_type == "schedule" else ""))
    _log("INFO", f"Imagenes       : {len(rutas)} archivo(s) | modo={modo_imagenes}")
    _log("INFO", f"Mensaje base   : {repr(mensaje_base[:80])}")
    _log("INFO", f"Mensajes alt   : {len(mensajes_alt)} | modo={modo_mensajes}")
    _log("INFO", f"Borrar anterior: {borrar_anterior}")
    _log("INFO", f"Silencio       : {silencio_desde}→{silencio_hasta}" if silencio_desde else "Silencio       : desactivado")
    _sep()

    num_envio    = 0
    carousel_idx = 0
    msg_seq_idx  = 0
    ultimo_msg: dict = _cargar_ultimo_msg()
    rl_hasta:   dict = {}  # channel_id → unix timestamp cuando expira RL
    if ultimo_msg:
        _log("INFO", f"[STATE] {len(ultimo_msg)} mensaje(s) previo(s) recuperado(s) de {STATE_PATH}")

    async with aiohttp.ClientSession() as session:

        # Obtener guild_id de cada canal para Referers precisos
        _log("INFO", "Obteniendo info de canales (guild IDs para Referer)...")
        await _obtener_guild_ids(session, token, channels)
        _sep()

        # ── Helper interno ───────────────────────────────────────────────────

        async def _enviar_a_canal(ch_id_str: str, contenido: str, rutas_envio: list, ciclo: int) -> str:
            """Envía a un canal. Retorna 'ok', 'rl', 'error'."""
            # Pausa de "reconocimiento" — simula que el usuario ve el chat antes de actuar
            pausa_previa = random.uniform(1.0, 3.5)
            await asyncio.sleep(pausa_previa)

            if borrar_anterior and ch_id_str in ultimo_msg:
                _log("INFO", f"[DEL] Borrando msg anterior {ultimo_msg[ch_id_str]} en canal {ch_id_str}")
                await _borrar_mensaje(session, token, ch_id_str, ultimo_msg[ch_id_str])

            msg_id, retry_after = await _enviar_canal(session, token, ch_id_str, contenido, rutas_envio)

            if msg_id:
                ultimo_msg[ch_id_str] = msg_id
                _guardar_ultimo_msg(ultimo_msg)
                rl_hasta.pop(ch_id_str, None)
                _log("OK   ", f"Canal {ch_id_str} ✓ id={msg_id} | ciclo #{ciclo}")
                return "ok"
            elif retry_after is not None:
                expira = time.time() + retry_after
                rl_hasta[ch_id_str] = expira
                expira_str = datetime.fromtimestamp(expira).strftime("%H:%M:%S")
                _log("WARN", f"[RL  ] Canal {ch_id_str} en rate limit {retry_after:.0f}s → se intenta de nuevo a las {expira_str}")
                return "rl"
            else:
                _log("ERROR", f"Canal {ch_id_str} ✗ error permanente | ciclo #{ciclo}")
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
                        proxima = (ahora + timedelta(seconds=espera)).strftime("%Y-%m-%d %H:%M:%S")
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
                    _log("INFO", f"Estado RL: {len(canales_en_rl)} canal(es) en espera:")
                    for cid, t in canales_en_rl:
                        _log("INFO", f"  └─ canal {cid} libre a las {datetime.fromtimestamp(t).strftime('%H:%M:%S')} (en {t-ahora_ts:.0f}s)")

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
                _log("INFO", f"Orden canales   : {channels_ciclo}")
                _log("INFO", f"Imágenes ciclo  : {[os.path.basename(r) for r in rutas_envio]}")
                _log("INFO", f"Mensaje         : {repr(contenido[:100])}")

                # ── Primera pasada: canales disponibles ───────────────────────
                en_espera: list = []
                stats = {"ok": 0, "rl": 0, "error": 0}

                for ch_id in channels_ciclo:
                    ch_id_str = str(ch_id)
                    ahora_ts  = time.time()
                    if ch_id_str in rl_hasta and ahora_ts < rl_hasta[ch_id_str]:
                        secs_left = rl_hasta[ch_id_str] - ahora_ts
                        _log("INFO", f"[SKIP] Canal {ch_id_str} todavía en RL ({secs_left:.0f}s) → segunda pasada")
                        en_espera.append(ch_id_str)
                        continue

                    resultado = await _enviar_a_canal(ch_id_str, contenido, rutas_envio, num_envio)
                    stats[resultado] += 1
                    if resultado == "rl":
                        en_espera.append(ch_id_str)
                    pausa_canal = random.uniform(12, 20)
                    _log("INFO", f"[WAIT] Esperando {pausa_canal:.1f}s antes del próximo canal...")
                    await asyncio.sleep(pausa_canal)

                # ── Segunda pasada: canales con RL que ya expiró ──────────────
                if en_espera:
                    _log("INFO", f"Segunda pasada: {len(en_espera)} canal(es) con rate limit pendiente")
                    for ch_id_str in en_espera:
                        espera_rl = max(0.0, rl_hasta.get(ch_id_str, 0) - time.time())
                        if espera_rl > intervalo:
                            _log("WARN", f"[SKIP] Canal {ch_id_str} RL demasiado largo ({espera_rl:.0f}s > {intervalo}s) → próximo ciclo")
                            stats["rl"] += 1
                            continue
                        if espera_rl > 0:
                            _log("INFO", f"[WAIT] Canal {ch_id_str}: esperando {espera_rl:.0f}s antes de reintentar...")
                            await asyncio.sleep(espera_rl)
                        resultado = await _enviar_a_canal(ch_id_str, contenido, rutas_envio, num_envio)
                        stats[resultado] += 1
                        pausa_canal = random.uniform(12, 20)
                        _log("INFO", f"[WAIT] Esperando {pausa_canal:.1f}s antes del próximo canal...")
                        await asyncio.sleep(pausa_canal)

                # ── Resumen del ciclo ─────────────────────────────────────────
                _sep(f"FIN CICLO #{num_envio}")
                _log("INFO", f"Resultado: {stats['ok']} OK | {stats['rl']} RL | {stats['error']} ERROR | total={len(channels)}")
                if stats["rl"] > 0:
                    pendientes = [(cid, rl_hasta[cid]) for cid in rl_hasta if cid in [str(c) for c in channels]]
                    for cid, t in pendientes:
                        _log("WARN", f"  └─ canal {cid} sigue en RL hasta {datetime.fromtimestamp(t).strftime('%H:%M:%S')}")

                if sched_type == "interval":
                    jitter = random.uniform(-0.15, 0.15)
                    espera_ciclo = int(intervalo * (1 + jitter))
                    prox = datetime.now() + timedelta(seconds=espera_ciclo)
                    _log("INFO", f"Esperando {espera_ciclo}s (jitter {jitter:+.0%}) | próximo ciclo a las {prox.strftime('%H:%M:%S')}")
                    await asyncio.sleep(espera_ciclo)
                else:
                    await asyncio.sleep(60)

            except Exception as exc:
                _log("ERROR", f"[LOOP] Excepción no capturada en el ciclo, se continúa en 10s: {type(exc).__name__}: {exc}")
                await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())

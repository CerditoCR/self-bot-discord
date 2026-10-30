"""Spanish console diagnostics with synthetic data and no network."""
import asyncio
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import aiohttp
import bot
import legacy_engine as engine

class LogTests(unittest.TestCase):
    def setUp(self):
        for name, value in [('_delivery_path', None), ('_delivery_state', dict(pending={}, paused={}, cleanup={}, global_until=0, stopped=False)), ('_delivery_signatures', {}), ('_account_id', '')]:
            item = patch.object(engine, name, value)
            item.start()
            self.addCleanup(item.stop)

    def test_console_is_flushed_spanish_and_redacted(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(engine, 'LOG_PATH', str(Path(folder) / 'bot.log')), patch.object(engine, '_log_secrets', ['DUMMY_SECRET']), patch('builtins.print') as output:
            engine._log('WARN', 'Aviso DUMMY_SECRET\nOtra línea')
            line = output.call_args.args[0]
            self.assertIn('[ADVERTENCIA]', line)
            self.assertNotIn('DUMMY_SECRET', line)
            self.assertNotIn('\n', line)
            self.assertTrue(output.call_args.kwargs['flush'])
            self.assertIn('[credencial oculta]', Path(folder, 'bot.log').read_text(encoding='utf-8'))

    def test_destination_metadata_for_each_message(self):
        config = dict(token='DUMMY_TEST_ONLY', account_type='personal', minutes=30, channels=['123456789012345678'], message='Uno', image='', channel_metadata=[dict(id='123456789012345678', name='frutas', group='Tienda', guild_id='333')], extra_messages=[dict(channels=['223456789012345678'], message='Dos', image='', channel_metadata=[dict(id='223456789012345678', name='verduras', group='Tienda', guild_id='333')])])
        with patch.dict(bot.os.environ, {}, clear=True):
            adapted = bot.adapt_config(config)
        with patch.object(engine, '_channel_details', adapted['channel_content']):
            label = engine._channel_label('223456789012345678')
            self.assertIn('Mensaje 2', label)
            self.assertIn('#verduras', label)
            self.assertIn('223456789012345678', label)
            self.assertIn('Tienda', label)
            self.assertIn('333', label)
            self.assertNotIn('frutas', label)
            self.assertIn('999', engine._channel_label('999'))

    def test_http_errors_spanish_and_retries(self):
        class Response:
            def __init__(self, status): self.status = status
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def json(self): return dict(code=50013 if self.status == 403 else 0, message='Missing Permissions', id='123')
        for status, phrase in [(400, 'Solicitud inválida'), (401, 'credencial'), (403, 'permiso'), (404, 'no existe'), (429, 'limitado'), (500, 'error de servidor')]:
            description = asyncio.run(engine._http_description(Response(status)))
            self.assertIn(phrase, description)
            self.assertIn('Código de Discord', description)
            self.assertNotIn('Missing Permissions', description)
        class Session:
            def __init__(self, statuses): self.statuses = iter(statuses)
            def post(self, *args, **kwargs): return Response(next(self.statuses))
            def get(self, *args, **kwargs):
                response = Response(200)
                response.json = AsyncMock(return_value=[])
                return response
        with patch.object(engine, '_leer_canal', new_callable=AsyncMock), patch.object(engine, '_mostrar_escribiendo', new_callable=AsyncMock), patch.object(engine.asyncio, 'sleep', new_callable=AsyncMock), patch.object(engine, '_log') as log:
            result = asyncio.run(engine._enviar_canal(Session([500, 200]), 'DUMMY_TEST_ONLY', '123', 'Texto', []))
            self.assertEqual(result, ('123', None))
            messages = ' '.join(call.args[1] for call in log.call_args_list)
            self.assertIn('intento 2/3', messages)
            self.assertIn('error de servidor', messages)
            result = asyncio.run(engine._enviar_canal(Session([403]), 'DUMMY_TEST_ONLY', '456', 'Texto', []))
            self.assertEqual(result, (None, None))
        self.assertIn('tiempo de espera', engine._error_description(TimeoutError('English secret error')))
        self.assertNotIn('English secret error', engine._error_description(aiohttp.ClientError('English secret error')))

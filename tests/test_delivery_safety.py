"""Failure recovery and safe replacement; every HTTP response is simulated."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import bot
import legacy_engine as engine

class Response:
    def __init__(self, status=200, data=None, error=None, headers=None):
        self.status, self.data, self.error, self.headers = status, data, error, headers or {}
    async def __aenter__(self):
        if self.error: raise self.error
        return self
    async def __aexit__(self, *args): pass
    async def json(self): return self.data

class Session:
    def __init__(self, posts=(), reads=(), deletes=()):
        self.posts, self.reads, self.deletes = iter(posts), iter(reads), iter(deletes)
        self.payloads = []
    def post(self, url, **options):
        self.payloads.append(options)
        return next(self.posts)
    def get(self, *args, **kwargs): return next(self.reads)
    def delete(self, *args, **kwargs): return next(self.deletes)
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass

class DeliverySafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name, value in [('BASE', str(self.root)), ('STATE_PATH', str(self.root / 'ultimo_msg.json')), ('_delivery_path', None), ('_delivery_state', dict(pending={}, paused={}, cleanup={}, global_until=0, stopped=False)), ('_delivery_signatures', {}), ('_account_id', ''), ('_log', None)]:
            item = patch.object(engine, name) if name == '_log' else patch.object(engine, name, value)
            result = item.start()
            self.addCleanup(item.stop)
            if name == '_log': self.log = result
        for name in ('_leer_canal', '_mostrar_escribiendo'):
            item = patch.object(engine, name, new_callable=AsyncMock)
            item.start()
            self.addCleanup(item.stop)
        item = patch.object(engine.asyncio, 'sleep', new_callable=AsyncMock)
        self.sleep = item.start()
        self.addCleanup(item.stop)

    def send(self, session, channel='123'):
        return asyncio.run(engine._enviar_canal(session, 'DUMMY_TEST_ONLY', channel, 'Texto', [], previous_id='111'))

    def test_same_nonce_is_enforced_on_retry(self):
        session = Session(posts=[Response(500, {}), Response(200, {'id': '222'})], reads=[Response(200, [])])
        self.assertEqual(self.send(session), ('222', None))
        self.assertEqual(len(session.payloads), 2)
        first, second = [options['json'] for options in session.payloads]
        self.assertEqual(first['nonce'], second['nonce'])
        self.assertTrue(first['enforce_nonce'])
        self.assertTrue(second['enforce_nonce'])

    def test_lost_response_is_recovered_without_second_post(self):
        async def messages():
            return [dict(id='222', nonce=engine._delivery_state['pending']['123']['nonce'])]
        read = Response()
        read.json = messages
        session = Session(posts=[Response(error=TimeoutError())], reads=[read])
        self.assertEqual(self.send(session), ('222', None))
        self.assertEqual(len(session.payloads), 1)
        self.assertIn('ENVÍO RECUPERADO', ' '.join(call.args[1] for call in self.log.call_args_list))

    def test_unknown_delivery_is_not_resent_on_next_call(self):
        session = Session(posts=[Response(500, {}) for _ in range(3)], reads=[Response(200, []) for _ in range(4)])
        self.assertEqual(self.send(session), (None, None))
        self.assertIn('123', engine._delivery_state['pending'])
        self.assertEqual(self.send(session), (None, None))
        self.assertEqual(len(session.payloads), 3)
        self.assertIn('no se reenviará a ciegas', self.log.call_args.args[1])

    def test_pending_delivery_survives_restart(self):
        config = dict(token='DUMMY_TEST_ONLY', channel_content={})
        engine._load_delivery_state(config)
        pending = dict(nonce='1234', previous='111', created=0, uncertain=True)
        engine._delivery_state['pending']['123'] = pending
        engine._save_delivery_state()
        engine._load_delivery_state(config)
        session = Session(reads=[Response(200, [dict(id='222', nonce='1234')])])
        self.assertEqual(self.send(session), ('222', None))
        self.assertFalse(session.payloads)
        self.assertNotIn('DUMMY_TEST_ONLY', (self.root / 'estado_entregas.json').read_text())

    def test_auth_error_stops_and_is_remembered(self):
        config = dict(token='DUMMY_TEST_ONLY', channel_content={})
        engine._load_delivery_state(config)
        with self.assertRaises(engine.StopDelivery):
            self.send(Session(posts=[Response(401, {})]))
        with self.assertRaises(engine.StopDelivery):
            engine._load_delivery_state(config)
        engine._load_delivery_state(dict(config, token='NEW_DUMMY_ONLY'))
        self.assertFalse(engine._delivery_state['stopped'])

    def test_permission_pause_and_other_channel_continues(self):
        session = Session(posts=[Response(403, {'code': 50013}), Response(200, {'id': '333'})])
        self.assertEqual(self.send(session), (None, None))
        self.assertEqual(self.send(session), (None, None))
        self.assertEqual(len(session.payloads), 1)
        self.assertEqual(self.send(session, '456'), ('333', None))
        self.assertEqual(len(session.payloads), 2)
        self.assertIn('permisos', engine._delivery_state['paused']['123']['reason'])

    def test_content_pause_clears_after_configuration_changes(self):
        engine._delivery_signatures['123'] = 'before'
        self.send(Session(posts=[Response(400, {'code': 50035})]))
        self.assertIsNone(engine._delivery_state['paused']['123']['until'])
        engine._delivery_signatures['123'] = 'after'
        self.assertEqual(self.send(Session(posts=[Response(200, {'id': '222'})])), ('222', None))

    def test_global_limit_delays_other_destinations(self):
        session = Session(posts=[Response(429, {'retry_after': 25, 'global': True}), Response(200, {'id': '333'})])
        self.assertEqual(self.send(session), (None, 26))
        self.assertNotIn('123', engine._delivery_state['pending'])
        self.assertEqual(self.send(session, '456'), ('333', None))
        self.assertTrue(any(call.args[0] >= 25 for call in self.sleep.call_args_list))

    def test_cannot_save_state_means_no_post(self):
        engine._delivery_path = str(self.root / 'missing' / 'state.json')
        session = Session(posts=[Response(200, {'id': '222'})])
        with self.assertRaises(engine.StopDelivery): self.send(session)
        self.assertFalse(session.payloads)

    def run_round(self, send_result, delete_result=True):
        config = dict(token='DUMMY_TEST_ONLY', account_type='personal', minutes=2,
                      channels=['123456789012345678'], message='Texto', image='')
        (self.root / 'config.json').write_text(json.dumps(config), encoding='utf-8')
        (self.root / 'ultimo_msg.json').write_text(json.dumps({'123456789012345678': '111'}), encoding='utf-8')
        events = []
        async def send(*args, **kwargs): events.append('send'); return send_result
        async def delete(*args, **kwargs): events.append('delete'); return delete_result
        async def sleep(delay):
            if delay > 30: raise asyncio.CancelledError()
        with patch.object(engine, 'configuration_adapter', bot.adapt_config), patch.object(engine.aiohttp, 'ClientSession', return_value=Session()), patch.object(engine, '_obtener_guild_ids', new_callable=AsyncMock), patch.object(engine, '_enviar_canal', side_effect=send), patch.object(engine, '_borrar_mensaje', side_effect=delete), patch.object(engine.asyncio, 'sleep', side_effect=sleep), patch.dict(bot.os.environ, {}, clear=True):
            with self.assertRaises(asyncio.CancelledError): asyncio.run(engine.main())
        return events

    def test_only_delete_after_confirmed_send_and_state_saved(self):
        self.assertEqual(self.run_round(('222', None)), ['send', 'delete'])
        self.assertEqual(json.loads((self.root / 'ultimo_msg.json').read_text()), {'123456789012345678': '222'})
        self.assertFalse(engine._delivery_state['cleanup'])

    def test_failed_send_preserves_previous_message(self):
        self.assertEqual(self.run_round((None, None)), ['send'])
        self.assertEqual(json.loads((self.root / 'ultimo_msg.json').read_text()), {'123456789012345678': '111'})

    def test_failed_delete_is_saved_for_cleanup(self):
        self.assertEqual(self.run_round(('222', None), False), ['send', 'delete'])
        self.assertEqual(engine._delivery_state['cleanup'], {'123456789012345678': '111'})
        self.assertEqual(json.loads((self.root / 'ultimo_msg.json').read_text()), {'123456789012345678': '222'})

    def test_delete_missing_message_is_already_complete(self):
        self.assertTrue(asyncio.run(engine._borrar_mensaje(Session(deletes=[Response(404)]), 'DUMMY_TEST_ONLY', '123', '111')))

    def test_single_instance_lock_is_released(self):
        with engine.delivery_lock():
            with self.assertRaises(engine.StopDelivery):
                with engine.delivery_lock(): pass
        with engine.delivery_lock(): pass

    def test_corrupt_state_stops_before_network(self):
        (self.root / 'estado_entregas.json').write_text('{broken', encoding='utf-8')
        with self.assertRaises(engine.StopDelivery):
            engine._load_delivery_state(dict(token='DUMMY_TEST_ONLY', channel_content={}))

    def test_long_global_wait_does_not_retry_old_nonce(self):
        first = Response(500, {})
        session = Session(posts=[first], reads=[Response(200, [])])
        async def sleep(delay):
            pending = engine._delivery_state['pending'].get('123')
            if pending: pending['created'] -= 120
        with patch.object(engine.asyncio, 'sleep', side_effect=sleep):
            self.assertEqual(self.send(session), (None, None))
        self.assertEqual(len(session.payloads), 1)

    def test_global_limit_from_headers_is_respected(self):
        response = Response(429, {}, headers={'Retry-After': '12.5', 'X-RateLimit-Scope': 'global'})
        self.assertEqual(engine._record_limit(response, {}), 13.5)
        self.assertGreater(engine._delivery_state['global_until'], 0)

    def test_token_refresh_for_same_account_preserves_pending(self):
        config = dict(token='DUMMY_TEST_ONLY', account_id='555', channel_content={})
        engine._load_delivery_state(config)
        engine._delivery_state['pending']['123'] = dict(nonce='1234', previous='111', created=0, uncertain=True)
        engine._delivery_state['stopped'] = True
        engine._save_delivery_state()
        self.assertTrue(engine._load_delivery_state(dict(config, token='NEW_DUMMY_ONLY')))
        self.assertIn('123', engine._delivery_state['pending'])
        self.assertFalse(engine._delivery_state['stopped'])

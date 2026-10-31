"""Multiple-message packages and delivery, entirely offline."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import zipfile
from PIL import Image
import app
import bot
import core
import legacy_engine as engine

ROOT = Path(__file__).resolve().parents[1]

class MultipleMessageTests(unittest.TestCase):
    def isolate_delivery_state(self):
        for name, value in [('_delivery_path', None), ('_delivery_state', dict(pending={}, paused={}, cleanup={}, global_until=0, stopped=False)), ('_delivery_signatures', {}), ('_account_id', '')]:
            item = patch.object(engine, name, value)
            item.start()
            self.addCleanup(item.stop)

    def setUp(self):
        self.isolate_delivery_state()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.first = self.root / 'first.png'
        self.second = self.root / 'second.png'
        Image.new('RGB', (30, 20), 'red').save(self.first)
        Image.new('RGB', (30, 20), 'blue').save(self.second)
        self.config = dict(token='DUMMY_TEST_ONLY', account_type='personal', minutes=2,
                           channels=['123456789012345678'], message='First', image=str(self.first),
                           extra_messages=[dict(channels=['223456789012345678'], message='Second', image=str(self.second))])

    def test_packages_roundtrip_and_update(self):
        for kind, export in [('cloud', core.export_zip), ('local', core.export_local_zip)]:
            path = self.root / (kind + '.zip')
            export(path, self.config, ROOT)
            with zipfile.ZipFile(path) as z:
                c = json.loads(z.read('config.json'))
                self.assertNotEqual(c['image'], c['extra_messages'][0]['image'])
                self.assertEqual(z.read(c['image']), self.first.read_bytes())
                self.assertEqual(z.read(c['extra_messages'][0]['image']), self.second.read_bytes())
            loaded = core.import_package(path, self.root / 'cache')
            loaded['config']['extra_messages'][0]['message'] = 'Edited second'
            core.update_package(loaded['source'], loaded['config'], ROOT)
            result = core.import_package(path, self.root / 'cache')['config']
            self.assertEqual(result['message'], 'First')
            self.assertEqual(result['extra_messages'][0]['message'], 'Edited second')
            self.assertEqual(Path(result['extra_messages'][0]['image']).read_bytes(), self.second.read_bytes())
        bat = core.export_local_desktop(self.config, ROOT, desktop=self.root)
        loaded = core.import_package(bat, self.root / 'cache')
        self.assertEqual(loaded['config']['extra_messages'][0]['channels'], ['223456789012345678'])
        core.update_package(loaded['source'], loaded['config'], ROOT)
        self.assertEqual(core.import_package(bat, self.root / 'cache')['config']['extra_messages'][0]['message'], 'Second')

    def test_validation_and_extra_path_rejection(self):
        c = dict(self.config, extra_messages=[dict(channels=self.config['channels'], message='Duplicate')])
        with self.assertRaisesRegex(ValueError, 'Mensaje 2'):
            core.validate(c)
        c = dict(self.config, extra_messages=[dict(channels=['223456789012345678'], message='')])
        with self.assertRaisesRegex(ValueError, 'Mensaje 2'):
            core.validate(c)
        path = self.root / 'unsafe.zip'
        c = dict(self.config, image='', extra_messages=[dict(channels=['223456789012345678'], message='Second', image='../outside.png')])
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('config.json', json.dumps(c))
            z.writestr('discloud.config', '')
            z.writestr('bot.py', '')
            z.writestr('../outside.png', b'bad')
        with self.assertRaises(ValueError):
            core.import_package(path, self.root / 'cache')

    def test_recheck_marks_each_id_and_blocks_invalid_export(self):
        def resolved(token, account_type, channel_id):
            if channel_id == '223456789012345678':
                raise core.APIError(404, {})
            return dict(id=channel_id, name='ventas', group='Tienda', guild_id='333')
        with patch.object(core, 'resolve_channel', side_effect=resolved):
            checked = core.recheck_channels('DUMMY_TEST_ONLY', 'personal',
                                            ['123456789012345678', '223456789012345678'])
        self.assertEqual(checked[0]['validation'], 'valid')
        self.assertEqual(checked[1]['validation'], 'invalid')
        invalid = dict(self.config, channel_metadata=[checked[1]])
        with self.assertRaisesRegex(ValueError, 'ID no válido'):
            core.validate(invalid)

    def test_engine_routes_each_content_and_image(self):
        (self.root / 'config.json').write_text(json.dumps(self.config), encoding='utf-8')
        class Session:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
        async def sleep(seconds):
            if seconds > 30:
                raise asyncio.CancelledError()
        send = AsyncMock(side_effect=[('first-id', None), ('second-id', None)])
        with patch.object(engine, 'BASE', str(self.root)), patch.object(engine, 'configuration_adapter', bot.adapt_config), patch.object(engine.aiohttp, 'ClientSession', return_value=Session()), patch.object(engine, '_obtener_guild_ids', new_callable=AsyncMock), patch.object(engine, '_enviar_canal', send), patch.object(engine, '_cargar_ultimo_msg', return_value={}), patch.object(engine, '_guardar_ultimo_msg'), patch.object(engine, '_log'), patch.object(engine, '_sep'), patch.object(engine.asyncio, 'sleep', side_effect=sleep), patch.dict(bot.os.environ, {}, clear=True):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(engine.main())
        self.assertEqual([(call.args[2], call.args[3], call.args[4]) for call in send.call_args_list], [
            ('123456789012345678', 'First', [str(self.first)]),
            ('223456789012345678', 'Second', [str(self.second)])])

    def test_editor_switch_restore_and_remove(self):
        with patch.object(app, 'DATA', self.root / 'saved.json'), patch.object(app, 'PREFS', self.root / 'prefs.json'):
            panel = app.App()
            panel.withdraw()
            self.addCleanup(panel.destroy)
            panel.token.set('DUMMY_TEST_ONLY')
            panel.posts = [dict(self.config), dict(self.config['extra_messages'][0])]
            panel.load_editor(0)
            panel.message.delete('1.0', 'end')
            panel.message.insert('1.0', 'First edited')
            panel.post_selector.current(1)
            panel.select_post()
            self.assertEqual(panel.message.get('1.0', 'end-1c'), 'Second')
            c = panel.validated_snapshot()
            self.assertEqual(c['message'], 'First edited')
            self.assertEqual(c['extra_messages'][0]['image'], str(self.second))
            self.assertTrue(panel.save())
            panel.add_post()
            self.assertEqual(len(panel.posts), 3)
            with patch.object(app.messagebox, 'askyesno', return_value=True):
                panel.remove_post()
            self.assertEqual(len(panel.posts), 2)
            panel.restore()
            self.assertEqual(panel.snapshot()['extra_messages'][0]['message'], 'Second')
            panel.language.set('English')
            panel.apply_language()
            self.assertEqual(panel.post_selector['values'], ('Message 1', 'Message 2'))
            panel.theme.set('Oscuro')
            panel.apply_theme()
            panel.update()

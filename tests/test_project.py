"""Offline tests: only synthetic credentials; no Discord requests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from PIL import Image
import core
from i18n import translate
ROOT = Path(__file__).resolve().parents[1]

class ProjectTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.base = self.root/'base'; self.base.mkdir()
        for name in ('bot.py','core.py','i18n.py','legacy_engine.py'):
            (self.base/name).write_bytes((ROOT/name).read_bytes())
        (self.base/'local-runner.exe').write_bytes(b'OFFLINE PLACEHOLDER - NEVER EXECUTE')
        self.config = dict(token='DUMMY_TEST_ONLY',account_type='personal',channels=['123456789012345678'],message='Original',minutes=30)
        network = patch.object(core.urllib.request,'urlopen',side_effect=AssertionError('Network forbidden'))
        network.start(); self.addCleanup(network.stop)

    def test_token_normalization(self):
        for token in ['DUMMY_TEST_ONLY','"DUMMY_TEST_ONLY"',"'DUMMY_TEST_ONLY'",'“DUMMY_TEST_ONLY”']:
            self.assertEqual(core.normalize_token(token),'DUMMY_TEST_ONLY')
        with self.assertRaises(ValueError): core.request('"unclosed','personal','/users/@me')
        self.assertTrue(core.validate(dict(self.config,read_before=False))['read_before'])

    def test_zip_languages_and_updates(self):
        for kind,export in [('cloud',core.export_zip),('local',core.export_local_zip)]:
            path = self.root/(kind+'.zip'); export(path,self.config,self.base,'English')
            with zipfile.ZipFile(path) as z:
                self.assertIn('README.txt',z.namelist())
                self.assertEqual(json.loads(z.read('config.json'))['language'],'English')
                self.assertIn('i18n.py' if kind=='cloud' else 'start.bat',z.namelist())
            loaded = core.import_package(path,self.root/'cache'); loaded['config']['message']='Edited'
            core.update_package(loaded['source'],loaded['config'],self.base,'Español')
            result = core.import_package(path,self.root/'cache')['config']
            self.assertEqual(result['message'],'Edited'); self.assertEqual(result['language'],'Español')

    def test_bat_update_preserves_state_and_existing_files(self):
        desktop = self.root/'Desktop with spaces';desktop.mkdir()
        existing = desktop/'BOT MENSAJE.bat';existing.write_text('user file')
        bat = Path(core.export_local_desktop(self.config,self.base,'English',desktop))
        self.assertEqual(existing.read_text(),'user file')
        loaded = core.import_package(bat,self.root/'cache'); old = Path(loaded['source']['folder'])
        state = dict(account_id='555',channels={'123456789012345678':'777'})
        (old/'ultimo_envio.json').write_text(json.dumps(state))
        delivery = dict(pending={}, paused={}, cleanup={'123456789012345678':'777'})
        (old/'estado_entregas.json').write_text(json.dumps(delivery))
        (old/'ultimo_msg.json').write_text(json.dumps({'123456789012345678':'888'}))
        result = core.update_package(loaded['source'],self.config,self.base,'Español')
        self.assertTrue(old.is_dir());self.assertTrue(bat.is_file())
        self.assertEqual(json.loads((Path(result['folder'])/'estado_entregas.json').read_text()),delivery)
        self.assertEqual(json.loads((Path(result['folder'])/'ultimo_msg.json').read_text()),{'123456789012345678':'888'})
        self.assertEqual(json.loads((Path(result['folder'])/'ultimo_envio.json').read_text()),state)
        self.assertEqual(core.import_package(bat,self.root/'cache')['config']['language'],'Español')

    def test_account_named_bat_and_collision(self):
        desktop = self.root/'Desktop'; desktop.mkdir()
        config = dict(self.config, account_username='cerdito.cr', account_id='123456789012345678')
        first = Path(core.export_local_desktop(config,self.base,'Español',desktop))
        second = Path(core.export_local_desktop(config,self.base,'English',desktop))
        self.assertEqual(first.name,'cerdito.cr.bat')
        self.assertEqual(second.name,'cerdito.cr (2).bat')
        self.assertTrue(core.bat_package_directory(first).name.startswith('cerdito.cr Local '))
        imported = core.import_package(first,self.root/'cache')['config']
        self.assertEqual(imported['account_username'],'cerdito.cr')
        self.assertEqual(imported['language'],'Español')

    def test_account_file_names_are_safe(self):
        self.assertEqual(core.package_name('CON'), '_CON')
        self.assertEqual(core.package_name('nul.txt'), '_nul.txt')
        self.assertEqual(core.package_name('..', '123456789012345678'),'123456789012345678')
        self.assertEqual(core.package_name('José'), 'Jose')
        for unsafe in ['../../evil', '%PATH% & calc!', 'user\nOTHER=1', 'a'*200]:
            stem=core.package_name(unsafe)
            self.assertLessEqual(len(stem),64)
            self.assertNotIn('/',stem)
            self.assertNotIn('%',stem)
            self.assertNotIn('&',stem)
            self.assertNotIn('\n',stem)

    def test_image_import_and_path_rejection(self):
        image = self.root/'image.png';Image.new('RGB',(20,10),'green').save(image)
        path = self.root/'image.zip';core.export_zip(path,dict(self.config,image=str(image)),self.base)
        result = core.import_package(path,self.root/'cache')
        self.assertEqual(Path(result['config']['image']).read_bytes(),image.read_bytes())
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('config.json',json.dumps(dict(self.config,image='../outside.png')))
            z.writestr('discloud.config','');z.writestr('bot.py','');z.writestr('../outside.png',b'bad')
        with self.assertRaises(ValueError):core.import_package(path,self.root/'cache')
        self.assertFalse((self.root/'outside.png').exists())

    def test_translated_stop_and_errors(self):
        self.assertEqual(translate('Detenido: Introduce un token válido, sin espacios ni comillas sueltas.','English'),'Stopped: Enter a valid token without spaces or unmatched quotes.')
        self.assertIn('Ctrl+C',translate('Para detener: pulsa Ctrl+C o cierra esta ventana.','English'))

if __name__ == '__main__':unittest.main()

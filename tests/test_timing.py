"""Offline verification of original runtime integration."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch
import bot
import legacy_engine as engine

class EngineTests(unittest.TestCase):
    def setUp(self):
        for name, value in [('_delivery_path', None), ('_delivery_state', dict(pending={}, paused={}, cleanup={}, global_until=0, stopped=False)), ('_delivery_signatures', {}), ('_account_id', '')]:
            item = patch.object(engine, name, value)
            item.start()
            self.addCleanup(item.stop)

    def test_adapter(self):
        c=dict(token='"DUMMY_TEST_ONLY"',account_type='personal',channels=['123456789012345678'],message='Example',image='',minutes=2)
        with patch.dict(bot.os.environ,{},clear=True): result=bot.adapt_config(c)
        self.assertEqual(result['token'],'DUMMY_TEST_ONLY')
        self.assertEqual(result['intervalo'],120)
        self.assertEqual(result['mensaje'],'Example')
        self.assertEqual(result['imagenes'],[])
        self.assertTrue(result['borrar_anterior'])

    def test_payload_and_order(self):
        events=[]
        owner=self
        class Response:
            status=200
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            async def json(self): return {'id':'987654321098765432'}
        class Session:
            def post(self,url,**kwargs):
                events.append('send')
                p=kwargs['json']
                owner.assertEqual(p['content'],'Example')
                owner.assertFalse(p['tts'])
                owner.assertEqual(p['flags'],0)
                owner.assertIn('nonce',p)
                owner.assertNotIn('allowed_mentions',p)
                return Response()
        async def read(*args,**kwargs): events.append('read')
        async def typing(*args,**kwargs): events.append('typing')
        with patch.object(engine,'_leer_canal',side_effect=read), patch.object(engine,'_mostrar_escribiendo',side_effect=typing), patch.object(engine,'_log'):
            result=asyncio.run(engine._enviar_canal(Session(),'DUMMY_TEST_ONLY','123','Example',[]))
        self.assertEqual(events,['read','typing','send'])
        self.assertEqual(result,('987654321098765432',None))

    def test_typing(self):
        class Response:
            status=204
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
        class Session:
            def post(self,*args,**kwargs): return Response()
        with patch.object(engine, '_log'), patch.object(engine.asyncio,'sleep',new_callable=AsyncMock) as sleep:
            asyncio.run(engine._mostrar_escribiendo(Session(),'DUMMY_TEST_ONLY','123','a'*2000,1))
        self.assertEqual([c.args[0] for c in sleep.call_args_list],[8,8,2])

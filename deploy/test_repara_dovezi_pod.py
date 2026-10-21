import asyncio
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, mock_open, patch
import repara_dovezi_pod as p


def fixture(method):
    return 'class Example:\n' + method


class Diagnostics(unittest.TestCase):
    def capture(self, screenshot_error=None, text_error=None):
        log = Mock()
        scope = dict(asyncio=asyncio, os=types.SimpleNamespace(makedirs=Mock()),
                     time=types.SimpleNamespace(strftime=lambda _: 'test'), jurnal=log)
        exec(fixture(p.NEW_CAPTURE), scope)
        page = Mock()
        page.is_closed.return_value = False
        page.screenshot = AsyncMock(side_effect=screenshot_error)
        page.evaluate = AsyncMock(return_value='first characters', side_effect=text_error)
        with patch('builtins.open', mock_open()) as opened:
            asyncio.run(scope['Example']()._captura_dot(types.SimpleNamespace(dot_page=page), 'dot_ui_lost'))
        return page, opened, log

    def test_page_access_errors_do_not_escape(self):
        log = Mock()
        scope = dict(jurnal=log)
        exec(fixture(p.NEW_CAPTURE), scope)
        page = Mock(); page.is_closed.side_effect = RuntimeError('closed browser')
        for call in (object(), types.SimpleNamespace(dot_page=page)):
            asyncio.run(scope['Example']()._captura_dot(call, 'lost'))
        self.assertEqual(log.call_count, 2)

    def test_actual_command_grammar(self):
        scope = {}; exec(fixture(p.NEW_COMMAND), scope)
        obj = scope['Example'](); obj.jurnal = Mock()
        commands = [
            ['pactl', 'load-module', 'module-null-sink', 'sink_name=wa_in_2', 'rate=48000', 'channels=1', 'sink_properties=device.description=WhatsApp_in_2'],
            ['pactl', 'load-module', 'module-remap-source', 'master=wa_in_2.monitor', 'source_name=mic_wa_2', 'source_properties=device.description=Microfon_WhatsApp_2'],
            ['pactl', 'list', 'short', 'sources'],
            ['pactl', 'load-module', 'module-null-sink', 'rate=44100', 'channels=2'],
        ]
        for command in commands:
            with self.assertRaises(RuntimeError):
                obj._eroare_sunet(types.SimpleNamespace(numar=2), 'failure', types.SimpleNamespace(args=command,stderr='failed',stdout='',returncode=1))
            self.assertEqual(obj.jurnal.call_args.args[0]['comanda'], command)

    def test_first_2000(self):
        page, opened, _ = self.capture()
        self.assertEqual(page.evaluate.await_args_list[0].args, ('document.body.innerText.slice(0, 2000)',))
        opened().write.assert_any_call('first characters')

    def test_screenshot_failure_does_not_block_text(self):
        page, opened, log = self.capture(TimeoutError())
        opened().write.assert_any_call('first characters')
        self.assertTrue(any(x.kwargs.get('etapa') == 'screenshot' for x in log.call_args_list))

    def test_text_failure_preserves_screenshot(self):
        page, opened, log = self.capture(text_error=TimeoutError())
        page.screenshot.assert_awaited_once()
        self.assertTrue(any(x.kwargs.get('fisier', '').endswith('.png') for x in log.call_args_list))

    def test_command_and_stderr_redacted_and_deduplicated(self):
        scope = {}
        exec(fixture(p.NEW_COMMAND), scope)
        obj = scope['Example']()
        obj.jurnal = Mock()
        result = types.SimpleNamespace(args=['pactl','load-module','module-null-sink','sink_name=wa_in_2','token=SECRET'], stderr='token=SECRET Module initialization failed', stdout='', returncode=1)
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                obj._eroare_sunet(types.SimpleNamespace(numar=2), 'wa_in_2', result)
        obj.jurnal.assert_called_once()
        event = obj.jurnal.call_args.args[0]
        self.assertEqual(event['comanda'][:4], result.args[:4])
        self.assertNotIn('SECRET', str(event))
        self.assertIn('Module initialization failed', event['eroare'])

    def test_unknown_argv_not_logged(self):
        scope = {}
        exec(fixture(p.NEW_COMMAND), scope)
        obj = scope['Example'](); obj.jurnal = Mock()
        with self.assertRaises(RuntimeError):
            obj._eroare_sunet(types.SimpleNamespace(numar=2), 'list sinks', types.SimpleNamespace(args='arbitrary secret shell',stderr='',stdout='',returncode=1))
        self.assertEqual(obj.jurnal.call_args.args[0]['comanda'], ['[UNAVAILABLE]'])

    def test_copy_only_compiles_and_refuses_repeat(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)/'source'; src.mkdir(); (src/'pod_locuri').mkdir()
            for name, old, new in p.PATCHES:
                (src/name).write_text(fixture(old))
            dest=Path(d)/'result'
            p.prepare(src,dest)
            for name, old, new in p.PATCHES:
                self.assertEqual((src/name).read_text(), fixture(old))
                self.assertEqual((dest/name).read_text(), fixture(new))
            with self.assertRaises(ValueError): p.prepare(src,dest)

    def test_drift_produces_no_destination(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source'; src.mkdir(); (src/'pod_locuri').mkdir()
            (src/'kelion_pod.py').write_text(fixture(p.OLD_CAPTURE))
            (src/'pod_locuri/executor_server.py').write_text('changed source')
            dest=Path(d)/'result'
            with self.assertRaises(ValueError): p.prepare(src,dest)
            self.assertFalse(dest.exists())

    def test_duplicate_method_rejected(self):
        with self.assertRaises(ValueError): p.transform(p.OLD_CAPTURE*2,p.OLD_CAPTURE,p.NEW_CAPTURE)


if __name__ == '__main__': unittest.main()

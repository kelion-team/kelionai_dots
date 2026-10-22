"""Offline acceptance: temporary CDP failure must not tear down call slots."""
import io
import json
import unittest
from unittest import mock

from pod_locuri.executor_server import ExecutorServer
from pod_locuri.locuri import Manager, descrie_loc, PORNIRE, OCUPAT, LOGIN_NECESAR
from pod_locuri.resurse import Capacitate


class CdpRecoveryTests(unittest.TestCase):
    def setup_manager(self):
        ex = ExecutorServer()
        for name in ('porneste', 'opreste', 'alerta', 'jurnal'):
            setattr(ex, name, mock.Mock())
        ex.procese[2] = mock.Mock()
        ex.procese[2].poll.return_value = None
        manager = Manager(ex, citeste_resurse=lambda *a: Capacitate(
            12000, 9000, 6, 0.3, 2, 2, 2, 'RAM'))
        active, waiting = descrie_loc(1), descrie_loc(2)
        active.stare, active.apel = OCUPAT, 'existing-call'
        waiting.stare = PORNIRE
        manager.locuri = {1: active, 2: waiting}
        return ex, manager, active, waiting

    def test_transient_failure_recovers_without_restart_or_touching_other_call(self):
        for failure in (OSError('CDP starting'), TimeoutError('CDP timeout'),
                        ValueError('invalid JSON')):
            with self.subTest(failure=type(failure).__name__):
                ex, manager, active, waiting = self.setup_manager()
                page = io.BytesIO(json.dumps([
                    {'type': 'page', 'url': 'https://chatgpt.com/dots/home'}
                ]).encode())
                with mock.patch('pod_locuri.executor_server.urllib.request.urlopen',
                                side_effect=[failure, page]):
                    manager.sincronizeaza()
                    self.assertEqual(waiting.stare, PORNIRE)
                    self.assertIs(manager.aloca('new-call'), waiting)
                self.assertEqual((waiting.stare, waiting.apel), (OCUPAT, 'new-call'))
                self.assertEqual((active.stare, active.apel), (OCUPAT, 'existing-call'))
                ex.opreste.assert_not_called()
                ex.porneste.assert_not_called()
                ex.alerta.assert_not_called()

    def test_actual_login_page_still_requires_login(self):
        ex, manager, active, waiting = self.setup_manager()
        page = io.BytesIO(b'[{"type":"page","url":"https://chatgpt.com/auth/login"}]')
        with mock.patch('pod_locuri.executor_server.urllib.request.urlopen', return_value=page):
            manager.sincronizeaza()
        self.assertEqual(waiting.stare, LOGIN_NECESAR)
        ex.opreste.assert_called_once_with(waiting)
        ex.porneste.assert_called_once_with(waiting, login=True)
        self.assertEqual((active.stare, active.apel), (OCUPAT, 'existing-call'))

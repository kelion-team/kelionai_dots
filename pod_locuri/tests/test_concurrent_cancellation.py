"""Finite, deterministic races through the public allocation/release API."""
import threading
import unittest
from unittest import mock

from pod_locuri.locuri import Manager, descrie_loc, PORNIRE, PREGATIT, OCUPAT
from pod_locuri.resurse import Capacitate


class Executor:
    def __init__(self):
        self.ready = False

    def pregatit(self, loc):
        return PREGATIT if self.ready else PORNIRE

    def jurnal(self, event):
        pass

    def alerta(self, text):
        raise AssertionError('unexpected capacity alert')

    def porneste(self, loc, login=False):
        raise AssertionError('no new slot is needed')

    def opreste(self, loc):
        raise AssertionError('occupied slots must not be stopped')


class CancellationTests(unittest.TestCase):
    def test_new_duplicate_cannot_clear_cancellation_while_first_waits(self):
        executor = Executor()
        manager = Manager(executor, citeste_resurse=lambda *a: Capacitate(
            12000, 9000, 6, 0.3, 1, 1, 1, 'RAM'))
        waiting = descrie_loc(1)
        waiting.stare = PORNIRE
        manager.locuri = {1: waiting}
        duplicate = []

        def during_wait(_):
            manager.elibereaza('ended')
            executor.ready = True
            duplicate.append(manager.aloca('ended', asteapta_s=0))

        manager._dormi = during_wait
        self.assertIsNone(manager.aloca('ended', asteapta_s=10))
        self.assertEqual(duplicate, [None])
        self.assertIsNone(waiting.apel)
        # Once all old attempts have returned, no stale cancellation survives.
        self.assertIs(manager.aloca('ended', asteapta_s=1), waiting)

    def test_failed_attempt_does_not_leave_stale_cancellation(self):
        executor = Executor()
        manager = Manager(executor, citeste_resurse=lambda *a: Capacitate(
            12000, 9000, 6, 0.3, 1, 1, 1, 'RAM'))
        waiting = descrie_loc(1)
        waiting.stare = PORNIRE
        manager.locuri = {1: waiting}

        def failed_probe(loc):
            manager.elibereaza('retry')
            raise RuntimeError('probe failed')

        with mock.patch.object(executor, 'pregatit', side_effect=failed_probe):
            with self.assertRaisesRegex(RuntimeError, 'probe failed'):
                manager.aloca('retry', asteapta_s=1)
        executor.ready = True
        self.assertIs(manager.aloca('retry', asteapta_s=1), waiting)

    def test_all_duplicate_waiters_observe_termination(self):
        executor = Executor()
        asleep = [threading.Event(), threading.Event()]
        wake = [threading.Event(), threading.Event()]
        results, errors = {}, []

        def sleep(_):
            index = int(threading.current_thread().name)
            asleep[index].set()
            if not wake[index].wait(3):
                raise AssertionError('test did not release waiter')

        manager = Manager(executor, dormi=sleep, citeste_resurse=lambda *a: Capacitate(
            12000, 9000, 6, 0.3, 2, 2, 2, 'RAM'))
        active, waiting = descrie_loc(1), descrie_loc(2)
        active.stare, active.apel = OCUPAT, 'other-call'
        waiting.stare = PORNIRE
        manager.locuri = {1: active, 2: waiting}

        def allocate(index):
            try:
                results[index] = manager.aloca('terminated-call', asteapta_s=10)
            except BaseException as error:
                errors.append(error)

        threads = [threading.Thread(target=allocate, args=(i,), name=str(i)) for i in range(2)]
        try:
            for i, thread in enumerate(threads):
                thread.start()
                self.assertTrue(asleep[i].wait(3), 'allocation did not reach wait')
            manager.elibereaza('terminated-call')
            wake[0].set()
            threads[0].join(3)
            self.assertFalse(threads[0].is_alive())
            executor.ready = True
            wake[1].set()
            threads[1].join(3)
            self.assertFalse(threads[1].is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(results, {0: None, 1: None})
            self.assertIsNone(waiting.apel)
            self.assertNotEqual(waiting.stare, OCUPAT)
            self.assertEqual((active.stare, active.apel), (OCUPAT, 'other-call'))
            # Cancellation of the old in-flight attempts must not poison a new call.
            self.assertIs(manager.aloca('new-call', asteapta_s=1), waiting)
        finally:
            for event in wake:
                event.set()
            for thread in threads:
                if thread.ident is not None:
                    thread.join(3)

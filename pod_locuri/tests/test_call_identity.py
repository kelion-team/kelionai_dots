"""A missing call identity must never alias the unused-slot sentinel."""
import unittest
from pod_locuri.locuri import Manager, OCUPAT, PREGATIT
from pod_locuri.tests.test_locuri import FakeExec, resurse_fixe


class CallIdentityTests(unittest.TestCase):
    def setUp(self):
        self.executor = FakeExec()
        _, resources = resurse_fixe(2)
        self.manager = Manager(self.executor, citeste_resurse=resources)
        self.manager.sincronizeaza()

    def test_invalid_allocation_does_not_return_or_mutate_any_slot(self):
        for value in (None, '', ' \t\n', False, 0, [], {}):
            with self.subTest(value=value):
                before = self.manager.stare()
                events = list(self.executor.ev)
                with self.assertRaises(ValueError):
                    self.manager.aloca(value, asteapta_s=0)
                self.assertEqual(self.manager.stare(), before)
                self.assertEqual(self.executor.ev, events)
        valid = self.manager.aloca('valid', asteapta_s=0)
        self.assertEqual((valid.stare, valid.apel), (OCUPAT, 'valid'))

    def test_invalid_release_cannot_touch_free_or_active_slots(self):
        active = self.manager.aloca('active', asteapta_s=0)
        for value in (None, '', ' \t\n', False, 0, [], {}):
            with self.subTest(value=value):
                before = self.manager.stare()
                events = list(self.executor.ev)
                with self.assertRaises(ValueError):
                    self.manager.elibereaza(value)
                self.assertEqual(self.manager.stare(), before)
                self.assertEqual(self.executor.ev, events)
        self.assertEqual((active.stare, active.apel), (OCUPAT, 'active'))
        self.assertEqual(sum(l.stare == PREGATIT for l in self.manager.locuri.values()), 1)

    def test_nonblank_identity_is_not_normalized_or_rewritten(self):
        first = self.manager.aloca('call', asteapta_s=0)
        second = self.manager.aloca(' call ', asteapta_s=0)
        self.assertIsNot(first, second)
        self.assertEqual(second.apel, ' call ')
        self.assertIs(self.manager.aloca('call', asteapta_s=0), first)

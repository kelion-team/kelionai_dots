import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kelion_brain import decide, preflight
import bridge

class BrainTests(unittest.TestCase):
    def setUp(self):
        self.envelope = bridge.prepare('task-1234', 'work', 'agt_TEST', 'agtch_TEST', 'Extrage numele', None)
        self.assessment = {'agent_id': 'agt_TEST', 'task_id': 'task-1234', 'task_input': 'Extrage numele', 'difficulty': 1, 'reason': 'Simple extraction'}
        self.manifest = {'schema_version': 1, 'models': [
            {'id': 'economic', 'surface': 'agent', 'agent_id': 'agt_TEST', 'capability_tier': 1, 'enabled': True, 'verified': True, 'billing_mode': 'included', 'cost_rank': 1, 'reasoning_levels': ['low']},
            {'id': 'advanced', 'surface': 'agent', 'agent_id': 'agt_TEST', 'capability_tier': 4, 'enabled': True, 'verified': True, 'billing_mode': 'included', 'cost_rank': 3, 'reasoning_levels': ['low', 'medium', 'high']}],
            'execution_bindings': [{'agent_id': 'agt_TEST', 'api_trigger_id': 'agtch_TEST', 'verified': True, 'model_id': 'economic', 'reasoning': 'low', 'usage_cost_verified': True, 'estimated_max_credits': 1, 'remaining_authorized_credits': 2}]}

    def test_adapts_to_dots_difficulty(self):
        self.assertEqual(decide(self.envelope, self.assessment, self.manifest)['host_model']['id'], 'economic')
        self.assessment['difficulty'] = 3
        chosen = decide(self.envelope, self.assessment, self.manifest)['host_model']
        self.assertEqual((chosen['id'], chosen['reasoning']), ('advanced', 'high'))

    def test_no_model_applied_no_dispatch(self):
        self.assessment['difficulty'] = 3
        with self.assertRaisesRegex(ValueError, 'not applied'):
            preflight(self.envelope, self.assessment, self.manifest)

    def test_other_dot_is_not_eligible(self):
        self.manifest['models'][0]['agent_id'] = 'agt_OTHER'
        self.assertEqual(decide(self.envelope, self.assessment, self.manifest)['host_model']['id'], 'advanced')

    def test_assessment_bound_to_exact_task(self):
        self.assessment['task_input'] = 'Different task'
        with self.assertRaises(ValueError):
            decide(self.envelope, self.assessment, self.manifest)

    def test_no_unverified_or_exceeded_budget(self):
        binding = self.manifest['execution_bindings'][0]
        for change in [{'usage_cost_verified': False}, {'remaining_authorized_credits': 0}, {'estimated_max_credits': float('nan')}]:
            original = dict(binding)
            binding.update(change)
            with self.assertRaises(ValueError):
                preflight(self.envelope, self.assessment, self.manifest)
            binding.clear()
            binding.update(original)

    def test_validated_binding(self):
        self.assertEqual(preflight(self.envelope, self.assessment, self.manifest)['status'], 'execution_binding_verified')

    def test_cli_blocks_before_api(self):
        import tempfile, json
        with tempfile.TemporaryDirectory() as directory:
            files = []
            for name, value in [('envelope', self.envelope), ('assessment', self.assessment), ('manifest', self.manifest)]:
                path = Path(directory) / (name + '.json')
                if name == 'manifest':
                    value = dict(value, execution_bindings=[])
                path.write_text(json.dumps(value))
                files.append(str(path))
            with patch.object(bridge, '_trigger_transport') as send:
                rc = bridge.main(['trigger', '--execute', '--envelope', files[0], '--dots-assessment', files[1], '--cost-manifest', files[2], '--out', str(Path(directory)/'out.json')])
                self.assertEqual(rc, 2)
                send.assert_not_called()

    def test_public_trigger_requires_kelion_decision(self):
        with patch.object(bridge, '_trigger_transport') as send:
            with self.assertRaises(ValueError):
                bridge.trigger(self.envelope, 'FAKE_TOKEN')
            send.assert_not_called()

    def test_public_trigger_records_decision(self):
        with patch.object(bridge, '_trigger_transport', return_value={'status': 'trigger_accepted'}) as send:
            receipt = bridge.trigger(self.envelope, 'FAKE_TOKEN', assessment=self.assessment, manifest=self.manifest)
            self.assertEqual(receipt['kelion_decision']['host_model']['id'], 'economic')
            self.assertEqual(send.call_count, 1)

if __name__ == '__main__':
    unittest.main()

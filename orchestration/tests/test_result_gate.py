import copy
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import result_gate

class GateTests(unittest.TestCase):
    def setUp(self):
        self.inp = b'original user input'
        self.out = b'result from agent'
        self.receipt = {'task_id':'kelion-0001','agent_id':'agt_abc','agent_trigger_run_id':'apirun_xyz','agent_run_status':'completed','status':'run_completed_result_not_retrieved','input_sha256':result_gate.digest(self.inp)}
        self.result = {'task_id':'kelion-0001','agent_id':'agt_abc','agent_trigger_run_id':'apirun_xyz','input_sha256':result_gate.digest(self.inp),'result_sha256':result_gate.digest(self.out),'result_ref':'https://github.com/a/b/issues/4#issuecomment-123'}
        self.verifier = {'task_id':'kelion-0001','agent_id':'agt_abc','agent_trigger_run_id':'apirun_xyz','input_sha256':result_gate.digest(self.inp),'result_sha256':result_gate.digest(self.out),'verifier':'agt_independent','passed':True,'evidence_ref':'https://github.com/a/b/actions/runs/42'}
    def evaluate(self):
        return result_gate.evaluate(self.receipt,self.result,self.inp,self.out,self.verifier)
    def test_missing_dispatch_binding_is_rejected(self):
        self.receipt.pop('input_sha256')
        with self.assertRaisesRegex(ValueError, 'original dispatch'):
            self.evaluate()

    def test_consistent_substituted_input_is_rejected(self):
        self.inp = b'substituted request'
        self.result['input_sha256'] = result_gate.digest(self.inp)
        self.verifier['input_sha256'] = result_gate.digest(self.inp)
        with self.assertRaisesRegex(ValueError, 'dispatch input_sha256'):
            self.evaluate()

    def test_positive_is_not_claimed_authenticated(self):
        r=self.evaluate()
        self.assertTrue(r['integrity_checks_passed'])
        self.assertFalse(r['fully_verified'])
        self.assertFalse(r['provenance_authenticated'])

    def test_official_202_no_run_id_integrity_only(self):
        self.receipt.pop('agent_trigger_run_id')
        self.receipt.pop('agent_run_status')
        self.receipt['status'] = 'trigger_accepted'
        self.result.pop('agent_trigger_run_id')
        self.verifier.pop('agent_trigger_run_id')
        out = self.evaluate()
        self.assertIsNone(out['run_id'])
        self.assertTrue(out['integrity_checks_passed'])
        self.assertFalse(out['fully_verified'])
        self.assertFalse(out['provenance_authenticated'])

    def test_unreceipted_run_id_is_rejected(self):
        self.receipt.pop('agent_trigger_run_id')
        self.receipt.pop('agent_run_status')
        self.receipt['status'] = 'trigger_accepted'
        with self.assertRaisesRegex(ValueError, 'Unexpected agent_trigger_run_id'):
            self.evaluate()

    def test_wrong_output_blocked(self):
        self.out=b'tampered'
        with self.assertRaisesRegex(ValueError,'result_sha256'):
            self.evaluate()
    def test_wrong_input_blocked(self):
        self.inp=b'tampered'
        with self.assertRaisesRegex(ValueError,'input_sha256'):
            self.evaluate()
    def test_spoofed_task_blocked(self):
        self.result['task_id']='other-task'
        with self.assertRaisesRegex(ValueError,'task_id'):
            self.evaluate()
    def test_spoofed_run_blocked(self):
        self.result['agent_trigger_run_id']='apirun_other'
        with self.assertRaisesRegex(ValueError,'agent_trigger_run_id'):
            self.evaluate()
    def test_wrong_verifier_hash_blocked(self):
        self.verifier['result_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'verification result sha'):
            self.evaluate()
    def test_same_agent_verifier_blocked(self):
        self.verifier['verifier']='agt_abc'
        with self.assertRaisesRegex(ValueError,'Verifier'):
            self.evaluate()
    def test_failed_verify_blocked(self):
        self.verifier['passed']=False
        with self.assertRaisesRegex(ValueError,'evidence'):
            self.evaluate()
    def test_nonterminal_run_blocked(self):
        self.receipt['agent_run_status']='in_progress'
        with self.assertRaisesRegex(ValueError,'completed'):
            self.evaluate()
    def test_no_output_blocked(self):
        self.out=b''
        with self.assertRaisesRegex(ValueError,'No output'):
            self.evaluate()
    def test_no_result_ref_blocked(self):
        self.result['result_ref']=''
        with self.assertRaisesRegex(ValueError,'reference'):
            self.evaluate()
    def test_no_verification_proof_blocked(self):
        self.verifier.pop('evidence_ref')
        with self.assertRaisesRegex(ValueError,'evidence'):
            self.evaluate()

if __name__=='__main__':
    unittest.main()

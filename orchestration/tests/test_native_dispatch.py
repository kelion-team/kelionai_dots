import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_dispatch import plan

class NativeTests(unittest.TestCase):
    def setUp(self):
        self.registry = {'roles': [{'role':'test','name':'dots_test','source_agent_id':'agt_TEST',
                                   'description':'Test specialist','requires_logic_validation':False}]}
        self.request = {'task_id':'native-test-1','task':'Count fields','role':'test','surface':'work'}
        self.assessment = {'task_id':'native-test-1','task_input':'Count fields','source_agent_id':'agt_TEST',
                           'difficulty':1,'reason':'Simple counting','risk_flags':[]}
        self.manifest = {'schema_version':1,'models':[
            {'id':'economic','surface':'work','enabled':True,'verified':True,'billing_mode':'included',
             'cost_rank':1,'capability_tier':1,'reasoning_levels':['low'],'native_spawn_supported':True},
            {'id':'advanced','surface':'work','enabled':True,'verified':True,'billing_mode':'included',
             'cost_rank':3,'capability_tier':4,'reasoning_levels':['low','medium','high'],'native_spawn_supported':True}]}

    def test_simple_assessment_not_overridden_by_uncertain_baseline(self):
        result=plan(self.request,self.assessment,self.manifest,self.registry)
        self.assertEqual(result['policy_tier'],1)
        self.assertEqual(result['spawn_request']['model'],'economic')
        self.assertEqual(result['spawn_request']['reasoning_effort'],'low')
        self.assertEqual(result['spawn_request']['fork_turns'],'none')

    def test_difficult_assessment_changes_spawn_model_and_effort(self):
        self.assessment['difficulty']=3
        result=plan(self.request,self.assessment,self.manifest,self.registry)
        self.assertEqual((result['spawn_request']['model'],result['spawn_request']['reasoning_effort']),('advanced','high'))

    def test_model_eligibility(self):
        self.manifest['models'][0]['billing_mode']='metered'
        self.assertEqual(plan(self.request,self.assessment,self.manifest,self.registry)['spawn_request']['model'],'advanced')
        self.manifest['models'][1]['verified']=False
        with self.assertRaises(ValueError): plan(self.request,self.assessment,self.manifest,self.registry)

    def test_plain_chat_not_claimed_native(self):
        self.request['surface']='chat'
        with self.assertRaises(ValueError): plan(self.request,self.assessment,self.manifest,self.registry)

    def test_task_identity_and_guard(self):
        self.assessment['task_id']='other'
        with self.assertRaises(ValueError): plan(self.request,self.assessment,self.manifest,self.registry)
        self.assessment['task_id']=self.request['task_id']
        self.registry['roles'][0]['requires_logic_validation']=True
        with self.assertRaises(ValueError): plan(self.request,self.assessment,self.manifest,self.registry)

    def test_native_supported_and_no_dispatch_claim(self):
        self.manifest['models'][0]['native_spawn_supported']=False
        with self.assertRaises(ValueError): plan(self.request,self.assessment,self.manifest,self.registry)
        self.manifest['models'][0]['native_spawn_supported']=True
        self.assertFalse(plan(self.request,self.assessment,self.manifest,self.registry)['dispatch_performed'])

    def test_real_profiles_do_not_override_kelion(self):
        import tomllib
        root=Path(__file__).resolve().parents[2]
        registry=json.loads((root/'orchestration/native_roles.json').read_text())
        names=[]
        for f in (root/'.codex/agents').glob('*.toml'):
            content=tomllib.loads(f.read_text())
            names.append(content['name'])
            self.assertNotIn('model',content)
            self.assertNotIn('model_reasoning_effort',content)
        self.assertEqual(set(names),{r['name'] for r in registry['roles']})
        self.assertEqual(len(names),len(registry['roles']))

if __name__=='__main__': unittest.main()

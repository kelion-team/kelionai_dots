import unittest
from channel_bridge.coordination import project


def c(mid='m', sender='kelion', recipient='openai', kind='msg', ref='-', task='task', text='body'):
    return {'id':mid, 'url':'https://github.com/kelion-team/kelionai_dots/issues/48#issuecomment-1',
            'user':{'login':'kelion-team'},
            'body':f'[KC] id={mid} from={sender} to={recipient} task={task} type={kind} ref={ref}\n{text}'}


class CoordinationTests(unittest.TestCase):
    def test_reverse_order_duplicate_and_ack_not_completion(self):
        msg=c(); ack=c('a','openai','kelion','ack','m')
        r=project([ack,msg,msg])
        self.assertEqual(len(r['messages']),1)
        self.assertEqual(r['messages'][0]['status'],'acknowledged_awaiting_result')
        self.assertFalse(r['fully_verified'])

    def test_wrong_task_and_sender_do_not_ack(self):
        r=project([c(),c('a','openai','kelion','ack','m',task='wrong'),c('b','kelion','openai','ack','m')])
        self.assertEqual(r['messages'][0]['status'],'unacknowledged')
        self.assertEqual(len(r['warnings']),2)

    def test_conflicting_duplicate_blocks(self):
        r=project([c(),c(text='changed'),c('a','openai','kelion','ack','m')])
        self.assertEqual(r['messages'][0]['status'],'blocked_id_conflict')

    def test_done_is_only_claim(self):
        r=project([c(),c('d','openai','kelion','done','m')])
        self.assertEqual(r['messages'][0]['status'],'result_claim_requires_readback')
        self.assertFalse(r['messages'][0]['verified'])

    def test_legacy_identity_preserved(self):
        r=project([c(recipient='claude'),c('a','openai','kelion','ack','m')])
        self.assertEqual(r['messages'][0]['recipient'],'claude')
        self.assertEqual(r['messages'][0]['status'],'unacknowledged')
        self.assertIn('migration',r['messages'][0])

    def test_malformed_header_and_missing_ref(self):
        r=project([{'id':1,'body':'[KC] invalid'}, c('a','openai','kelion','ack','missing')])
        self.assertEqual(len(r['warnings']),2)
        self.assertFalse(r['execution_started'])

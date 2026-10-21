import unittest
from channel_bridge.coordination import project


def c(mid='m', sender='kelion', recipient='claude', kind='msg', ref='-', task='task', text='body'):
    return {'id':{'m':1,'a':2,'b':3,'d':4}.get(mid,10), 'url':'https://github.com/kelion-team/kelionai_dots/issues/48#issuecomment-1',
            'user':{'login':'kelion-team'},
            'body':f'[KC] id={mid} from={sender} to={recipient} task={task} type={kind} ref={ref}\n{text}'}


class CoordinationTests(unittest.TestCase):
    def test_reverse_order_duplicate_and_ack_not_completion(self):
        msg=c(); ack=c('a','claude','kelion','ack','m')
        r=project([ack,msg,msg])
        self.assertEqual(len(r['messages']),1)
        self.assertEqual(r['messages'][0]['status'],'acknowledged_awaiting_result')
        self.assertFalse(r['fully_verified'])

    def test_wrong_task_and_sender_do_not_ack(self):
        r=project([c(),c('a','claude','kelion','ack','m',task='wrong'),c('b','kelion','claude','ack','m')])
        self.assertEqual(r['messages'][0]['status'],'unacknowledged')
        self.assertEqual(len(r['warnings']),2)

    def test_conflicting_duplicate_blocks(self):
        r=project([c(),c(text='changed'),c('a','claude','kelion','ack','m')])
        self.assertEqual(r['messages'][0]['status'],'blocked_id_conflict')

    def test_done_is_only_claim(self):
        r=project([c(),c('d','claude','kelion','done','m')])
        self.assertEqual(r['messages'][0]['status'],'result_claim_requires_readback')
        self.assertFalse(r['messages'][0]['verified'])

    def test_legacy_identity_preserved(self):
        ack=c('a','claude','kelion','ack','m')
        ack['body']=ack['body'].replace('from=claude','from=openai')
        r=project([c(recipient='claude'),ack])
        self.assertEqual(r['messages'][0]['recipient'],'claude')
        self.assertEqual(r['messages'][0]['status'],'unacknowledged')
        self.assertIn('migration',r['messages'][0])

    def test_malformed_header_and_missing_ref(self):
        r=project([{'id':1,'body':'[KC] invalid'}, c('a','claude','kelion','ack','missing')])
        self.assertEqual(len(r['warnings']),2)
        self.assertFalse(r['execution_started'])


class EvidenceTests(unittest.TestCase):
    def test_reply_evidence_retained(self):
        reply=c('d','claude','kelion','done','m',text='commit abc SHA256 xyz tests OK')
        report=project([c(),reply])
        record=next(r for r in report['records'] if r['id']=='d')
        self.assertEqual(record['body'],reply['body'])
        self.assertEqual(record['comment_url'],reply['url'])
        self.assertEqual(record['github_author'],'kelion-team')
        self.assertEqual(len(record['sha256']),64)
        self.assertFalse(record['provenance_authenticated'])

    def test_older_response_cannot_ack_new_message(self):
        msg=c(); msg['id']=20
        ack=c('a','claude','kelion','ack','m'); ack['id']=10
        r=project([msg,ack])
        self.assertEqual(r['messages'][0]['status'],'unacknowledged')
        self.assertEqual(r['warnings'][0]['reason'],'response_predates_parent')

    def test_missing_immutable_order_is_rejected(self):
        msg=c(); msg['id']=None
        r=project([msg])
        self.assertEqual(r['messages'],[])
        self.assertEqual(r['warnings'][0]['reason'],'invalid_comment_order_metadata')

    def test_duplicate_order_is_deterministic(self):
        msg=c(); later=dict(msg,id=50)
        ack=c('a','claude','kelion','ack','m')
        for snapshot in ([later,ack,msg],[msg,ack,later]):
            r=project(snapshot)
            self.assertEqual(r['messages'][0]['status'],'acknowledged_awaiting_result')

import copy
import unittest
from unittest.mock import Mock, patch

import test_shopee_continuous_queue as fixtures
from core.shopee_posting.product_attachment import ProductUnavailable
from core.shopee_posting.device import ReviewRequired
from core.shopee_posting.restart import restartable
from core.shopee_posting.workflow import restart_before_first_post


class ProductSkipTests(unittest.TestCase):
    def setUp(self):
        self.h=fixtures.ContinuousQueueTests();self.h.setUp();self.addCleanup(self.h.doCleanups)
        self.skipped_closed=[]
        original=self.h.device.adb.shell.side_effect
        def close(*args,**kw):
            state=self.h.store.read();row=next(r for r in state['items'] if r['id']==state['posting_run']['current_id'])
            if row['phase']=='skipped':
                self.assertFalse(row.get('publish_intent'));self.skipped_closed.append(row['id']);self.h.app_closed=True
                return Mock(returncode=0)
            return original(*args,**kw)
        self.h.device.adb.shell.side_effect=close
        old_snapshot=self.h.device.snapshot.side_effect
        def snapshot():
            state=self.h.store.read();current=state.get('posting_run',{}).get('current_id')
            row=next((r for r in state['items'] if r['id']==current),{})
            if row.get('phase')=='skipped':
                return '<hierarchy/>',[{'package':'com.shopee.th','text':'กรอกลิงก์สินค้า'}]
            return old_snapshot()
        self.h.device.snapshot.side_effect=snapshot

    def test_skip_first_then_publish_remaining_without_empty_product_post(self):
        h=self.h;rid=h.begin()
        with h.fixtures(),patch('core.shopee_posting.workflow.add_product',side_effect=[ProductUnavailable('empty after retries'),'Product','Product']):
            h.service._post(h.ids,'owner',rid)
        state=h.service.state();run=state['posting_run']
        self.assertEqual(h.public,h.ids[1:]);self.assertEqual(self.skipped_closed,h.ids[:1])
        self.assertEqual([r['phase'] for r in state['items']],['skipped','published','published'])
        self.assertEqual((run['status'],run['completed'],run['skipped_count'],run['remaining']),('complete',2,1,0))
        self.assertNotIn('publish_intent',state['items'][0]);self.assertNotIn(h.ids[0],state['restartable_ids'])

    def test_all_skipped_is_finished_not_published(self):
        h=self.h;rid=h.begin()
        with h.fixtures(),patch('core.shopee_posting.workflow.add_product',side_effect=ProductUnavailable('excluded')):
            h.service._post(h.ids,'owner',rid)
        run=h.service.state()['posting_run']
        self.assertEqual((run['status'],run['completed'],run['skipped_count']),('complete',0,3))
        self.assertEqual(h.public,[]);self.assertEqual(self.skipped_closed,h.ids[:2])

    def test_unknown_import_still_stops_not_skipped(self):
        h=self.h;rid=h.begin()
        with h.fixtures(),patch('core.shopee_posting.workflow.add_product',side_effect=ReviewRequired('unknown screen')):
            h.service._post(h.ids,'owner',rid)
        self.assertEqual([r['phase'] for r in h.store.read()['items']],['review','draft','draft'])
        self.assertFalse(h.public);self.assertFalse(self.skipped_closed)

    def test_old_contract_does_not_implicitly_skip(self):
        h=self.h;rid=h.begin();h.store.change(lambda s:[r['run_contract'].pop('skip_unavailable_products') for r in s['items']])
        with h.fixtures(),patch('core.shopee_posting.workflow.add_product',side_effect=ProductUnavailable('empty')):
            h.service._post(h.ids,'owner',rid)
        self.assertEqual(h.service.state()['posting_run']['status'],'review');self.assertFalse(h.public)

    def test_idle_confirmed_skip_is_reversible_only_by_explicit_edit(self):
        h=self.h;s=h.store.read();i=h.ids[0]
        h.service.action('shopee_post_skip_unavailable',{'id':i,'revision':s['revision'],'confirm':True})
        row=h.store.read()['items'][0];self.assertEqual(row['phase'],'skipped');self.assertFalse(restartable(row))
        h.store.recover();self.assertEqual(h.store.read()['items'][0]['phase'],'skipped')
        h.store.edit(i,row['revision'],product_url='https://s.shopee.co.th/new')
        row=h.store.read()['items'][0];self.assertEqual(row['phase'],'draft');self.assertNotIn('skip_reason',row)
        self.assertTrue(row['skip_history']);self.assertTrue(restartable(row))

    def test_skip_rejects_busy_stale_revision_and_sent(self):
        h=self.h;s=h.store.read();i=h.ids[0]
        for payload in ({'id':i,'revision':s['revision'],'confirm':False},{'id':i,'revision':-1,'confirm':True}):
            with self.assertRaises(ValueError):h.service.action('shopee_post_skip_unavailable',payload)
        self.assertEqual(h.store.read(),s)
        h.store.transition(i,{'draft'},'review',publish_intent={'id':'unknown'})
        with self.assertRaises(ValueError):h.service.action('shopee_post_skip_unavailable',{'id':i,'revision':h.store.read()['revision'],'confirm':True})
        h.service._busy=True
        with self.assertRaises(ValueError):h.service.action('shopee_post_skip_unavailable',{'id':h.ids[1],'revision':h.store.read()['revision'],'confirm':True})

    def test_active_skip_requires_current_product_stage(self):
        h=self.h;rid=h.begin();before=copy.deepcopy(h.store.read())
        with self.assertRaises(ValueError):h.store.skip_product(h.ids[0],'excluded',run_id=rid)
        self.assertEqual(h.store.read(),before)

    def test_skip_close_requires_frozen_policy_and_current_owned_row(self):
        h=self.h;rid=h.begin();i=h.ids[0]
        h.store.transition(i,{'queued'},'editing');h.store.progress(i,'product','import')
        h.store.skip_product(i,'excluded',run_id=rid)
        h.store.change(lambda s:s['items'][0]['run_contract'].pop('skip_unavailable_products'))
        with self.assertRaises(ReviewRequired):restart_before_first_post(h.device,h.store,i,'owner',rid,after_skip=True)
        self.assertFalse(self.skipped_closed)


if __name__=='__main__':unittest.main()

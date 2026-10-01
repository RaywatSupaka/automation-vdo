import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

from core.shopee_posting import product_attachment as a
from core.shopee_posting.device import ReviewRequired

URL='https://s.shopee.co.th/test'
PACKAGE='com.shopee.th'
TITLE='สินค้าอ้างอิงสำหรับทดสอบ'


def page(kind='empty', editor=URL, selected=False, commission=True, ordinal=False, busy=False, count=1):
    root=ET.Element('hierarchy')
    def node(parent, text='', bounds='[0,0][400,40]', cls='android.widget.TextView', **extra):
        return ET.SubElement(parent,'node',{'text':text,'package':PACKAGE,'enabled':'true',
                   'visible-to-user':'true','class':cls,'bounds':bounds,**extra})
    node(root,'กรอกลิงก์สินค้า')
    node(root,editor,'[0,50][400,100]',cls='android.widget.EditText')
    node(root,'นำเข้า','[0,110][400,140]')
    node(root,'รายการสินค้า','[0,150][400,180]')
    if kind=='empty':node(root,'ไม่มีสินค้า','[0,200][400,240]')
    if kind=='invalid':node(root,'ลิงก์ไม่ถูกต้อง','[0,200][400,240]')
    if kind=='product':
        for index in range(count):
            y=200+index*160
            card=node(root,bounds=f'[0,{y}][400,{y+150}]',cls='android.view.ViewGroup')
            if ordinal:node(card,'1',f'[0,{y}][20,{y+20}]')
            node(card,TITLE+('อื่น' if index else ''),f'[30,{y}][400,{y+40}]')
            if commission:node(card,'ค่าคอมสูงสุด 12%',f'[30,{y+45}][400,{y+75}]')
            node(card,'฿499',f'[30,{y+90}][400,{y+120}]')
    if busy:node(root,bounds='[0,800][50,850]',cls='android.widget.ProgressBar')
    node(root,'เลือกทั้งหมด','[0,900][200,950]')
    node(root,'เพิ่ม(1)' if selected else 'เพิ่ม','[200,900][400,950]')
    xml=ET.tostring(root,encoding='unicode')
    return xml,[dict(n.attrib) for n in root.iter('node')]


def composer(title=TITLE, caption='owned'):
    return '',[{'package':PACKAGE,'resource-id':a.P+'tv_product_title','text':title},
               {'package':PACKAGE,'resource-id':a.P+'et_caption','text':caption}]


class ProductRead(unittest.TestCase):
    def test_commission_optional_and_ordinal_not_title(self):
        for commission in (False,True):
            for ordinal in (False,True):
                with self.subTest(commission=commission,ordinal=ordinal):
                    p=a.inspect_import(page('product',commission=commission,ordinal=ordinal)[0])
                    self.assertEqual((p['state'],p['product']),('product',TITLE))

    def test_two_products_not_single(self):
        self.assertEqual(a.inspect_import(page('product',count=2)[0])['state'],'ambiguous')

    def test_foreign_and_search_pages_not_import(self):
        xml=page('product')[0]
        for bad in (xml.replace(PACKAGE,'foreign'),xml.replace('กรอกลิงก์สินค้า','เพิ่มสินค้า')):
            self.assertEqual(a.inspect_import(bad)['state'],'unknown')

    def test_empty_invalid_and_busy_distinct(self):
        self.assertEqual(a.inspect_import(page('empty')[0])['state'],'empty')
        self.assertEqual(a.inspect_import(page('invalid')[0])['state'],'invalid')
        self.assertTrue(a.inspect_import(page('empty',busy=True)[0])['busy'])

    def test_stable_product_requires_two_observations(self):
        d=Mock();d.snapshot.return_value=page('product',commission=False)
        with patch.object(a.time,'sleep'):
            self.assertEqual(a.wait_import(d)['product'],TITLE)
        self.assertEqual(d.snapshot.call_count,2)

    def test_expired_loading_cannot_authorize_reimport(self):
        for kind,busy in [('empty',True),('unknown',False)]:
            d=Mock();d.snapshot.return_value=page(kind,busy=busy)
            with patch.object(a.time,'monotonic',side_effect=[0,0,1,2,40]),patch.object(a.time,'sleep'),self.assertRaises(ReviewRequired):
                a.wait_import(d)

    def test_stable_empty_only_after_deadline(self):
        d=Mock();d.snapshot.return_value=page('empty')
        with patch.object(a.time,'monotonic',side_effect=[0,0,1,2,40]),patch.object(a.time,'sleep'):
            self.assertEqual(a.wait_import(d)['state'],'empty')
        self.assertEqual(d.snapshot.call_count,3)

    def test_import_refocus_hides_keyboard_then_reads_existing_result(self):
        xml,nodes=page('unknown');nodes.append({'resource-id':'android:id/input_method_nav_back'})
        d=Mock(package=PACKAGE);d.snapshot.side_effect=[(xml,nodes),page('product'),page('product')]
        with patch.object(a.time,'sleep'):
            self.assertEqual(a.wait_import(d)['product'],TITLE)
        d.hide_keyboard.assert_called_once();d.tap.assert_not_called()

    def test_keyboard_on_another_page_never_goes_back(self):
        d=Mock(package=PACKAGE);d.snapshot.return_value=('<hierarchy/>',[{'resource-id':'android:id/input_method_nav_back'}])
        with patch.object(a.time,'monotonic',side_effect=[0,0,1,40]),patch.object(a.time,'sleep'),self.assertRaises(ReviewRequired):a.wait_import(d)
        d.hide_keyboard.assert_not_called()

    def test_keyboard_reopens_no_repeated_back(self):
        xml,nodes=page('unknown');nodes.append({'resource-id':'android:id/input_method_nav_back'})
        d=Mock(package=PACKAGE);d.snapshot.return_value=(xml,nodes)
        with patch.object(a.time,'monotonic',side_effect=[0,0,1,2,40]),patch.object(a.time,'sleep'),self.assertRaises(ReviewRequired):a.wait_import(d)
        d.hide_keyboard.assert_called_once()


class ImportRetry(unittest.TestCase):
    def test_empty_then_same_link_retry_succeeds(self):
        d=Mock();d.snapshot.return_value=page('empty')
        p=a.inspect_import(page('product')[0]);empty=a.inspect_import(page('empty')[0])
        progress=Mock()
        with patch.object(a,'wait_import',side_effect=[empty,p]):
            self.assertEqual(a.import_product(d,URL,progress),p)
        self.assertEqual(d.tap.call_count,2)
        self.assertEqual([c.args[0] for c in d.set_text.call_args_list],[URL,URL])
        self.assertTrue(all(c.kwargs=={'text':'นำเข้า'} for c in d.tap.call_args_list))

    def test_three_attempt_budget_not_endless(self):
        d=Mock();d.snapshot.return_value=page('empty')
        with patch.object(a,'wait_import',return_value=a.inspect_import(page('empty')[0])),self.assertRaisesRegex(ReviewRequired,'3 รอบ'):
            a.import_product(d,URL)
        self.assertEqual(d.tap.call_count,3)

    def test_late_result_consumed_before_retry(self):
        d=Mock();d.snapshot.side_effect=[page(),page(),page('product')]
        p=a.inspect_import(page('product')[0]);empty=a.inspect_import(page()[0])
        with patch.object(a,'wait_import',side_effect=[empty,p]):
            self.assertEqual(a.import_product(d,URL),p)
        self.assertEqual(d.tap.call_count,1)

    def test_existing_card_or_foreign_link_never_overwritten(self):
        for snapshot in (page('product'),page(editor='https://s.shopee.co.th/other'),page(busy=True)):
            d=Mock();d.snapshot.return_value=snapshot
            with self.assertRaises(ReviewRequired):a.import_product(d,URL)
            d.set_text.assert_not_called();d.tap.assert_not_called()

    def test_lost_import_ack_reads_success_no_second_click(self):
        d=Mock();d.snapshot.return_value=page();d.tap.side_effect=ReviewRequired('lost ACK')
        with patch.object(a,'wait_import',return_value=a.inspect_import(page('product')[0])):
            self.assertEqual(a.import_product(d,URL)['product'],TITLE)
        d.tap.assert_called_once_with(text='นำเข้า')

    def test_cancel_does_not_retry(self):
        d=Mock();d.snapshot.return_value=page();d.tap.side_effect=ReviewRequired('pause');d.verify.side_effect=ReviewRequired('pause')
        with self.assertRaises(ReviewRequired):a.import_product(d,URL)
        self.assertEqual(d.tap.call_count,1)


class AttachRetry(unittest.TestCase):
    def test_attach_success(self):
        d=Mock(package=PACKAGE);d.snapshot.side_effect=[page('product'),page('product',selected=True),composer()]
        self.assertEqual(a.attach_imported(d,{'product':TITLE},'owned'),TITLE)
        self.assertEqual([c.kwargs for c in d.tap.call_args_list],[{'text':'เลือกทั้งหมด'},{'text':'เพิ่ม(1)'}])

    def test_selected_card_no_toggle_and_lost_ack_success(self):
        d=Mock(package=PACKAGE);d.snapshot.side_effect=[page('product',selected=True),composer()];d.tap.side_effect=ReviewRequired('lost ACK')
        self.assertEqual(a.attach_imported(d,{'product':TITLE},'owned'),TITLE)
        d.tap.assert_called_once_with(text='เพิ่ม(1)')

    def test_unchanged_selected_card_one_add_retry(self):
        d=Mock(package=PACKAGE);selected=page('product',selected=True)
        d.snapshot.side_effect=[selected,selected,selected,selected,composer()]
        with patch.object(a.time,'monotonic',side_effect=[0,0,1,21,22,22]),patch.object(a.time,'sleep'):
            self.assertEqual(a.attach_imported(d,{'product':TITLE},'owned'),TITLE)
        self.assertEqual([c.kwargs for c in d.tap.call_args_list],[{'text':'เพิ่ม(1)'},{'text':'เพิ่ม(1)'}])

    def test_wrong_caption_or_product_no_retry(self):
        for final in (composer(caption='changed'),composer(title='other')):
            d=Mock(package=PACKAGE);d.snapshot.side_effect=[page('product',selected=True),final]
            with self.assertRaises(ReviewRequired):a.attach_imported(d,{'product':TITLE},'owned')
            self.assertEqual(d.tap.call_count,1)

    def test_unknown_page_never_add_retry(self):
        d=Mock(package=PACKAGE);d.snapshot.side_effect=[page('product',selected=True),('',[]),('',[])]
        with patch.object(a.time,'monotonic',side_effect=[0,0,1,21]),patch.object(a.time,'sleep'),self.assertRaises(ReviewRequired):
            a.attach_imported(d,{'product':TITLE},'owned')
        self.assertEqual(d.tap.call_count,1)

    def test_product_changed_after_selection_never_adds(self):
        d=Mock(package=PACKAGE)
        d.snapshot.side_effect=[page('product'),page('product',selected=True,count=2)]
        with self.assertRaises(ReviewRequired):a.attach_imported(d,{'product':TITLE},'owned')
        d.tap.assert_called_once_with(text='เลือกทั้งหมด')

    def test_five_product_import_attach_simulation(self):
        # Local UI simulation only, explicitly NOT five actual Shopee publications.
        for number in range(5):
            d=Mock(package=PACKAGE)
            empty=page(editor='รองรับเฉพาะลิงก์สินค้าใน Shopee')
            product=page('product',commission=bool(number%2),ordinal=bool(number%3))
            selected=page('product',selected=True,commission=bool(number%2),ordinal=True)
            d.snapshot.side_effect=[empty,page(),product,product,product,selected,composer()]
            with patch.object(a.time,'sleep'):
                imported=a.import_product(d,URL)
                self.assertEqual(a.attach_imported(d,imported,'owned'),TITLE)
            self.assertEqual([c.kwargs for c in d.tap.call_args_list],
                             [{'text':'นำเข้า'},{'text':'เลือกทั้งหมด'},{'text':'เพิ่ม(1)'}])


if __name__=='__main__':unittest.main()

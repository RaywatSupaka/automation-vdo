"""Synthetic phone I/O for actual shared-observation and publisher tests."""
import xml.etree.ElementTree as ET
from unittest.mock import Mock

from PIL import Image, ImageDraw
from core.shopee_posting.device import ShopeeDevice
from core.shopee_posting.settings import P, CONTROLS, RESOURCES


def ready_device(caption='new caption 0', identity='phone', product='Product'):
    d = ShopeeDevice.__new__(ShopeeDevice)
    d.identity = identity; d.stop = None
    d.adb = Mock(); d.adb.prop.return_value = identity
    d.adb.shell.return_value = Mock(returncode=0)
    d.ui = Mock()
    d.ui.info = dict(currentPackageName=d.package, screenOn=True, displayWidth=400, displayHeight=800)
    def node(resource, text='', bounds='[10,10][300,40]'):
        return dict(package=d.package, enabled='true', **{
            'resource-id': P+resource, 'text': text, 'bounds': bounds, 'visible-to-user':'true'})
    d.fixture_nodes = [node('et_caption', caption), node('tv_product_title', product),
                       node('btn_post', 'โพสต์', '[10,700][390,760]')]
    for _, label, text in CONTROLS.values():
        d.fixture_nodes.append(node(label, text))
    for index, resource in enumerate(RESOURCES):
        y = 100+index*100
        width = 100 if resource.endswith('_toggle') else 56
        d.fixture_nodes.append(node(resource.rsplit('/',1)[-1], bounds=f'[10,{y}][{10+width},{y+56}]'))
    d.fixture_values = {r: r.endswith('ai_generated_toggle') for r in RESOURCES}
    d.fixture_resources = list(RESOURCES)
    def hierarchy(**kwargs):
        root = ET.Element('hierarchy')
        for n in d.fixture_nodes: ET.SubElement(root, 'node', n)
        return ET.tostring(root, encoding='unicode')
    def screenshot():
        image = Image.new('RGB', (400,800), 'white')
        for index, resource in enumerate(d.fixture_resources):
            value = d.fixture_values[resource]
            control = resource.rsplit('/',1)[-1]
            if control.endswith('_toggle'):
                crop = Image.new('RGB', (100,56), 'white'); draw = ImageDraw.Draw(crop)
                draw.rounded_rectangle((0,0,99,55),27,fill=(0,200,30) if value else (220,220,220))
                x = 51 if value else 5; draw.ellipse((x,5,x+44,49),fill='white')
            else:
                crop = Image.new('RGB',(56,56),'white'); draw = ImageDraw.Draw(crop)
                draw.ellipse((3,3,52,52), fill=(0,200,30) if value else (210,210,210))
            image.paste(crop,(10,100+index*100))
        return image
    d.ui.dump_hierarchy.side_effect = hierarchy
    d.ui.screenshot.side_effect = screenshot
    d.tap = Mock(wraps=d.tap)
    d.commit_observed_post = Mock(wraps=d.commit_observed_post)
    return d

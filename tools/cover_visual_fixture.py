"""Render an isolated synthetic cover fixture; never reads/writes user jobs."""
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.clip_cover import compose_cover, cover_settings, image_choices


def main():
    folder = ROOT / 'docs/reports/clip-cover-272/visual-fixture'
    folder.mkdir(parents=True, exist_ok=True)
    for index, color in ((1, '#173251'), (2, '#49305e')):
        image = Image.new('RGB', (1080, 1920), color)
        draw = ImageDraw.Draw(image)
        draw.ellipse((160, 280, 920, 1050), fill='#28577b')
        draw.rounded_rectangle((385, 760, 715, 1260), radius=50, fill='#cc9566')
        draw.ellipse((385, 430, 715, 800), fill='#e9ba87')
        image.save(folder / f'scene{index}.png')
    manifest = {'job_type':'story_short','video_title':'ใครอยู่หลังประตู','generated_images':['scene1.png','scene2.png'],
                'cover':{'headline':'ใครอยู่หลังประตู?', 'alternatives':['ประตูบานนั้น','ความลับที่ซ่อนอยู่'],
                         'emphasis':'ใคร', 'scene_index':2,'theme':'mystery','position':'bottom'}}
    settings = cover_settings(manifest, image_choices(folder, manifest))
    preview = compose_cover(ROOT, folder, manifest, settings, preview=True)
    exported = compose_cover(ROOT, folder, manifest)
    fixture = {'editor':{'item_id':'story:TEST-COVER', 'settings':settings, 'title':manifest['video_title'],
                        'revision':'fixture', 'aspect_ratio':'9:16', 'images':[{'index':i,'url':preview} for i in (1,2)]}, 'preview':preview,
               'exported':str(folder / exported['cover_path'])}
    (folder / 'fixture.json').write_text(json.dumps(fixture, ensure_ascii=False), encoding='utf-8')
    print(fixture['exported'])


if __name__ == '__main__': main()

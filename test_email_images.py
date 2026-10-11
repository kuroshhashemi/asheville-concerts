import base64
import io
import unittest
from PIL import Image
from concert_discovery.email_images import listener_bar, inline_images, play_button, revival_icon

class EmailVisualTests(unittest.TestCase):
    def test_listener_bars_use_largest_audience_not_a_fixed_threshold(self):
        for value, maximum, expected in [(500,1000,300),(1000,1000,600),(500,2000,150),(None,1000,0)]:
            url=listener_bar(value, maximum, '—' if value is None else str(value))
            image=Image.open(io.BytesIO(base64.b64decode(url.split(',',1)[1])))
            colored=sum(image.getpixel((x,1)) == (189,230,222) for x in range(600))
            self.assertEqual(colored,expected)
    def test_embedded_images_are_deduplicated_and_not_left_as_data_urls(self):
        image=play_button()
        content, attachments=inline_images(f'<img src="{image}"><img src="{image}"><img src="{revival_icon()}">')
        self.assertNotIn('data:image',content)
        self.assertEqual(len(attachments),2)
        self.assertEqual(content.count('cid:'),3)

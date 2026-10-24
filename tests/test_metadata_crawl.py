import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from metadata_crawl import Metadata,canonical

class CrawlerTests(unittest.TestCase):
    def test_only_one_topic_per_forum(self):
        self.assertIsNone(canonical("lpv","https://www.lapassionduvin.com/forum/other/47111-else"))
        self.assertIsNone(canonical("vinejo","http://www.vinejo.freebb.be/thread-666.html"))
    def test_pagination(self):
        u="https://www.lapassionduvin.com/forum/bourgognebeaujolais/47053-domaine-de-suremain?start=20"
        self.assertEqual(canonical("lpv",u),u)
    def test_no_message_content_saved(self):
        h=Metadata()
        h.feed('<html><title>Example</title><div class="kmsg">PRIVATE A</div><div class="post_content">PRIVATE B</div></html>')
        self.assertEqual(h.post_markers,2)
        self.assertFalse(hasattr(h,"body"))
if __name__=="__main__":unittest.main()

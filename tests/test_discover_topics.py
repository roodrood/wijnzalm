import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from discover_topics import clean_url, is_topic, topic_identity, LinksAndMetadata

class DiscoveryTests(unittest.TestCase):
    def test_lpv_topic_and_alias(self):
        url="https://www.lapassionduvin.com/bourgognebeaujolais/47053-domaine-de-suremain"
        expect="https://www.lapassionduvin.com/forum/bourgognebeaujolais/47053-domaine-de-suremain"
        self.assertEqual(clean_url("lpv",url),expect)
        self.assertTrue(is_topic("lpv",expect))
    def test_lpv_category(self):
        self.assertEqual(clean_url("lpv","https://www.lapassionduvin.com/forum/bourgognebeaujolais/"),
                         "https://www.lapassionduvin.com/forum/bourgognebeaujolais")
    def test_vinejo_thread(self):
        self.assertEqual(clean_url("vinejo","http://www.vinejo.freebb.be/thread-4841.html"),
                         "http://www.vinejo.freebb.be/thread-4841.html")
        self.assertTrue(is_topic("vinejo","http://www.vinejo.freebb.be/thread-4841-page-2.html"))
    def test_forbid_post_anchor_and_other_host(self):
        self.assertIsNone(clean_url("vinejo","http://www.vinejo.freebb.be/thread-4841-post-66.html"))
        self.assertIsNone(clean_url("lpv","https://other.example/forum/bourgognebeaujolais/47053-domaine-de-suremain"))
    def test_topic_identity_deduplicates_pages(self):
        one="https://www.lapassionduvin.com/forum/bordeaux/1234-chateau-example"
        two=one+"?start=30"
        self.assertEqual(topic_identity("lpv",one),"1234")
        self.assertEqual(topic_identity("lpv",one),topic_identity("lpv",two))
        self.assertEqual(topic_identity("vinejo","http://www.vinejo.freebb.be/thread-456.html"),"456")
        self.assertEqual(topic_identity("vinejo","http://www.vinejo.freebb.be/thread-456.html"),
                         topic_identity("vinejo","http://www.vinejo.freebb.be/thread-456-page-2.html"))
    def test_html_no_post_text_stored(self):
        m=LinksAndMetadata()
        m.feed("<title>Producer X</title><a href='/thread-123.html'>Read</a><div class='post_content'>Tasting note private</div>")
        self.assertEqual(m.post_markers,1)
        self.assertEqual(m.title,"Producer X")
        self.assertFalse(hasattr(m,"post_text"))
if __name__=="__main__":unittest.main()

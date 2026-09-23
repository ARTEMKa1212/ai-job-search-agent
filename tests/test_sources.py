import unittest

from job_agent.sources.arbeitnow import ArbeitnowUKSource


class SourceTests(unittest.TestCase):
    def test_arbeitnow_html_cleanup(self):
        text = ArbeitnowUKSource._text("&lt;p&gt;Python &amp;amp; APIs&lt;/p&gt;")
        self.assertEqual(text, "Python & APIs")


if __name__ == "__main__":
    unittest.main()

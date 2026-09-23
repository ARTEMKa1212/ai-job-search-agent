import sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import unittest

from job_agent.sources.arbeitnow import ArbeitnowUKSource


class SourceTests(unittest.TestCase):
    def test_arbeitnow_html_cleanup(self):
        text = ArbeitnowUKSource._text("&lt;p&gt;Python &amp;amp; APIs&lt;/p&gt;")
        self.assertEqual(text, "Python & APIs")


if __name__ == "__main__":
    unittest.main()

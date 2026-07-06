import unittest

from checks.accessibility_check import check_accessibility


class AccessibilityCheckTests(unittest.TestCase):
    def test_details_contains_issue_descriptions(self):
        html = """
        <html>
          <head><title></title></head>
          <body>
            <img src="image.png">
            <input name="name">
          </body>
        </html>
        """

        result = check_accessibility(html)

        self.assertEqual(result['status'], 'FAIL')
        self.assertIn("Missing 'lang' attribute on <html> tag", result['details'])
        self.assertIn("1 image(s) missing 'alt' attribute", result['details'])
        self.assertIn("Missing or empty <title> tag", result['details'])


if __name__ == '__main__':
    unittest.main()

"""SSRF regression tests for the scraper URL guard."""

import socket
import unittest
from unittest.mock import patch

from tools import _validate_public_url


class ScrapeUrlValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_address_is_rejected(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with patch("tools.socket.getaddrinfo", return_value=addresses):
            with self.assertRaisesRegex(ValueError, "private or reserved"):
                await _validate_public_url("https://example.test")

    async def test_non_http_scheme_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "public HTTP"):
            await _validate_public_url("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()

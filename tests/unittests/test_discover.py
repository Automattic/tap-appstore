import unittest
from unittest.mock import Mock, patch

from appstoreconnect.api import APIError

from tap_appstore import discover


class TestDiscover(unittest.TestCase):

    @patch('appstoreconnect.Api.list_users')
    @patch('time.sleep')
    def test_discover_retries_on_api_error(self, mock_sleep, mock_list_users):
        # Set up a side effect for the mock to raise APIError for the first 3 calls, then return an empty list
        mock_list_users.side_effect = [APIError('APIError') for _ in range(3)] + [[]]

        client = Mock()
        client.list_users = mock_list_users

        with self.assertRaises(AssertionError) as e:
            discover(client)

        # Ensure list_users was called 4 times (3 retries because of APIError + 1 assertion error)
        assert mock_list_users.call_count == 4
        assert str(e.exception) == 'API call failed - List of users is empty'


if __name__ == '__main__':
    unittest.main()
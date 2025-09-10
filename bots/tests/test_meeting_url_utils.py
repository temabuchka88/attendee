# test_meeting_utils.py
import unittest

from bots.meeting_url_utils import MeetingTypes, domain_and_subdomain_from_url, meeting_type_from_url, normalize_meeting_url, root_domain_from_url


class TestMeetingUrlUtils(unittest.TestCase):
    def test_root_domain_from_url(self):
        self.assertEqual(root_domain_from_url("https://meet.google.com/abc-defg-hij"), "google.com")
        self.assertEqual(root_domain_from_url("https://teams.microsoft.com/l/meetup-join/..."), "microsoft.com")
        self.assertEqual(root_domain_from_url("https://zoom.us/j/123456789"), "zoom.us")
        self.assertIsNone(root_domain_from_url(""))
        self.assertIsNone(root_domain_from_url(None))

    def test_domain_and_subdomain_from_url(self):
        self.assertEqual(domain_and_subdomain_from_url("https://meet.google.com/abc-defg-hij"), "meet.google.com")
        self.assertEqual(domain_and_subdomain_from_url("https://teams.microsoft.com/l/meetup-join/..."), "teams.microsoft.com")
        self.assertEqual(domain_and_subdomain_from_url("https://zoom.us/j/123456789"), ".zoom.us")
        self.assertIsNone(domain_and_subdomain_from_url(""))
        self.assertIsNone(domain_and_subdomain_from_url(None))

    def test_teams_live_urls(self):
        self.assertEqual(meeting_type_from_url("https://teams.live.com/meet/9876543210?p=abc"), MeetingTypes.TEAMS)
        self.assertEqual(meeting_type_from_url("https://teams.microsoft.com/meet/9876543210?p=qHDqtvFSfIg1rT"), MeetingTypes.TEAMS)
        self.assertEqual(meeting_type_from_url("https://teams.live.com/meet/9876543210?p=abc>"), MeetingTypes.TEAMS)
        self.assertEqual(normalize_meeting_url("https://teams.live.com/meet/9876543210?p=abc>")[1], "https://teams.live.com/meet/9876543210?p=abc")

    def test_teams_meetup_join_urls(self):
        teams_url_with_trailing_carat = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_MjYzNWQ3MzQtNzAzNi00ZTcxLWJjMzctODQwYTBmMDQ4MzQ2%40thread.v2/0?context=%7b%22Tid%22%3a%22b8291b4b-f793-49bc-8a00-9d5fc37b9a77%22%2c%22Oid%22%3a%22216d2e11-45cc-4326-9689-d05554e5c1d1%22%7d>"
        self.assertEqual(meeting_type_from_url(teams_url_with_trailing_carat), MeetingTypes.TEAMS)
        self.assertEqual(normalize_meeting_url(teams_url_with_trailing_carat)[1], 'https://teams.microsoft.com/l/meetup-join/19:meeting_MjYzNWQ3MzQtNzAzNi00ZTcxLWJjMzctODQwYTBmMDQ4MzQ2@thread.v2/0?context={"Tid":"b8291b4b-f793-49bc-8a00-9d5fc37b9a77","Oid":"216d2e11-45cc-4326-9689-d05554e5c1d1"}')

    def test_meeting_type_from_url(self):
        self.assertEqual(meeting_type_from_url("https://zoom.us/j/123456789"), MeetingTypes.ZOOM)
        self.assertEqual(meeting_type_from_url("https://meet.google.com/abc-defg-hij"), MeetingTypes.GOOGLE_MEET)
        self.assertEqual(meeting_type_from_url("https://teams.microsoft.com/l/meetup-join/19%3ameeting_ABCDEFGHIJKLMNOPQRSTUVWXYZ@thread.v2/0"), None)
        self.assertEqual(meeting_type_from_url("https://teams.live.com/l/meetup-join/19%3ameeting_1234567890ABCDEFGHIJK@thread.v2/0?context=xyz"), None)
        self.assertEqual(meeting_type_from_url("https://teams.live.com/meet/9341295272229?p=OVs7TU8cN91WowQYnd"), MeetingTypes.TEAMS)
        self.assertEqual(meeting_type_from_url("https://teams.live.com/meet/9876543210?p=abc"), MeetingTypes.TEAMS)
        self.assertIsNone(meeting_type_from_url("https://example.com"))
        self.assertIsNone(meeting_type_from_url(""))
        self.assertIsNone(meeting_type_from_url(None))
        self.assertEqual(meeting_type_from_url("https://teams.microsoft.com/l/meetup-join/19%3ameeting_OTA0nTDmYgItYTlTti00MmRkLTgxODItZGFmNWVmNTJmOGQ4%40thread.v2"), None)


if __name__ == "__main__":
    unittest.main()

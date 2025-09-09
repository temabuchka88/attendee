import re

from tldextract import tldextract

from .models import (
    MeetingTypes,
)


def root_domain_from_url(url):
    if not url:
        return None
    return tldextract.extract(url).registered_domain


def domain_and_subdomain_from_url(url):
    if not url:
        return None
    extract_from_url = tldextract.extract(url)
    return extract_from_url.subdomain + "." + extract_from_url.registered_domain


def is_valid_teams_url(url: str) -> bool:
    if not url:
        return False

    meetup_pattern = re.compile(
        r"^https://teams\.(microsoft|live)\.com/l/meetup-join/"
        r"19%3ameeting_([a-zA-Z0-9]{20,})@thread\.v2/0(\?.*)?$"
    )

    simple_meet_pattern = re.compile(r"^https://teams\.live\.com/meet/(\d+)(\?.*)?$")

    meeting_id = None

    meetup_match = meetup_pattern.match(url)
    if meetup_match:
        meeting_id = meetup_match.group(2)

    simple_match = simple_meet_pattern.match(url)
    if simple_match:
        meeting_id = simple_match.group(1)

    if not meeting_id:
        return False

    return True


def meeting_type_from_url(url):
    if not url:
        return None

    root_domain = root_domain_from_url(url)
    domain_and_subdomain = domain_and_subdomain_from_url(url)

    if root_domain == "zoom.us":
        return MeetingTypes.ZOOM
    elif domain_and_subdomain == "meet.google.com":
        return MeetingTypes.GOOGLE_MEET
    elif domain_and_subdomain and domain_and_subdomain.lower() in ("teams.microsoft.com", "teams.live.com"):
        if is_valid_teams_url(url):
            return MeetingTypes.TEAMS
    else:
        return None

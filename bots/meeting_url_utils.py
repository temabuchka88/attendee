from urllib.parse import unquote

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


def get_normalized_teams_url(url):
    if url is None:
        return None

    return unquote(unquote(url.strip())).rstrip(">")


def meeting_type_from_url(url):
    if not url:
        return None

    root_domain = root_domain_from_url(url)
    domain_and_subdomain = domain_and_subdomain_from_url(url)

    if root_domain == "zoom.us":
        return MeetingTypes.ZOOM
    elif domain_and_subdomain == "meet.google.com":
        return MeetingTypes.GOOGLE_MEET
    elif domain_and_subdomain == "teams.microsoft.com" or domain_and_subdomain == "teams.live.com":
        return MeetingTypes.TEAMS
    else:
        return None

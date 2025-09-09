import base64
import re
from urllib.parse import unquote

import tldextract

from .models import (
    MeetingTypes,
)

HTTP_URL_RE = re.compile(r"https?://[^\s<>\"']+")


def contains_multiple_urls(url: str):
    if not url:
        return False

    found_urls = []
    # Iterate over every suffix of the url
    for i in range(len(url)):
        suffix = url[i:]
        # Check if the suffix is a valid url via the regexp
        if HTTP_URL_RE.match(suffix):
            found_urls.append(suffix)
            continue
        # Check the unquoted suffix
        if HTTP_URL_RE.match(unquote(suffix)):
            found_urls.append(unquote(suffix))
            continue
        # Check the double unquoted suffix
        if HTTP_URL_RE.match(unquote(unquote(suffix))):
            found_urls.append(unquote(unquote(suffix)))
            continue
        # Check the base64 decoded suffix
        try:
            if HTTP_URL_RE.match(base64.b64decode(suffix).decode("utf-8")):
                found_urls.append(base64.b64decode(suffix).decode("utf-8"))
                continue
        except Exception:
            # Skip if not valid base64 or can't be decoded as UTF-8
            pass

    return len(found_urls) > 1


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
    if contains_multiple_urls(url):
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

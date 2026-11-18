"""Review a project's robots.txt without crawling or granting reuse permission."""
import hashlib
from http.client import HTTPSConnection
import ipaddress
import re
import socket
import ssl
import unicodedata
from urllib.parse import urlsplit
import certifi

ROBOTS_LIMIT = 65536
USER_AGENT = 'ALMG/1.0 (https://github.com/arpit-it/ALMG)'


def robots_url(website):
    if (not isinstance(website, str) or len(website) > 2048
            or any(not c.isprintable() or c.isspace() for c in website)):
        raise ValueError('Save a public HTTPS project website first.')
    parsed = urlsplit(website)
    host = parsed.hostname or ''
    if (parsed.scheme != 'https' or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443) or '?' in website or '#' in website
            or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\.?', host, re.I)):
        raise ValueError('Save a public HTTPS project website first.')
    return f'https://{host}/robots.txt'


def public_address(host):
    addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(value).is_global or ipaddress.ip_address(value).is_multicast for value in addresses):
        raise ValueError('Website access review requires public internet addresses.')
    return sorted(addresses)[0]


def robots_review(website, status, data):
    url = robots_url(website)
    if status not in (200, 404) or len(data) > ROBOTS_LIMIT:
        raise ValueError('robots.txt could not be reviewed within the approved limit.')
    text = data.decode('utf-8-sig') if status == 200 else ''
    if any(unicodedata.category(c) in {'Cc', 'Cs'} and c not in '\n\r\t' for c in text):
        raise ValueError('robots.txt contains unreadable text.')
    return {'website': website, 'robots_url': url, 'robots_status': status, 'robots_text': text,
            'robots_sha256': hashlib.sha256(data).hexdigest(), 'access_status': 'unverified', 'reuse_status': 'unverified'}


def fetch_robots(website):
    url = robots_url(website)
    host = urlsplit(url).hostname
    address = public_address(host)
    context = ssl.create_default_context(cafile=certifi.where())
    connection = HTTPSConnection(host, timeout=30, context=context)
    # Connect to the validated address while preserving TLS hostname verification.
    raw = socket.create_connection((address, 443), timeout=30)
    try:
        connection.sock = context.wrap_socket(raw, server_hostname=host)
        connection.request('GET', '/robots.txt', headers={'User-Agent': USER_AGENT, 'Accept': 'text/plain', 'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        if response.status == 404:
            return robots_review(website, 404, b'')
        if response.status != 200 or response.getheader('Content-Type', '').split(';')[0].strip().lower() != 'text/plain':
            raise ValueError('robots.txt must be a successful plain-text response; redirects are not followed.')
        return robots_review(website, 200, response.read(ROBOTS_LIMIT + 1))
    finally:
        connection.close()
        raw.close()

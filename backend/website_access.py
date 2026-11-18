"""Review a project's robots.txt without crawling or granting reuse permission."""
import hashlib
from http.client import HTTPSConnection
import ipaddress
import re
import socket
import ssl
import threading
import time
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
            'reviewed_at': time.time(), 'robots_sha256': hashlib.sha256(data).hexdigest(), 'access_status': 'unverified', 'reuse_status': 'unverified',
            **robots_path_decision(website, text, status)}


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


def guidance_checksum(review):
    """Bind access-rule review to the exact website and displayed robots guidance."""
    import json
    if (review.get('robots_url') != robots_url(review.get('website'))
            or review.get('robots_status') not in (200, 404)
            or not isinstance(review.get('reviewed_at'), (int, float))
            or not isinstance(review.get('robots_text'), str)
            or len(review['robots_text'].encode('utf-8')) > ROBOTS_LIMIT
            or (review['robots_status'] == 404 and review['robots_text'])
            or not isinstance(review.get('robots_sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', review['robots_sha256'])):
        raise ValueError('Review the website robots guidance first.')
    fields = {key: review[key] for key in ('website', 'robots_url', 'robots_status', 'robots_text', 'robots_sha256', 'reviewed_at')}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def access_rule_evidence(review, decision, current_website):
    """Record a user's site access-rule review without approving content reuse."""
    import time
    basis = decision.get('access_basis')
    if (current_website != review.get('website') or decision.get('approved_website') != current_website
            or decision.get('confirmed') is not True or decision.get('approved_scope') != 'website_access_rules'
            or not isinstance(basis, str) or not 10 <= len(basis.strip()) <= 2000):
        raise ValueError('Review the current website access rules and record the basis first.')
    return {'website': current_website, 'scope': 'website_access_rules', 'access_basis': basis.strip(),
            'guidance_sha256': guidance_checksum(review), 'time': time.time()}


def _normalized_path(value):
    """Normalize UTF-8 and percent-encoded unreserved octets for rule matching."""
    result, index = [], 0
    while index < len(value):
        char = value[index]
        if char == '%':
            code = value[index + 1:index + 3]
            if len(code) != 2 or not re.fullmatch(r'[0-9a-fA-F]{2}', code):
                raise ValueError('Invalid percent encoding in robots guidance.')
            decoded = chr(int(code, 16))
            result.append(decoded if decoded in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~' else '%' + code.upper())
            index += 3
        else:
            result.append(char if ord(char) < 128 else ''.join(f'%{byte:02X}' for byte in char.encode('utf-8')))
            index += 1
    return ''.join(result)


def _rule_matches(pattern, path):
    anchored = pattern.endswith('$')
    parts = (pattern[:-1] if anchored else pattern).split('*')
    if not path.startswith(parts[0]):
        return False
    cursor = len(parts[0])
    if len(parts) == 1:
        return not anchored or cursor == len(path)
    for part in parts[1:-1]:
        found = path.find(part, cursor)
        if found < 0:
            return False
        cursor = found + len(part)
    last = parts[-1]
    if anchored:
        return path.endswith(last) and len(path) - len(last) >= cursor
    return path.find(last, cursor) >= 0


def robots_path_decision(website, text, status=200):
    """Evaluate the saved URL for ALMG; this does not grant access or reuse."""
    from urllib.parse import unquote_to_bytes
    if status != 200:
        return {'robots_decision': 'undetermined', 'robots_rule': 'No robots.txt guidance was supplied.'}
    groups, agents, rules, has_rule = [], [], [], False
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if ':' not in line:
            continue
        key, value = (part.strip() for part in line.split(':', 1))
        key = key.casefold()
        if key == 'user-agent':
            if has_rule:
                groups.append((agents, rules))
                agents, rules, has_rule = [], [], False
            agents.append(value.casefold())
        elif key in {'allow', 'disallow'} and agents:
            has_rule = True
            if value:
                rules.append((key, value))
    groups.append((agents, rules))
    specific = [rules for agents, rules in groups if 'almg' in agents]
    applicable = specific if specific else [rules for agents, rules in groups if '*' in agents]
    try:
        path = _normalized_path(urlsplit(website).path or '/')
        matches = []
        for group in applicable:
            for key, value in group:
                if not value.startswith('/') or len(value) > 2048:
                    raise ValueError('Unsupported robots rule.')
                pattern = _normalized_path(value)
                if _rule_matches(pattern, path):
                    literal = pattern.removesuffix('$').replace('*', '')
                    matches.append((len(unquote_to_bytes(literal)), key == 'allow', key, value))
        if not matches:
            return {'robots_decision': 'allowed', 'robots_rule': 'No matching disallow rule for ALMG.'}
        _, allowed, key, value = max(matches)
        return {'robots_decision': 'allowed' if allowed else 'disallowed', 'robots_rule': f'{key.title()}: {value}'}
    except ValueError:
        return {'robots_decision': 'undetermined', 'robots_rule': 'A matching group contains unsupported rules; crawling must remain blocked.'}


SEED_LIMIT = 512 * 1024
SEED_LOCK = threading.Lock()
SEED_LAST_REQUEST = 0.0


def require_discovery_access(review, current_website):
    approval = review.get('access_approval')
    if (review.get('website') != current_website or not isinstance(approval, dict)
            or approval.get('scope') != 'website_access_rules' or approval.get('website') != current_website
            or approval.get('guidance_sha256') != guidance_checksum(review)
            or not isinstance(review.get('reviewed_at'), (int, float))
            or not 0 <= time.time() - review['reviewed_at'] <= 3600
            or robots_path_decision(current_website, review['robots_text'], review['robots_status'])['robots_decision'] != 'allowed'):
        raise ValueError('Refresh robots guidance and record current access-rule review for an allowed website URL first.')
    # Apply the most conservative supplied extension until richer scheduling exists.
    delay = 1.0
    for line in review['robots_text'].splitlines():
        key, separator, value = line.split('#', 1)[0].partition(':')
        if separator and key.strip().casefold() == 'request-rate':
            raise ValueError('Request-rate directives need review before discovery is supported.')
        if separator and key.strip().casefold() == 'crawl-delay':
            try:
                number = float(value.strip())
            except ValueError:
                raise ValueError('Unsupported crawl-delay directive.') from None
            if not 0 <= number <= 60:
                raise ValueError('Crawl-delay over 60 seconds is not supported for this preview.')
            delay = max(delay, number)
    return delay


def discovered_links(website, data, review):
    """List at most 20 same-origin links without loading their content."""
    from html.parser import HTMLParser
    from urllib.parse import urljoin, urldefrag, unquote_to_bytes
    if len(data) > SEED_LIMIT:
        raise ValueError('The website discovery page exceeds 512 KiB.')
    text = data.decode('utf-8-sig')
    origin = urlsplit(website)
    rows, seen = [], {website}
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag != 'a' or len(rows) >= 20:
                return
            href = dict(attrs).get('href')
            if not isinstance(href, str) or len(href) > 2048:
                return
            source = urldefrag(urljoin(website, href))[0]
            try:
                robots_url(source)
                parsed = urlsplit(source)
                if (parsed.hostname != origin.hostname or parsed.port != origin.port
                        or any(part in (b'.', b'..') for part in unquote_to_bytes(parsed.path).split(b'/'))
                        or '\\' in parsed.path or source in seen
                        or robots_path_decision(source, review['robots_text'], review['robots_status'])['robots_decision'] != 'allowed'):
                    return
            except (ValueError, UnicodeError):
                return
            seen.add(source)
            rows.append({'source': source, 'discovered_from': website, 'provider': 'project_website', 'reuse_status': 'unverified'})
    parser = Links()
    parser.feed(text)
    return rows


def fetch_seed_links(review, current_website):
    global SEED_LAST_REQUEST
    delay = require_discovery_access(review, current_website)
    parsed = urlsplit(current_website)
    address = public_address(parsed.hostname)
    context = ssl.create_default_context(cafile=certifi.where())
    connection = HTTPSConnection(parsed.hostname, timeout=30, context=context)
    with SEED_LOCK:
        time.sleep(max(0, delay - (time.time() - max(SEED_LAST_REQUEST, review['reviewed_at']))))
        raw = socket.create_connection((address, 443), timeout=30)
        try:
            connection.sock = context.wrap_socket(raw, server_hostname=parsed.hostname)
            SEED_LAST_REQUEST = time.time()
            connection.request('GET', parsed.path or '/', headers={'User-Agent': USER_AGENT, 'Accept': 'text/html', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status != 200 or response.getheader('Content-Type', '').split(';')[0].strip().lower() not in {'text/html', 'application/xhtml+xml'}:
                raise ValueError('Discovery requires a successful HTML page; redirects are not followed.')
            return discovered_links(current_website, response.read(SEED_LIMIT + 1), review)
        finally:
            connection.close()
            raw.close()

"""Bounded SEC submissions metadata preview; filing contents are never loaded."""
import re
import unicodedata
from datetime import date


def submissions_request(cik, contact):
    if not isinstance(cik, str) or not re.fullmatch(r'[0-9]{1,10}', cik) or int(cik) == 0:
        raise ValueError('Enter a company CIK containing one to ten digits.')
    if (not isinstance(contact, str) or len(contact) > 200
            or not re.fullmatch(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', contact)):
        raise ValueError('Enter a contact email for the declared SEC user agent.')
    return f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json', f'ALMG/1.0 {contact}'


def filing_candidates(payload, cik, limit=20):
    expected = int(cik)
    if (not isinstance(payload, dict) or isinstance(payload.get('cik'), bool)
            or not re.fullmatch(r'[0-9]{1,10}', str(payload.get('cik', ''))) or int(payload['cik']) != expected):
        raise ValueError('SEC metadata does not match the approved company CIK.')
    name = payload.get('name')
    if (not isinstance(name, str) or not 1 <= len(name) <= 1000
            or any(unicodedata.category(c) in {'Cc', 'Cs'} for c in name)):
        raise ValueError('SEC returned unreadable company metadata.')
    filings = payload.get('filings')
    recent = filings.get('recent') if isinstance(filings, dict) else None
    keys = ('accessionNumber', 'filingDate', 'form', 'primaryDocument')
    if (not isinstance(recent, dict) or any(not isinstance(recent.get(k), list) for k in keys)
            or len({len(recent[k]) for k in keys}) != 1):
        raise ValueError('SEC returned unreadable filing metadata.')
    rows, seen = [], set()
    for accession, filed, form, document in zip(*(recent[k] for k in keys)):
        if (not isinstance(accession, str) or not re.fullmatch(r'[0-9]{10}-[0-9]{2}-[0-9]{6}', accession)
                or accession in seen or not isinstance(document, str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._\-]{0,199}', document)
                or '..' in document or not isinstance(form, str) or not 1 <= len(form) <= 40
                or any(unicodedata.category(c) in {'Cc', 'Cs'} for c in form)):
            continue
        try:
            if not isinstance(filed, str) or date.fromisoformat(filed).isoformat() != filed:
                continue
        except ValueError:
            continue
        rows.append({'company': name, 'cik': str(expected), 'accession': accession, 'filing_date': filed,
                     'form': form, 'source': f'https://www.sec.gov/Archives/edgar/data/{expected}/{accession.replace("-", "")}/{document}',
                     'provider': 'sec_edgar', 'reuse_status': 'unverified'})
        seen.add(accession)
        if len(rows) >= limit:
            break
    return rows


COMPANY_CATALOG_URL = 'https://www.sec.gov/files/company_tickers_exchange.json'


def company_query(value):
    if (not isinstance(value, str) or not 1 <= len(value.strip()) <= 160
            or any(unicodedata.category(c) in {'Cc', 'Cs'} for c in value)):
        raise ValueError('Enter a company name or ticker, up to 160 characters.')
    return value.strip()


def company_candidates(payload, query, limit=20):
    """Match the bounded SEC association catalog locally; no filing requests."""
    terms = company_query(query).casefold().split()
    if (not isinstance(payload, dict) or payload.get('fields') != ['cik', 'name', 'ticker', 'exchange']
            or not isinstance(payload.get('data'), list) or len(payload['data']) > 50000):
        raise ValueError('SEC returned an unsupported company catalog.')
    rows, seen = [], set()
    for row in payload['data']:
        if not isinstance(row, list) or len(row) != 4:
            continue
        cik, name, ticker, exchange = row
        if (type(cik) is not int or not 1 <= cik <= 9999999999
                or any(not isinstance(v, str) or not 1 <= len(v) <= bound
                       or any(unicodedata.category(c) in {'Cc', 'Cs'} for c in v)
                       for v, bound in ((name, 1000), (ticker, 40)))
                or (exchange is not None and (not isinstance(exchange, str) or len(exchange) > 100
                    or any(unicodedata.category(c) in {'Cc', 'Cs'} for c in exchange)))):
            continue
        if cik in seen or not all(term in f'{name} {ticker}'.casefold() for term in terms):
            continue
        rows.append({'cik': str(cik), 'company': name, 'ticker': ticker, 'exchange': exchange or '',
                     'source': COMPANY_CATALOG_URL, 'provider': 'sec_edgar'})
        seen.add(cik)
        if len(rows) >= limit:
            break
    return rows

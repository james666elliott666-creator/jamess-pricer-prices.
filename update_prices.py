"""Refresh public City Plumbing prices; never download or store customer data."""
import argparse
import concurrent.futures
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import html as html_module
import json
from pathlib import Path
import re
import time
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent


def products(page):
    marker = re.search(r'window\.__PRELOADED_STATE__\s*=\s*', page)
    if not marker:
        raise ValueError('Product data unavailable; retained previous price')
    state = json.JSONDecoder().raw_decode(page[marker.end():])[0]
    result = {}

    def walk(value):
        if isinstance(value, dict):
            if value.get('code') and isinstance(value.get('price'), dict):
                code = str(value['code'])
                if code not in result or value.get('technicalSpecifications'):
                    result[code] = value
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(state)
    return result


def positive_money(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0:
            raise ValueError('Missing or invalid price')
        return number.quantize(Decimal('0.01'))
    except InvalidOperation as exc:
        raise ValueError('Invalid price') from exc


def extract(entry, product, page):
    price = product['price']
    if str(product.get('code')) != entry['code'] or str(price.get('productCode')) != entry['code']:
        raise ValueError('Product code mismatch')
    if price.get('isContractPrice'):
        raise ValueError('Account-specific price rejected')
    inc = positive_money(price['retailPrice']['valueIncVat'])
    ex = positive_money(price['retailPrice']['valueExVat'])
    # Explicit inc/ex VAT fields are required; do not infer tax from page text.
    if inc < ex:
        raise ValueError('VAT values inconsistent')
    for tier in price.get('promotionalPriceTiers') or []:
        if tier.get('minimumQuantity') == 1:
            inc = min(inc, positive_money(tier['finalPrice']['valueIncVat']))
    specs = {x.get('name', '').lower(): str(x.get('value', ''))
             for x in product.get('technicalSpecifications') or []}
    pack = specs.get('pack quantity')
    title = product.get('name', '')
    if not pack:
        match = re.search(r'pack\s*(?:of\s*)?(\d+)', title, re.I) or re.search(r'(\d+)\s*pack', title, re.I)
        if match:
            pack = match.group(1)
    if pack and Decimal(pack) != Decimal(str(entry['packQty'])):
        raise ValueError('Pack quantity changed; review required')
    if entry['packQty'] > 1 and not pack:
        raise ValueError('Pack quantity could not be verified')
    # For a product page, independently compare the displayed structured offer.
    for raw in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S):
        obj = json.loads(raw)
        if isinstance(obj, dict) and str(obj.get('sku')) == entry['code']:
            offer = obj.get('offers', {})
            if offer.get('priceCurrency') != 'GBP' or positive_money(offer.get('price')) != inc:
                raise ValueError('Displayed price disagrees with product data')
    # A large change requires review, not an automatic quote price replacement.
    old = positive_money(entry['price'])
    if not Decimal('0.5') <= inc / old <= Decimal('2'):
        raise ValueError('Price changed by more than the review threshold')
    paths = re.findall(r'href=["\']([^"\']*/p/' + re.escape(entry['code']) + r')["\']', page)
    resolved = urljoin('https://www.cityplumbing.co.uk', html_module.unescape(paths[0])) if paths else entry['url']
    return float(inc), title, resolved


def fetch(url):
    if urlparse(url).hostname != 'www.cityplumbing.co.uk' or not url.startswith('https://'):
        raise ValueError('Unexpected supplier URL')
    request = Request(url, headers={'User-Agent': 'JamesPricer-PriceCheck/1.0', 'Accept': 'text/html'})
    with urlopen(request, timeout=25) as response:
        if urlparse(response.url).hostname != 'www.cityplumbing.co.uk':
            raise ValueError('Unexpected redirect')
        raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError('Page too large')
        return raw.decode('utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT)
    args = parser.parse_args()
    entries = json.loads((ROOT / 'catalogue.json').read_text())
    previous_path = args.output / 'prices.json'
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {'items': []}
    previous_items = {x['key']: x for x in previous['items']}
    selected = entries[:args.limit] if args.limit else entries
    groups = {}
    for entry in selected:
        old = previous_items.get(entry['key'], {})
        url = old.get('sourceUrl', entry['url'])
        groups.setdefault(url, []).append(entry)
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    succeeded, failed = [], []

    def run(group):
        url, items = group
        good, bad = [], []
        try:
            if args.fixtures:
                page = (args.fixtures / ('cp-' + items[0]['code'] + '.html')).read_text()
            else:
                page = fetch(url)
                time.sleep(0.5)
            records = products(page)
            for entry in items:
                try:
                    product = records.get(entry['code'])
                    if not product:
                        raise ValueError('Product not found on source page')
                    current = dict(entry)
                    current['price'] = previous_items.get(entry['key'], {}).get('price', entry['price'])
                    amount, name, resolved = extract(current, product, page)
                    good.append({'key': entry['key'], 'code': entry['code'], 'price': amount,
                                 'packQty': entry['packQty'], 'quoteUnit': entry['quoteUnit'],
                                 'checkedAt': now, 'sourceUrl': resolved, 'name': name})
                except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
                    bad.append({'key': entry['key'], 'reason': str(exc)})
        except Exception as exc:
            bad.extend({'key': entry['key'], 'reason': str(exc)} for entry in items)
        return good, bad

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for good, bad in pool.map(run, groups.items()):
            succeeded.extend(good)
            failed.extend(bad)
            print(f'Checked {len(succeeded) + len(failed)}/{len(selected)}; valid {len(succeeded)}', flush=True)
    for item in succeeded:
        previous_items[item['key']] = item
    known = {entry['key'] for entry in entries}
    feed = {'schemaVersion': 1, 'supplier': 'City Plumbing', 'currency': 'GBP',
            'vatIncluded': True, 'generatedAt': now, 'catalogueCount': len(entries),
            'checkedThisRun': len(succeeded), 'failedThisRun': len(failed),
            'items': [item for key, item in previous_items.items() if key in known]}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'check-report.json').write_text(json.dumps({'checkedAt': now, 'success': len(succeeded), 'failures': failed}, indent=2) + '\n')
    if succeeded:
        temporary = args.output / 'prices.tmp'
        temporary.write_text(json.dumps(feed, separators=(',', ':')) + '\n')
        temporary.replace(previous_path)
    if not succeeded:
        raise SystemExit('No prices verified; existing feed left unchanged')


if __name__ == '__main__':
    main()

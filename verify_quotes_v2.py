#!/usr/bin/env python3
"""Verify quote sources by fetching URLs and checking for quote text.
Categorizes unfetchable sources (video, podcast, paywall) separately."""

import re, json, sys, csv
from urllib.parse import urlparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

# Domains/patterns that are video, podcast, or audio - text won't appear on page
VIDEO_PODCAST_DOMAINS = {
    'youtube.com', 'youtu.be', 'spotify.com', 'podcasts.apple.com',
    'open.spotify.com', 'soundcloud.com', 'vimeo.com', 'ted.com',
    'masterclass.com', 'audible.com',
}

VIDEO_PODCAST_PATTERNS = [
    '/podcast', '/episode', '/video', '/watch',
]

# Domains likely to block scrapers or be paywalled
PAYWALL_DOMAINS = {
    'stratechery.com', 'wsj.com', 'nytimes.com', 'ft.com',
    'bloomberg.com', 'economist.com', 'hbr.org',
}

# Social media that often doesn't render for scrapers
SOCIAL_DOMAINS = {
    'x.com', 'twitter.com', 'instagram.com', 'facebook.com',
    'linkedin.com', 'threads.net', 'tiktok.com',
}

# Book/product pages - quote might be inside the book, not on the page
BOOK_DOMAINS = {
    'amazon.com', 'amazon.co.uk', 'goodreads.com', 'bookshop.org',
}

def classify_url(url):
    """Classify URL into fetchable vs unfetchable categories."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower().replace('www.', '')
    path = parsed.path.lower()

    if domain in VIDEO_PODCAST_DOMAINS or any(p in path for p in VIDEO_PODCAST_PATTERNS):
        return 'video_podcast'
    if domain in PAYWALL_DOMAINS:
        return 'paywall'
    if domain in SOCIAL_DOMAINS:
        return 'social'
    if domain in BOOK_DOMAINS:
        return 'book_page'
    return 'fetchable'

# Extract quotes from index.html
with open('index.html', 'r') as f:
    content = f.read()
m = re.search(r'const QUOTES\s*=\s*(\[.*?\]);', content)
quotes = json.loads(m.group(1))

with_urls = [q for q in quotes if q.get('url')]

# Classify all URLs
classified = {}
for q in with_urls:
    cat = classify_url(q['url'])
    classified.setdefault(cat, []).append(q)

print("URL Classification:")
for cat in ['fetchable', 'video_podcast', 'social', 'paywall', 'book_page']:
    count = len(classified.get(cat, []))
    print(f"  {cat:<16} {count}")
print(f"  {'TOTAL':<16} {len(with_urls)}")
print()

def normalize(text):
    text = text.lower()
    text = re.sub(r'[\u2018\u2019\u201c\u201d\u2013\u2014\u2026]', '', text)
    text = re.sub(r"['\"\-\.\,\;\:\!\?]", '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_keywords(quote_text, min_words=4):
    words = quote_text.split()
    phrases = []
    if len(words) >= min_words:
        phrases.append(' '.join(words[:min_words]))
        mid = len(words) // 2
        phrases.append(' '.join(words[mid:mid+min_words]))
        phrases.append(' '.join(words[-min_words:]))
    else:
        phrases.append(quote_text)
    return phrases

def check_url(quote):
    url = quote['url']
    qid = quote['id']
    text = quote['text']

    try:
        result = subprocess.run(
            ['curl', '-sL', '--max-time', '15', '-A',
             'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
             url],
            capture_output=True, text=True, timeout=20, errors='replace'
        )
        page = result.stdout
    except Exception as e:
        return (qid, 'error', f'Fetch failed: {str(e)[:50]}', quote)

    if not page or len(page) < 100:
        return (qid, 'error', 'Empty or very short response', quote)

    if result.returncode != 0:
        return (qid, 'error', f'curl exit code {result.returncode}', quote)

    page_norm = normalize(page)
    text_norm = normalize(text)

    if text_norm in page_norm:
        return (qid, 'found', 'Full quote match', quote)

    keywords = get_keywords(text_norm)
    matches = sum(1 for kw in keywords if normalize(kw) in page_norm)

    if matches >= 2:
        return (qid, 'likely', f'{matches}/{len(keywords)} phrase chunks found', quote)
    elif matches == 1:
        return (qid, 'partial', f'1/{len(keywords)} phrase chunks found', quote)

    author_norm = normalize(quote['author'].split('(')[0].split(',')[0])
    author_on_page = author_norm in page_norm

    if not author_on_page:
        return (qid, 'not_found', 'Neither quote nor author found on page', quote)

    return (qid, 'not_found', 'Author found but quote text not found', quote)

# Only fetch the "fetchable" ones
fetchable = classified.get('fetchable', [])
print(f"Verifying {len(fetchable)} fetchable URLs...\n")

results = []
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(check_url, q): q for q in fetchable}
    done = 0
    for future in as_completed(futures):
        done += 1
        qid, status, detail, quote = future.result()
        results.append((qid, status, detail, quote))
        if done % 50 == 0:
            print(f"  Progress: {done}/{len(fetchable)}", file=sys.stderr)

# Summary
found = [r for r in results if r[1] == 'found']
likely = [r for r in results if r[1] == 'likely']
partial = [r for r in results if r[1] == 'partial']
not_found = [r for r in results if r[1] == 'not_found']
errors = [r for r in results if r[1] == 'error']

print("=" * 100)
print("FETCHABLE URLs RESULTS")
print("=" * 100)
print(f"  Found (full match):     {len(found)}")
print(f"  Likely (2+ phrases):    {len(likely)}")
print(f"  Partial (1 phrase):     {len(partial)}")
print(f"  Not found on page:      {len(not_found)}")
print(f"  Errors (fetch failed):  {len(errors)}")
print()
print("UNFETCHABLE URLs (need manual check):")
for cat in ['video_podcast', 'social', 'paywall', 'book_page']:
    items = classified.get(cat, [])
    if items:
        print(f"  {cat}: {len(items)} quotes")

# Print problem quotes
print()
print("=" * 100)
print("PROBLEM QUOTES — not found on fetchable pages")
print("=" * 100)
for qid, status, detail, quote in sorted(not_found, key=lambda r: r[0]):
    print(f"  [{qid}] {quote['author'][:30]:<32} {detail}")
    print(f"        \"{quote['text'][:70]}...\"")
    print(f"        URL: {quote['url']}")
    print()

if errors:
    print("=" * 100)
    print("FETCH ERRORS")
    print("=" * 100)
    for qid, status, detail, quote in sorted(errors, key=lambda r: r[0]):
        print(f"  [{qid}] {quote['author'][:30]:<32} {detail}")
        print(f"        URL: {quote['url']}")
        print()

# Write CSV
with open('quote_verification_report.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['ID', 'Status', 'Category', 'Author', 'Quote (first 80 chars)', 'Source', 'URL', 'Detail', 'needsReview'])

    # Write fetchable results
    for qid, status, detail, quote in sorted(results, key=lambda r: (
        {'not_found': 0, 'error': 1, 'partial': 2, 'likely': 3, 'found': 4}[r[1]], r[0]
    )):
        w.writerow([qid, status, 'fetchable', quote['author'], quote['text'][:80],
                     quote.get('source', ''), quote['url'], detail, quote.get('needsReview', False)])

    # Write unfetchable
    for cat in ['video_podcast', 'social', 'paywall', 'book_page']:
        for quote in classified.get(cat, []):
            w.writerow([quote['id'], 'skipped', cat, quote['author'], quote['text'][:80],
                         quote.get('source', ''), quote['url'], f'Unfetchable: {cat}', quote.get('needsReview', False)])

    # Write no-URL quotes
    for quote in quotes:
        if not quote.get('url'):
            w.writerow([quote['id'], 'no_url', 'no_url', quote['author'], quote['text'][:80],
                         quote.get('source', ''), '', 'No URL provided', quote.get('needsReview', False)])

print(f"\nFull report saved to: quote_verification_report.csv")

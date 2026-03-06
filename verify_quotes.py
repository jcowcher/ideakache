#!/usr/bin/env python3
"""Verify quote sources by fetching URLs and checking for quote text."""

import re, json, sys, time, csv
from urllib.parse import urlparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

# Extract quotes from index.html
with open('index.html', 'r') as f:
    content = f.read()
m = re.search(r'const QUOTES\s*=\s*(\[.*?\]);', content)
quotes = json.loads(m.group(1))

# Filter to quotes with URLs
with_urls = [q for q in quotes if q.get('url')]
print(f"Checking {len(with_urls)} quotes with URLs...\n")

def normalize(text):
    """Normalize text for fuzzy matching."""
    text = text.lower()
    # Remove smart quotes, apostrophes, dashes
    text = re.sub(r'[\u2018\u2019\u201c\u201d\u2013\u2014]', '', text)
    text = re.sub(r"['\"\-]", '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_keywords(quote_text, min_words=4):
    """Extract significant multi-word phrases from quote for searching."""
    words = quote_text.split()
    # Take a few chunks from the quote to search for
    phrases = []
    if len(words) >= min_words:
        # First chunk
        phrases.append(' '.join(words[:min_words]))
        # Middle chunk
        mid = len(words) // 2
        phrases.append(' '.join(words[mid:mid+min_words]))
        # Last chunk
        phrases.append(' '.join(words[-min_words:]))
    else:
        phrases.append(quote_text)
    return phrases

def check_url(quote):
    """Fetch URL and check if quote text appears on page."""
    url = quote['url']
    qid = quote['id']
    text = quote['text']

    # Skip certain URL types that can't be fetched easily
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Use curl to fetch the page
    try:
        result = subprocess.run(
            ['curl', '-sL', '--max-time', '15', '-A',
             'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
             url],
            capture_output=True, text=True, timeout=20
        )
        page = result.stdout
    except Exception as e:
        return (qid, 'error', f'Fetch failed: {str(e)[:50]}', quote)

    if not page or len(page) < 100:
        return (qid, 'error', 'Empty or very short response', quote)

    # Check for common error pages
    if result.returncode != 0:
        return (qid, 'error', f'curl exit code {result.returncode}', quote)

    # Normalize page content
    page_norm = normalize(page)
    text_norm = normalize(text)

    # Strategy 1: Full quote match (normalized)
    if text_norm in page_norm:
        return (qid, 'found', 'Full quote match', quote)

    # Strategy 2: Check significant phrase chunks
    keywords = get_keywords(text_norm)
    matches = sum(1 for kw in keywords if normalize(kw) in page_norm)

    if matches >= 2:
        return (qid, 'likely', f'{matches}/{len(keywords)} phrase chunks found', quote)
    elif matches == 1:
        return (qid, 'partial', f'1/{len(keywords)} phrase chunks found', quote)

    # Strategy 3: Check if author name appears (at minimum)
    author_norm = normalize(quote['author'])
    author_on_page = author_norm in page_norm

    if not author_on_page:
        return (qid, 'not_found', 'Neither quote nor author found on page', quote)

    return (qid, 'not_found', 'Author found but quote text not found', quote)

# Run checks with thread pool
results = []
print(f"{'ID':<5} {'Status':<12} {'Author':<25} {'Details'}")
print("-" * 100)

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(check_url, q): q for q in with_urls}
    done = 0
    for future in as_completed(futures):
        done += 1
        qid, status, detail, quote = future.result()
        results.append((qid, status, detail, quote))

        # Print non-found results immediately
        if status not in ('found', 'likely'):
            print(f"{qid:<5} {status:<12} {quote['author'][:24]:<25} {detail} | {quote['text'][:60]}...")

        if done % 50 == 0:
            print(f"\n--- Progress: {done}/{len(with_urls)} checked ---\n", file=sys.stderr)

# Summary
print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)

found = [r for r in results if r[1] == 'found']
likely = [r for r in results if r[1] == 'likely']
partial = [r for r in results if r[1] == 'partial']
not_found = [r for r in results if r[1] == 'not_found']
errors = [r for r in results if r[1] == 'error']

print(f"  Found (full match):     {len(found)}")
print(f"  Likely (2+ phrases):    {len(likely)}")
print(f"  Partial (1 phrase):     {len(partial)}")
print(f"  Not found on page:      {len(not_found)}")
print(f"  Errors (fetch failed):  {len(errors)}")

# Write detailed CSV report
with open('quote_verification_report.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['ID', 'Status', 'Author', 'Quote (first 80 chars)', 'Source', 'URL', 'Detail', 'needsReview'])
    for qid, status, detail, quote in sorted(results, key=lambda r: (
        {'not_found': 0, 'error': 1, 'partial': 2, 'likely': 3, 'found': 4}[r[1]], r[0]
    )):
        w.writerow([
            qid, status, quote['author'], quote['text'][:80],
            quote.get('source', ''), quote['url'], detail, quote.get('needsReview', False)
        ])

print(f"\nFull report saved to: quote_verification_report.csv")

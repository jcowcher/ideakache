#!/usr/bin/env python3
"""
One-time migration: extract QUOTES from index.html and insert into Supabase.

Prerequisites:
  1. Run setup.sql in Supabase SQL Editor first
  2. pip install requests (or use built-in urllib)

Usage:
  python migrate_quotes.py
"""

import json
import re
import urllib.request

SUPABASE_URL = "https://rhvtsfybcnvmqtwrfrkm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJodnRzZnliY252bXF0d3JmcmttIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI3NTg3OTAsImV4cCI6MjA4ODMzNDc5MH0.AqIPY64ZrIpAFktO29KhBXH8siWPMgrdh7Cg7IVNGzE"

def extract_quotes(html_path="index.html"):
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the QUOTES array: starts with "const QUOTES = [" and ends with "];"
    match = re.search(r'const QUOTES = (\[.*?\]);', content, re.DOTALL)
    if not match:
        raise ValueError("Could not find QUOTES array in index.html")

    raw = match.group(1)
    # The array uses JS booleans/strings; Python json can parse it since it's valid JSON
    quotes = json.loads(raw)
    print(f"Extracted {len(quotes)} quotes from index.html")
    return quotes


def transform_quote(q):
    """Convert JS camelCase keys to Postgres snake_case columns."""
    verified = q.get("verified", True)
    if isinstance(verified, bool):
        verified = "true" if verified else "false"
    else:
        verified = str(verified)

    return {
        "id": q["id"],
        "text": q["text"],
        "author": q["author"],
        "source": q.get("source", ""),
        "url": q.get("url", ""),
        "verified": verified,
        "verification_notes": q.get("verificationNotes", ""),
        "concepts": q.get("concepts", []),
        "needs_review": q.get("needsReview", False),
    }


def insert_batch(rows):
    """Insert a batch of rows via Supabase REST API."""
    url = f"{SUPABASE_URL}/rest/v1/quotes"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    data = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code}: {body}")


def main():
    quotes = extract_quotes()
    rows = [transform_quote(q) for q in quotes]

    # Insert in batches of 50
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        status = insert_batch(batch)
        print(f"  Inserted {i + len(batch)}/{len(rows)} (HTTP {status})")

    print(f"\nDone! {len(rows)} quotes migrated to Supabase.")


if __name__ == "__main__":
    main()

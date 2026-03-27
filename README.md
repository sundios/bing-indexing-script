# IndexNow Batch Submission Script

A Python CLI tool to submit URLs to IndexNow-compatible search engines (Bing, Yandex) in batches. Reads URLs from a CSV file or sitemap XML.

## Requirements

- Python 3.10+
- `requests` library

```bash
pip install requests
```

## Setup

Before submitting URLs you need an IndexNow API key:

1. Generate a key — any string of 8–128 alphanumeric characters (e.g. `a1b2c3d4e5f6g7h8`)
2. Create a text file named `{your-key}.txt` containing only the key string
3. Host it at your domain root: `https://yourdomain.com/{your-key}.txt`

## Usage

```bash
# From a remote sitemap
python indexnow.py --sitemap https://example.com/sitemap.xml --key YOUR_KEY --host example.com

# From a local sitemap file
python indexnow.py --sitemap sitemap.xml --key YOUR_KEY --host example.com

# From a CSV file
python indexnow.py --csv urls.csv --key YOUR_KEY --host example.com
```

## Options

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--csv FILE` | Yes* | — | Path to CSV file containing URLs |
| `--sitemap FILE_OR_URL` | Yes* | — | Path or URL to sitemap XML |
| `--key KEY` | Yes | — | Your IndexNow API key |
| `--host DOMAIN` | No | auto-detected | Your domain (e.g. `example.com`) |
| `--key-location URL` | No | `https://{host}/{key}.txt` | Full URL to your hosted key file |
| `--column NAME` | No | auto-detected | CSV column name containing URLs |
| `--batch-size N` | No | `200` | URLs per request (max 10,000) |
| `--engine NAME` | No | `indexnow` | Endpoint: `indexnow`, `bing`, or `yandex` |
| `--delay SECONDS` | No | `1.0` | Wait time between batch requests |
| `--dry-run` | No | — | Preview requests without submitting |

*One of `--csv` or `--sitemap` is required.

## Examples

```bash
# Submit from a remote sitemap to Bing in batches of 500
python indexnow.py \
  --sitemap https://example.com/sitemap.xml \
  --key a1b2c3d4e5f6g7h8 \
  --host example.com \
  --engine bing \
  --batch-size 500

# Submit from a CSV export (e.g. Screaming Frog), specifying the URL column
python indexnow.py \
  --csv urls.csv \
  --key a1b2c3d4e5f6g7h8 \
  --host example.com \
  --column "Address"

# Dry run to preview what would be sent without submitting
python indexnow.py \
  --sitemap sitemap.xml \
  --key a1b2c3d4e5f6g7h8 \
  --dry-run
```

## CSV Format

The script auto-detects columns named `url`, `URL`, `address`, `link`, etc. — works out of the box with Screaming Frog and Google Search Console exports. Use `--column` to specify manually if needed.

Example:
```
Address,Status Code,Indexability
https://example.com/page-1,200,Indexable
https://example.com/page-2,200,Indexable
```

## Sitemap Support

- Handles standard sitemaps and **sitemap index files** (recursively fetches all child sitemaps)
- Accepts local files or remote URLs

## Response Codes

| Code | Meaning |
|------|---------|
| 200 | URLs submitted successfully |
| 202 | Accepted — key validation pending |
| 400 | Bad request — check host/key/URL format |
| 403 | Forbidden — key file not found or doesn't match host |
| 422 | URLs don't match host, or key schema mismatch |
| 429 | Too many requests — increase `--delay` |

## Supported Engines

| Name | Endpoint |
|------|----------|
| `indexnow` | `https://api.indexnow.org/IndexNow` |
| `bing` | `https://www.bing.com/indexnow` |
| `yandex` | `https://yandex.com/indexnow` |

Submitting to any one engine notifies all IndexNow-participating search engines.

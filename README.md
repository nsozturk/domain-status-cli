# Domain Status CLI

Written by Enes OZTURK.

A small Python CLI that queries a domain status WebSocket endpoint and exports the latest responses to CSV. It can resume safely after interruption and appends results per base name.

## Features

- WebSocket domain status queries with batch control
- Resume support (skips fully completed bases)
- Incremental CSV appends after each base completes
- Progress output in terminal (uses `tqdm` if installed, otherwise a fallback)
- Optional available-only and priced outputs
- Optional category mapping for priced output

## Requirements

- Python 3.10+
- `websockets` package
- Optional: `tqdm` for nicer progress bars

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install websockets tqdm
```

## Usage

Create a `bases.txt` file with one base per line:

```text
example
mybrand
another
```

Run:

```bash
python ws_domain_export.py --bases bases.txt --out domain_status.csv
```

### Available-only and priced outputs

```bash
python ws_domain_export.py \
  --bases bases.txt \
  --out ws_domain_status.csv \
  --available-out available_domains.csv \
  --prices-json domain_prices.json \
  --category-csv domain_extensions_by_category.csv \
  --priced-out available_domains_priced.csv
```

### Options

- `--bases`: Path to base names file (required)
- `--tlds`: CSV file with a `tld` column (default: `domain_extensions.csv`)
- `--out`: Output CSV path (default: `ws_domain_status.csv`)
- `--batch-size`: Domains per request batch (default: 50)
- `--idle-timeout`: Seconds to wait without messages (default: 5.0)
- `--no-tlds`: Treat bases as full domains (do not append TLDs)
- `--available-out`: Optional CSV path for available-only domains
- `--prices-json`: Optional JSON file with TLD pricing (domain_prices.json format)
- `--category-csv`: Optional CSV file with TLD categories (columns: `category`, `tld`)
- `--priced-out`: Optional CSV path for available domains with prices

## Output

CSV columns for the main output:

- `domain`
- `available`
- `lookupType`
- `extra_json`

CSV columns for the priced output:

- `domain`
- `available`
- `lookupType`
- `extra_json`
- `tld`
- `category`
- `price`
- `regular`
- `renewal`

## License

MIT

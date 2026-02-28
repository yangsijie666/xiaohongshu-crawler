<!-- Generated: 2026-02-27 | Files scanned: 2 | Token estimate: ~400 -->

# Dependencies — rednote-crawler

## Python Runtime
- **Python** 3.10+ (required)
- **Package manager:** uv (not pip)

## Direct Dependencies (pyproject.toml)

| Package | Version | Purpose | Used in |
|---------|---------|---------|---------|
| playwright | ≥1.58.0 | Browser automation (async API) | browser.py, auth.py, search.py, note.py, comment.py |
| playwright-stealth | ≥2.0.2 | Anti-detection patches | stealth.py |
| browserforge | ≥1.2.4 | Real browser fingerprint generation | stealth.py |
| pyyaml | ≥6.0.3 | YAML config loading | main.py |
| openpyxl | ≥3.1.5 | Excel workbook generation | storage.py |

## System Requirements
- Chromium browser (installed via `uv run playwright install chromium`)

## Standard Library Usage

| Module | Used in | Purpose |
|--------|---------|---------|
| asyncio | main.py | Event loop |
| logging | all modules | Structured logging |
| pathlib | browser.py, storage.py, main.py | Path management |
| json | storage.py | JSON serialization |
| re | parser.py | Regex extraction |
| random | main.py, search.py, note.py, comment.py | Human-like delays |
| datetime | storage.py | Timestamps |
| urllib.parse | search.py | URL encoding |

## External Services

| Service | URL | Purpose |
|---------|-----|---------|
| Xiaohongshu | xiaohongshu.com | Target crawl site |
| bot.sannysoft.com | bot.sannysoft.com | Anti-detection validation (scripts only) |

## No Database / No API Server / No Message Queue
This is a standalone CLI tool with file-based output only.

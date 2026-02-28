<!-- Generated: 2026-02-27 | Files scanned: 15 | Token estimate: ~600 -->

# Architecture — rednote-crawler

## System Type
Single Python CLI application — Xiaohongshu (小红书) data crawler

## High-Level Flow

```
config/settings.yaml
        ↓
   main.py (entry)
        ↓
┌─ BrowserManager ──────────────────────────┐
│  Playwright + stealth + browserforge      │
│                                           │
│  ensure_logged_in()                       │
│       ↓                                   │
│  For each keyword:                        │
│    search_notes() → [summaries]           │
│       ↓                                   │
│    fetch_note_details() → [details]       │
│       ├── parse_note_detail()             │
│       └── fetch_comments() → [comments]   │
│       ↓                                   │
│    Storage.save_all()                     │
│       ├── raw/*.json                      │
│       └── processed/*.xlsx (3 sheets)     │
└───────────────────────────────────────────┘
```

## Module Dependency Graph

```
main.py
├── src/browser.py   ← src/stealth.py
├── src/auth.py      ← src/browser.py
├── src/search.py    ← src/browser.py, src/parser.py
├── src/note.py      ← src/browser.py, src/parser.py, src/comment.py
├── src/comment.py   ← src/parser.py
├── src/parser.py    (leaf — no internal deps)
└── src/storage.py   (leaf — no internal deps)
```

## Anti-Detection (Dual Layer)

```
Layer 1: playwright-stealth
  → navigator.webdriver removal
  → automation markers patch

Layer 2: browserforge
  → Chrome 120+ fingerprints (macOS)
  → WebGL / Canvas / viewport spoofing
  → Random per session
```

## Key Directories

```
src/            9 modules, 1744 lines — core crawler logic
scripts/        5 scripts, 808 lines  — verification tests
config/         settings.yaml          — runtime configuration
auth_state/     state.json             — persistent login (gitignored)
data/raw/       *.json                 — raw collection output
data/processed/ *.xlsx                 — formatted Excel output
```

## Total Codebase: ~2,800 lines Python

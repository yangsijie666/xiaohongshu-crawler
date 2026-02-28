<!-- Generated: 2026-02-27 | Files scanned: 10 | Token estimate: ~900 -->

# Backend (Module Pipeline) — rednote-crawler

## Entry Point

```
main.py → load_config() → BrowserManager → ensure_logged_in → crawl_keyword() loop
```

### main.py (205 lines)
```python
load_config(path="config/settings.yaml") → dict
crawl_keyword(bm, keyword, crawler_cfg, delay_cfg, storage) → None
main() → None  # asyncio entry
```

## Core Modules

### src/stealth.py (69 lines) — Fingerprint & anti-detection
```python
build_stealth(user_agent: str) → Stealth
generate_context_options() → dict          # viewport, UA, locale
apply_stealth_to_page(page, stealth) → None
```

### src/browser.py (110 lines) — Browser lifecycle
```python
class BrowserManager:
    __init__(headless=False)
    __aenter__() → BrowserManager           # launch + context
    __aexit__(*_args)                        # close all
    new_page() → Page                       # auto-applies stealth
    save_state()                            # persist auth_state
    context → BrowserContext | None
```
Constants: `AUTH_STATE_PATH = Path("auth_state/state.json")`

### src/auth.py (126 lines) — Login management
```python
is_logged_in(page) → bool                  # checks login-btn selector
wait_for_manual_login(page) → bool          # 120s timeout
ensure_logged_in(bm) → bool                # restore or prompt
```
Constants: `REDNOTE_HOME`, `_LOGIN_BTN_SELECTOR`, `LOGIN_WAIT_TIMEOUT = 120`

### src/search.py (201 lines) — Search collection
```python
search_notes(bm, keyword, max_count=20, ...) → list[dict]
_detect_card_selector(page) → str | None
_scroll_to_load(page, card_selector, target_count, ...) → None
```
Flow: `navigate → detect cards → scroll → parse each card`

### src/note.py (209 lines) — Note detail collection
```python
fetch_note_details(bm, search_results, max_comments=20, ...) → list[dict]
_fetch_single_note(bm, note_id, note_url, ...) → dict | None
_wait_for_content(page) → None
```
Flow: `for each note → goto URL → wait render → parse detail → fetch comments`
Retry: up to `_MAX_RETRIES = 2`

### src/comment.py (185 lines) — Comment collection
```python
fetch_comments(page, note_id, max_count=20, ...) → list[dict]
_detect_comment_selector(page) → str | None
_scroll_comments(page, item_selector, target_count, ...) → None
```
Flow: `detect selector → scroll container → parse each comment`

### src/parser.py (569 lines) — DOM extraction (largest module)
```python
normalize_count(text: str) → int             # "1.2万" → 12000
parse_search_card(card) → dict | None        # 9 fields
parse_note_detail(page, note_id) → dict | None  # 14 fields
parse_comment(comment_el, note_id) → dict | None  # 8 fields
_query_text(page, selectors) → str
_parse_interact_count(page, selectors) → int
```
Pattern: Multi-selector fallback — tries selectors in priority order

### src/storage.py (275 lines) — Data persistence
```python
class Storage:
    __init__(config: dict)
    save_all(keyword, search_results, note_details) → None
```
Output: JSON (raw/) + Excel 3-sheet workbook (processed/)

## Pipeline Chain

```
search_notes(bm, kw)
    → parse_search_card(card)         [per card]
    → list[dict] (9 fields)

fetch_note_details(bm, results)
    → _fetch_single_note(bm, id, url)
        → parse_note_detail(page, id)  [14 fields]
        → fetch_comments(page, id)
            → parse_comment(el, id)    [8 fields per comment]
    → list[dict]

Storage.save_all(kw, search, details)
    → JSON files + XLSX workbook
```

## Verification Scripts

```
scripts/verify_stealth.py  (119 lines) — bot.sannysoft.com test
scripts/verify_login.py    (92 lines)  — login state test
scripts/verify_search.py   (141 lines) — search pipeline test
scripts/verify_note.py     (178 lines) — detail+comment test
scripts/verify_e2e.py      (278 lines) — full integration test
```

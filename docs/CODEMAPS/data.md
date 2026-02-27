<!-- Generated: 2026-02-27 | Files scanned: 3 | Token estimate: ~700 -->

# Data Models & Storage — rednote-crawler

## Data Models

### Search Result (9 fields)
```python
{
    "note_id": str,          # extracted from URL
    "title": str,
    "author": str,
    "author_id": str,        # extracted from profile URL
    "cover_url": str,
    "likes": int,            # normalized ("1.2万" → 12000)
    "note_url": str,         # full URL
    "note_type": "image" | "video",
    "publish_time": str,
}
```

### Note Detail (14 fields)
```python
{
    "note_id": str,
    "title": str,
    "content": str,          # full text body
    "author": str,
    "author_id": str,
    "publish_time": str,
    "likes": int,
    "collects": int,
    "comments_count": int,
    "shares": int,
    "tags": list[str],       # hashtags
    "images": list[str],     # image URLs
    "note_type": "image" | "video",
    "video_url": str,
    "comments": list[dict],  # nested Comment objects
}
```

### Comment (8 fields)
```python
{
    "comment_id": str,
    "note_id": str,          # parent note reference
    "user_name": str,
    "user_id": str,
    "content": str,
    "likes": int,
    "time": str,
    "ip_location": str,
}
```

## Storage Format

### File Structure
```
data/
├── raw/
│   ├── {keyword}_{timestamp}.json          # search results
│   └── notes_{keyword}_{timestamp}.json    # note details + comments
└── processed/
    └── {keyword}_{timestamp}.xlsx          # 3-sheet workbook
```

### JSON Output
- UTF-8 encoding, `ensure_ascii=False`
- 2-space indent
- Includes metadata wrapper with keyword and timestamp

### Excel Output (openpyxl)
```
Sheet 1: "搜索结果" — 8 columns (search fields minus cover_url)
Sheet 2: "笔记详情" — 13 columns (detail fields, tags joined, nested removed)
Sheet 3: "评论数据" — 8 columns (all comments flattened)
```

Excel features:
- Frozen header row (row 1)
- Auto-filter on all columns
- Auto-width with Chinese character handling (×2.1 factor)
- Filename sanitized (invalid chars removed)

### Field Mappings (Excel columns)

```
_SEARCH_FIELDS = [
    ("note_id", "笔记ID"), ("title", "标题"), ("author", "作者"),
    ("author_id", "作者ID"), ("likes", "点赞数"), ("note_url", "链接"),
    ("note_type", "类型"), ("publish_time", "发布时间"),
]

_NOTE_FIELDS = [
    ("note_id", "笔记ID"), ("title", "标题"), ("content", "正文"),
    ("author", "作者"), ("author_id", "作者ID"), ("publish_time", "发布时间"),
    ("likes", "点赞数"), ("collects", "收藏数"), ("comments_count", "评论数"),
    ("shares", "分享数"), ("tags", "标签"), ("note_type", "类型"),
    ("video_url", "视频链接"),
]

_COMMENT_FIELDS = [
    ("note_id", "所属笔记"), ("comment_id", "评论ID"), ("user_name", "用户名"),
    ("user_id", "用户ID"), ("content", "评论内容"), ("likes", "点赞数"),
    ("time", "时间"), ("ip_location", "IP属地"),
]
```

## Configuration (config/settings.yaml)

```yaml
crawler:
  keywords: [...]             # search terms
  max_notes_per_keyword: 20
  max_comments_per_note: 20
  scroll_pause: 1.5

delay:
  between_notes: [2, 5]       # random range (seconds)
  between_searches: [3, 8]
  scroll_interval: [1, 3]

browser:
  headless: false

storage:
  output_dir: "data"
  save_raw_json: true
  save_xlsx: true
```

## Persistent State

```
auth_state/state.json — Playwright storage_state (cookies + localStorage)
                        Gitignored, auto-created on first login
```

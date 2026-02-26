"""
数据存储模块

职责：
  - 将采集结果持久化到本地文件
  - 支持两种格式：JSON（原始完整数据）和 CSV（扁平化表格）
  - 按关键词和时间戳组织文件命名，避免覆盖

目录结构：
    data/
    ├── raw/
    │   └── {keyword}_{timestamp}.json   # 原始完整数据
    └── processed/
        └── search_results_{keyword}.csv  # 搜索结果摘要表

用法：
    storage = Storage(config["storage"])
    storage.save_search_results("Python教程", results)
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# CSV 导出字段及顺序
_SEARCH_CSV_FIELDS = [
    "note_id",
    "title",
    "author",
    "author_id",
    "likes",
    "note_type",
    "note_url",
    "publish_time",
]


class Storage:
    """本地数据存储管理器。

    根据配置决定是否写入 JSON / CSV，负责目录创建和文件命名。
    """

    def __init__(self, config: dict) -> None:
        """初始化存储配置。

        Args:
            config: settings.yaml 中 storage 节点的字典，包含：
                - output_dir (str): 输出根目录，默认 "data"
                - save_raw_json (bool): 是否保存原始 JSON
                - save_csv (bool): 是否保存 CSV
        """
        self._root = Path(config.get("output_dir", "data"))
        self._save_json: bool = config.get("save_raw_json", True)
        self._save_csv: bool = config.get("save_csv", True)
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """确保输出目录存在。"""
        (self._root / "raw").mkdir(parents=True, exist_ok=True)
        (self._root / "processed").mkdir(parents=True, exist_ok=True)

    def save_search_results(self, keyword: str, results: list[dict]) -> None:
        """将搜索结果列表保存到本地文件。

        Args:
            keyword: 搜索关键词（用于文件命名）
            results: parse_search_card() 返回的字典列表

        副作用：
            - 若 save_raw_json=True：写入 data/raw/{keyword}_{timestamp}.json
            - 若 save_csv=True：追加写入 data/processed/search_results_{keyword}.csv
        """
        if not results:
            logger.warning("采集结果为空，跳过存储（keyword=%s）", keyword)
            return

        # 安全化关键词用于文件名（替换路径分隔符等特殊字符）
        safe_keyword = _sanitize_filename(keyword)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self._save_json:
            self._write_json(safe_keyword, timestamp, keyword, results)

        if self._save_csv:
            self._write_csv(safe_keyword, results)

    def _write_json(
        self,
        safe_keyword: str,
        timestamp: str,
        keyword: str,
        results: list[dict],
    ) -> None:
        """写入原始 JSON 文件。"""
        json_path = self._root / "raw" / f"{safe_keyword}_{timestamp}.json"
        payload = {
            "keyword": keyword,
            "crawled_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(results),
            "results": results,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("JSON 已写入：%s（%d 条）", json_path, len(results))

    def _write_csv(self, safe_keyword: str, results: list[dict]) -> None:
        """追加写入 CSV 文件（文件不存在则创建并写表头）。"""
        csv_path = self._root / "processed" / f"search_results_{safe_keyword}.csv"
        file_exists = csv_path.exists()

        with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
            # utf-8-sig 让 Excel 正确识别中文
            writer = csv.DictWriter(f, fieldnames=_SEARCH_CSV_FIELDS, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerows(results)

        logger.info("CSV 已写入：%s（%d 条）", csv_path, len(results))


def _sanitize_filename(name: str) -> str:
    """将字符串转化为安全的文件名（去除 / \\ : * ? " < > | 等特殊字符）。

    Args:
        name: 原始字符串

    Returns:
        安全的文件名字符串（保留中文、字母、数字、下划线、连字符）
    """
    import re
    # 替换不安全字符为下划线
    safe = re.sub(r'[\\/:*?"<>|\s]', "_", name)
    # 合并连续下划线
    safe = re.sub(r"_+", "_", safe)
    return safe.strip("_") or "unnamed"

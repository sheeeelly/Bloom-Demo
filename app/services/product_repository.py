"""
选品数据访问层。

一期通过 SeedFileProductRepository 读取本地种子文件（data/seed_products.json）。
二期接入真实爬虫结果后，新增 CrawledProductRepository（读取爬虫落库/落文件的结果），
在 main.py 中切换依赖注入即可，不影响路由和前端。
"""
from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config
from app.schemas.product import SelectionResponse


class ProductRepository(ABC):
    """选品数据访问接口，屏蔽具体数据来源（种子文件 / 数据库 / 爬虫产出）。"""

    @abstractmethod
    def get_selection(self) -> SelectionResponse:
        """返回目标竞品 URL 及其商品列表。"""
        raise NotImplementedError


class SeedFileProductRepository(ProductRepository):
    """一期实现：读取本地占位种子数据文件。"""

    def __init__(self, seed_path: Path | None = None):
        self.seed_path = seed_path or config.SEED_DATA_PATH

    def get_selection(self) -> SelectionResponse:
        if not self.seed_path.exists():
            raise FileNotFoundError(f"种子数据文件不存在：{self.seed_path}")
        if not self.seed_path.is_file():
            # SEED_DATA_PATH 配置错误时（如被误置空导致解析为当前目录），
            # exists() 为 True 但并非文件，需在此显式识别为“文件不存在”，
            # 避免 read_text() 抛出 IsADirectoryError 导致未捕获的 500。
            raise FileNotFoundError(f"种子数据路径不是文件：{self.seed_path}")
        raw = json.loads(self.seed_path.read_text(encoding="utf-8"))
        return SelectionResponse(**raw)


def get_product_repository() -> ProductRepository:
    """FastAPI 依赖注入入口，二期切换真实数据源时只需改动这里。"""
    return SeedFileProductRepository()

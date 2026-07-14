"""数据存储层 - SQLite CRUD操作

使用标准库 sqlite3 实现饮食记录的持久化存储，
不依赖 ORM，所有查询参数化以防 SQL 注入。
"""

import os
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB_PATH = "data/foodlog.db"

# 建表 SQL，与文档中定义的 schema 保持一致
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    time TEXT,
    meal_type TEXT NOT NULL,
    source TEXT NOT NULL,
    food_name TEXT NOT NULL,
    food_category TEXT,
    staple_food TEXT,
    meat_type TEXT,
    vegetable_type TEXT,
    taste TEXT,
    calories REAL,
    protein REAL,
    carbs REAL,
    fat REAL,
    price REAL,
    tags TEXT,
    notes TEXT,
    screenshot_path TEXT,
    ai_raw_response TEXT,
    status TEXT DEFAULT 'confirmed',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# meals 表中除 id 外的所有列，用于 INSERT/SELECT 时保持顺序一致
_MEAL_COLUMNS = [
    "date",
    "time",
    "meal_type",
    "source",
    "food_name",
    "food_category",
    "staple_food",
    "meat_type",
    "vegetable_type",
    "taste",
    "calories",
    "protein",
    "carbs",
    "fat",
    "price",
    "tags",
    "notes",
    "screenshot_path",
    "ai_raw_response",
    "status",
    "created_at",
    "updated_at",
]


@dataclass
class Meal:
    """饮食记录数据类"""

    date: str
    meal_type: str
    source: str
    food_name: str
    id: Optional[int] = None
    time: Optional[str] = None
    food_category: Optional[str] = None
    staple_food: Optional[str] = None
    meat_type: Optional[str] = None
    vegetable_type: Optional[str] = None
    taste: Optional[str] = None
    calories: Optional[float] = None
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    price: Optional[float] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    screenshot_path: Optional[str] = None
    ai_raw_response: Optional[str] = None
    status: str = "confirmed"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转为字典，包含所有字段（含 None）"""
        return asdict(self)

    @classmethod
    def from_db_row(cls, row) -> "Meal":
        """从数据库行（sqlite3.Row 或类似对象）构造 Meal"""
        return cls(
            id=row["id"],
            date=row["date"],
            time=row["time"],
            meal_type=row["meal_type"],
            source=row["source"],
            food_name=row["food_name"],
            food_category=row["food_category"],
            staple_food=row["staple_food"],
            meat_type=row["meat_type"],
            vegetable_type=row["vegetable_type"],
            taste=row["taste"],
            calories=row["calories"],
            protein=row["protein"],
            carbs=row["carbs"],
            fat=row["fat"],
            price=row["price"],
            tags=row["tags"],
            notes=row["notes"],
            screenshot_path=row["screenshot_path"],
            ai_raw_response=row["ai_raw_response"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class Database:
    """SQLite 数据库封装，提供 meals 表的 CRUD 操作"""

    def __init__(self, db_path: str = None):
        """初始化数据库连接，自动建表。

        优先级：显式参数 > 环境变量 DATABASE_PATH > DEFAULT_DB_PATH。
        若目录不存在则自动创建。
        """
        if db_path is None:
            db_path = os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)

        self.db_path = str(db_path)

        # 确保目录存在（如果路径中包含目录）
        parent = os.path.dirname(self.db_path)
        if parent:
            Path(parent).mkdir(parents=True, exist_ok=True)

        # 连接数据库；check_same_thread=False 以便在 Web/CLI 多场景使用
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # 启用外键约束（虽然当前没有外键，保持良好习惯）
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    def _create_tables(self) -> None:
        """建表（IF NOT EXISTS）"""
        self.conn.execute(_CREATE_TABLE_SQL)
        self.conn.commit()

    # ---------- 内部工具 ----------
    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat()

    # ---------- 增删改查 ----------
    def insert_meal(self, meal: Meal) -> int:
        """插入一条记录，返回新记录的 id。

        自动填充 created_at 和 updated_at（若未提供）。
        """
        now = self._now_iso()
        if not meal.created_at:
            meal.created_at = now
        if not meal.updated_at:
            meal.updated_at = now

        values = [getattr(meal, col) for col in _MEAL_COLUMNS]
        placeholders = ", ".join(["?"] * len(_MEAL_COLUMNS))
        col_list = ", ".join(_MEAL_COLUMNS)
        sql = f"INSERT INTO meals ({col_list}) VALUES ({placeholders})"
        cursor = self.conn.execute(sql, values)
        self.conn.commit()
        meal_id = cursor.lastrowid
        return int(meal_id) if meal_id is not None else 0

    def get_meal_by_id(self, meal_id: int) -> Optional[Meal]:
        """根据 id 获取单条记录，找不到返回 None"""
        cursor = self.conn.execute(
            "SELECT * FROM meals WHERE id = ?", (meal_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Meal.from_db_row(row)

    def get_meals_by_date(self, date_str: str) -> List[Meal]:
        """获取某天的所有记录，按 time 升序（无 time 的排后）"""
        cursor = self.conn.execute(
            "SELECT * FROM meals WHERE date = ? ORDER BY time IS NULL, time ASC, id ASC",
            (date_str,),
        )
        return [Meal.from_db_row(r) for r in cursor.fetchall()]

    def get_meals_by_date_range(
        self, start_date: str, end_date: str
    ) -> List[Meal]:
        """获取日期范围内的所有记录（闭区间），按 date, time 升序"""
        cursor = self.conn.execute(
            "SELECT * FROM meals WHERE date >= ? AND date <= ? "
            "ORDER BY date ASC, time IS NULL, time ASC, id ASC",
            (start_date, end_date),
        )
        return [Meal.from_db_row(r) for r in cursor.fetchall()]

    def get_all_meals(self, limit: int = 100, offset: int = 0) -> List[Meal]:
        """获取所有记录（分页），按 created_at 倒序"""
        cursor = self.conn.execute(
            "SELECT * FROM meals ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [Meal.from_db_row(r) for r in cursor.fetchall()]

    def update_meal(self, meal_id: int, updates: dict) -> bool:
        """更新记录，updates 是需要更新的字段字典。

        自动更新 updated_at。返回是否更新成功（是否有行被修改）。
        不允许更新 id。
        """
        if not updates:
            # 即使没有更新字段，也刷新 updated_at
            updates = {}
        # 过滤掉 id 与 None 值以外的非法字段，仅允许表内列
        allowed = set(_MEAL_COLUMNS)
        clean: Dict[str, Any] = {}
        for k, v in updates.items():
            if k == "id":
                continue
            if k in allowed:
                clean[k] = v
        # 强制刷新 updated_at
        clean["updated_at"] = self._now_iso()
        if not clean:
            return False

        set_clause = ", ".join([f"{col} = ?" for col in clean.keys()])
        values = list(clean.values()) + [meal_id]
        sql = f"UPDATE meals SET {set_clause} WHERE id = ?"
        cursor = self.conn.execute(sql, values)
        self.conn.commit()
        return cursor.rowcount > 0

    def delete_meal(self, meal_id: int) -> bool:
        """删除记录，返回是否删除成功"""
        cursor = self.conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_all_tags(self) -> List[Dict[str, Any]]:
        """获取所有标签及其使用次数和对应支出。

        解析 tags 字段（逗号分隔，忽略空白），返回形如：
        [{"tag": "咖啡", "count": 3, "total_price": 95.0}, ...]
        按 count 倒序、tag 升序排序。
        """
        cursor = self.conn.execute(
            "SELECT tags, price FROM meals WHERE tags IS NOT NULL AND tags != ''"
        )
        agg: Dict[str, Dict[str, Any]] = {}
        for row in cursor.fetchall():
            tags_raw = row["tags"]
            price = row["price"] if row["price"] is not None else 0.0
            for tag in tags_raw.split(","):
                tag = tag.strip()
                if not tag:
                    continue
                entry = agg.setdefault(tag, {"tag": tag, "count": 0, "total_price": 0.0})
                entry["count"] += 1
                entry["total_price"] += float(price)

        result = list(agg.values())
        # count 倒序，tag 升序
        result.sort(key=lambda x: (-x["count"], x["tag"]))
        # 四舍五入 total_price 到 2 位小数，避免浮点误差
        for item in result:
            item["total_price"] = round(item["total_price"], 2)
        return result

    def get_meal_count(self) -> int:
        """获取总记录数"""
        cursor = self.conn.execute("SELECT COUNT(*) AS cnt FROM meals")
        row = cursor.fetchone()
        return int(row["cnt"]) if row else 0

    def get_confirmed_meals(self) -> List[Meal]:
        """获取所有已确认的记录（用于推荐），按 created_at 倒序"""
        cursor = self.conn.execute(
            "SELECT * FROM meals WHERE status = 'confirmed' "
            "ORDER BY created_at DESC, id DESC"
        )
        return [Meal.from_db_row(r) for r in cursor.fetchall()]

    def close(self):
        """关闭数据库连接"""
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

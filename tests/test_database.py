"""数据库层测试

使用 pytest 的 tmp_path fixture，每个测试使用独立的临时数据库文件，
互不干扰。覆盖建表、增删改查、日期范围查询、标签统计、
Meal dataclass 序列化反序列化等场景。
"""

import sqlite3

import pytest

from foodlog.database import Database, Meal


# ---------- 公共 fixture ----------
@pytest.fixture
def db(tmp_path):
    """每个测试一个临时数据库"""
    db_path = tmp_path / "test_foodlog.db"
    instance = Database(str(db_path))
    yield instance
    instance.close()


def _make_meal(**overrides) -> Meal:
    """构造一条测试 Meal，默认值可被 overrides 覆盖"""
    defaults = dict(
        date="2026-07-13",
        meal_type="breakfast",
        source="takeout",
        food_name="拿铁咖啡",
    )
    defaults.update(overrides)
    return Meal(**defaults)


# ---------- 测试 ----------
def test_create_database(tmp_path):
    """测试数据库创建和建表"""
    db_path = tmp_path / "subdir" / "foodlog.db"
    # 目录不存在时应自动创建
    db = Database(str(db_path))
    try:
        assert db_path.exists(), "数据库文件应被创建"

        # meals 表应存在
        cur = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meals'"
        )
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["name"] == "meals"

        # 校验关键列存在
        cur = db.conn.execute("PRAGMA table_info(meals)")
        col_names = {row["name"] for row in cur.fetchall()}
        expected = {
            "id", "date", "time", "meal_type", "source", "food_name",
            "food_category", "calories", "protein", "carbs", "fat", "price",
            "tags", "notes", "screenshot_path", "ai_raw_response", "status",
            "created_at", "updated_at",
        }
        assert expected.issubset(col_names), f"缺少列: {expected - col_names}"

        # 初始记录数为 0
        assert db.get_meal_count() == 0
    finally:
        db.close()


def test_insert_and_get(db):
    """测试插入和查询"""
    meal = _make_meal(
        time="08:30",
        food_category="饮品",
        calories=180.0,
        protein=4.0,
        carbs=24.0,
        fat=8.0,
        price=28.0,
        tags="咖啡",
        notes="早餐",
    )
    meal_id = db.insert_meal(meal)
    assert meal_id > 0, "插入应返回正整数 id"

    # get_meal_by_id
    fetched = db.get_meal_by_id(meal_id)
    assert fetched is not None
    assert fetched.id == meal_id
    assert fetched.date == "2026-07-13"
    assert fetched.meal_type == "breakfast"
    assert fetched.source == "takeout"
    assert fetched.food_name == "拿铁咖啡"
    assert fetched.calories == 180.0
    assert fetched.tags == "咖啡"
    # created_at / updated_at 应被自动填充
    assert fetched.created_at is not None
    assert fetched.updated_at is not None

    # get_meals_by_date
    meals_today = db.get_meals_by_date("2026-07-13")
    assert len(meals_today) == 1
    assert meals_today[0].id == meal_id

    # 不存在的 id
    assert db.get_meal_by_id(99999) is None
    # 不存在的日期
    assert db.get_meals_by_date("1999-01-01") == []

    # get_meal_count
    assert db.get_meal_count() == 1


def test_update_meal(db):
    """测试更新"""
    meal = _make_meal(calories=300.0, price=20.0, status="draft")
    meal_id = db.insert_meal(meal)

    original = db.get_meal_by_id(meal_id)
    assert original.status == "draft"

    ok = db.update_meal(meal_id, {"calories": 450.0, "status": "confirmed", "notes": "已确认"})
    assert ok is True

    updated = db.get_meal_by_id(meal_id)
    assert updated.calories == 450.0
    assert updated.status == "confirmed"
    assert updated.notes == "已确认"
    # 未更新的字段保持不变
    assert updated.food_name == "拿铁咖啡"
    # updated_at 应被刷新
    assert updated.updated_at >= original.updated_at

    # 更新不存在的 id 应返回 False
    assert db.update_meal(99999, {"calories": 1.0}) is False

    # id 字段不应被更新（应被忽略）
    db.update_meal(meal_id, {"id": 8888, "food_name": "改后"})
    again = db.get_meal_by_id(meal_id)
    assert again.id == meal_id
    assert again.food_name == "改后"


def test_delete_meal(db):
    """测试删除"""
    meal = _make_meal()
    meal_id = db.insert_meal(meal)
    assert db.get_meal_count() == 1

    assert db.delete_meal(meal_id) is True
    assert db.get_meal_count() == 0
    assert db.get_meal_by_id(meal_id) is None

    # 重复删除返回 False
    assert db.delete_meal(meal_id) is False


def test_get_by_date_range(db):
    """测试日期范围查询（闭区间）"""
    dates = ["2026-07-10", "2026-07-11", "2026-07-12", "2026-07-13", "2026-07-14"]
    for i, d in enumerate(dates):
        db.insert_meal(_make_meal(date=d, food_name=f"meal-{i}"))

    # 闭区间 [07-11, 07-13]
    ranged = db.get_meals_by_date_range("2026-07-11", "2026-07-13")
    assert len(ranged) == 3
    returned_dates = [m.date for m in ranged]
    assert returned_dates == ["2026-07-11", "2026-07-12", "2026-07-13"]

    # 同一日期起止
    single = db.get_meals_by_date_range("2026-07-12", "2026-07-12")
    assert len(single) == 1
    assert single[0].date == "2026-07-12"

    # 范围外
    empty = db.get_meals_by_date_range("2026-01-01", "2026-01-02")
    assert empty == []

    # 全部
    all_range = db.get_meals_by_date_range("2026-07-10", "2026-07-14")
    assert len(all_range) == 5


def test_get_all_tags(db):
    """测试标签统计：count 与 total_price 聚合正确"""
    # 咖啡出现 3 次，价格分别为 28, 30, 32 -> count=3, total_price=90
    db.insert_meal(_make_meal(food_name="拿铁", price=28.0, tags="咖啡"))
    db.insert_meal(_make_meal(food_name="美式", price=30.0, tags="咖啡,早餐"))
    db.insert_meal(_make_meal(food_name="可颂咖啡", price=32.0, tags="咖啡"))
    # 奶茶 2 次
    db.insert_meal(_make_meal(food_name="珍珠奶茶", price=22.0, tags="奶茶"))
    db.insert_meal(_make_meal(food_name="芋圆奶茶", price=24.0, tags="奶茶"))
    # 无标签 / None 标签应被忽略
    db.insert_meal(_make_meal(food_name="米饭", price=5.0, tags=None))
    db.insert_meal(_make_meal(food_name="面包", price=6.0, tags=""))
    # 无 price 的记录，price 视为 0
    db.insert_meal(_make_meal(food_name="赠送咖啡", price=None, tags="咖啡"))

    tags = db.get_all_tags()
    tag_map = {t["tag"]: t for t in tags}

    assert "咖啡" in tag_map
    assert tag_map["咖啡"]["count"] == 4  # 3 + 1 赠送
    assert tag_map["咖啡"]["total_price"] == pytest.approx(28 + 30 + 32 + 0)

    assert tag_map["奶茶"]["count"] == 2
    assert tag_map["奶茶"]["total_price"] == pytest.approx(22 + 24)

    assert tag_map["早餐"]["count"] == 1
    assert tag_map["早餐"]["total_price"] == pytest.approx(30.0)

    # 不应出现空标签
    assert "" not in tag_map

    # 结果应为列表字典，包含 tag / count / total_price 三键
    for t in tags:
        assert set(t.keys()) == {"tag", "count", "total_price"}


def test_meal_dataclass():
    """测试 Meal 的序列化 / 反序列化"""
    meal = Meal(
        id=42,
        date="2026-07-13",
        time="08:30",
        meal_type="breakfast",
        source="home",
        food_name="燕麦牛奶",
        food_category="主食",
        calories=350.0,
        protein=18.0,
        carbs=42.0,
        fat=10.0,
        price=5.0,
        tags="健康,早餐",
        notes="自炊",
        screenshot_path=None,
        ai_raw_response=None,
        status="confirmed",
        created_at="2026-07-13T08:30:00",
        updated_at="2026-07-13T08:30:00",
    )

    # to_dict
    d = meal.to_dict()
    assert d["id"] == 42
    assert d["date"] == "2026-07-13"
    assert d["food_name"] == "燕麦牛奶"
    assert d["calories"] == 350.0
    assert d["tags"] == "健康,早餐"
    assert d["status"] == "confirmed"
    # 字段完整
    assert "screenshot_path" in d
    assert "ai_raw_response" in d

    # from_db_row：用 sqlite3.Row 模拟数据库行
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # 构造一个与表结构一致的行用于 from_db_row 测试
    cols = [
        "id", "date", "time", "meal_type", "source", "food_name",
        "food_category", "staple_food", "meat_type", "vegetable_type", "taste",
        "calories", "protein", "carbs", "fat", "price",
        "tags", "notes", "screenshot_path", "ai_raw_response", "status",
        "created_at", "updated_at",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    conn.execute(f"CREATE TABLE meals ({', '.join(cols)})")
    conn.execute(
        f"INSERT INTO meals VALUES ({placeholders})",
        tuple(d[c] for c in cols),
    )
    row = conn.execute("SELECT * FROM meals").fetchone()
    restored = Meal.from_db_row(row)
    conn.close()

    assert restored.id == meal.id
    assert restored.date == meal.date
    assert restored.meal_type == meal.meal_type
    assert restored.food_name == meal.food_name
    assert restored.calories == meal.calories
    assert restored.tags == meal.tags
    assert restored.created_at == meal.created_at

    # 往返一致性：to_dict 后字段对齐
    assert restored.to_dict() == d


def test_context_manager_and_pagination(db):
    """测试上下文管理器与分页查询"""
    for i in range(5):
        db.insert_meal(_make_meal(food_name=f"meal-{i}"))

    # 分页：第一页 2 条
    page1 = db.get_all_meals(limit=2, offset=0)
    assert len(page1) == 2
    # 第二页
    page2 = db.get_all_meals(limit=2, offset=2)
    assert len(page2) == 2
    # 第三页只剩 1 条
    page3 = db.get_all_meals(limit=2, offset=4)
    assert len(page3) == 1
    # 无重复
    ids = {m.id for m in page1 + page2 + page3}
    assert len(ids) == 5

    # 上下文管理器
    tmp_path_str = db.db_path
    with Database(tmp_path_str) as ctx_db:
        assert ctx_db.get_meal_count() == 5
    # 退出后连接应已关闭（conn 为 None）
    assert ctx_db.conn is None


def test_get_confirmed_meals(db):
    """测试已确认记录查询"""
    db.insert_meal(_make_meal(food_name="confirmed1", status="confirmed"))
    db.insert_meal(_make_meal(food_name="draft1", status="draft"))
    db.insert_meal(_make_meal(food_name="confirmed2", status="confirmed"))

    confirmed = db.get_confirmed_meals()
    assert len(confirmed) == 2
    for m in confirmed:
        assert m.status == "confirmed"
    names = {m.food_name for m in confirmed}
    assert names == {"confirmed1", "confirmed2"}


def test_auto_timestamps(db):
    """测试 created_at / updated_at 自动填充"""
    meal = _make_meal()  # 不提供 created_at / updated_at
    assert meal.created_at is None
    assert meal.updated_at is None

    meal_id = db.insert_meal(meal)
    fetched = db.get_meal_by_id(meal_id)
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.created_at == meal.created_at  # insert 内部已回填到对象


def test_env_path_priority(tmp_path, monkeypatch):
    """测试未传路径时从 DATABASE_PATH 环境变量读取"""
    env_path = tmp_path / "env.db"
    monkeypatch.setenv("DATABASE_PATH", str(env_path))
    db = Database()  # 不传参
    try:
        assert db.db_path == str(env_path)
        # 插入并读取，验证可用
        mid = db.insert_meal(_make_meal())
        assert db.get_meal_by_id(mid) is not None
    finally:
        db.close()

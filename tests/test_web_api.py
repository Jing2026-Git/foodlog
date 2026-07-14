"""Web API 测试

使用 FastAPI 的 TestClient 测试所有 API 接口。
通过 monkeypatch DATABASE_PATH 环境变量实现测试隔离，
每个测试使用独立的临时数据库文件。

覆盖接口：
- GET    /api/meals           列表 / 日期过滤
- GET    /api/meals/{id}      单条 / 404
- POST   /api/meals           添加
- PUT    /api/meals/{id}      更新
- DELETE /api/meals/{id}      删除
- GET    /api/today           今日统计
- GET    /api/week            周报
- GET    /api/recommend       推荐
- POST   /api/search          搜索
- GET    /api/init-status     初始化状态
- POST   /api/init            初始化 / 重置
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from foodlog.database import Database, Meal
from foodlog.web.app import app


# ----------------------------------------------------------------------
# 公共 fixture
# ----------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """设置临时数据库路径到 DATABASE_PATH 环境变量，并返回该路径。

    Database() / stats / recommender / app 内部均读取此环境变量，
    从而实现测试与正式数据库的隔离。
    """
    path = str(tmp_path / "test_web.db")
    monkeypatch.setenv("DATABASE_PATH", path)
    return path


@pytest.fixture
def client(db_path):
    """提供一个使用临时数据库的 TestClient"""
    with TestClient(app) as c:
        yield c


# ----------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------


def _today() -> str:
    return date.today().isoformat()


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _make_meal(**overrides) -> Meal:
    """构造一条测试 Meal，默认值可被 overrides 覆盖"""
    defaults = dict(
        date=_today(),
        meal_type="lunch",
        source="takeout",
        food_name="测试餐",
        food_category="主食",
        calories=500.0,
        protein=20.0,
        carbs=60.0,
        fat=15.0,
        price=30.0,
        tags=None,
        status="confirmed",
    )
    defaults.update(overrides)
    return Meal(**defaults)


def _insert_meal(db, **overrides) -> int:
    """向数据库插入一条 Meal，返回 id"""
    return db.insert_meal(_make_meal(**overrides))


# ----------------------------------------------------------------------
# 测试
# ----------------------------------------------------------------------


def test_get_meals(client, db_path):
    """测试获取记录列表"""
    db = Database()
    _insert_meal(db, food_name="餐1")
    _insert_meal(db, food_name="餐2")
    _insert_meal(db, food_name="餐3")
    db.close()

    response = client.get("/api/meals")
    assert response.status_code == 200
    data = response.json()
    assert "meals" in data
    assert "total" in data
    assert data["total"] == 3
    assert len(data["meals"]) == 3
    # 每条 meal 都应是 dict
    for meal in data["meals"]:
        assert isinstance(meal, dict)
        assert "id" in meal
        assert "food_name" in meal
        assert "date" in meal


def test_get_meals_by_date(client, db_path):
    """测试按日期过滤"""
    db = Database()
    _insert_meal(db, date="2026-07-10", food_name="A")
    _insert_meal(db, date="2026-07-11", food_name="B")
    _insert_meal(db, date="2026-07-11", food_name="C")
    _insert_meal(db, date="2026-07-12", food_name="D")
    db.close()

    # 按单日过滤
    resp = client.get("/api/meals", params={"date": "2026-07-11"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    names = {m["food_name"] for m in data["meals"]}
    assert names == {"B", "C"}

    # 按日期范围过滤
    resp = client.get(
        "/api/meals",
        params={"start_date": "2026-07-11", "end_date": "2026-07-12"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    names = {m["food_name"] for m in data["meals"]}
    assert names == {"B", "C", "D"}

    # 仅 start_date
    resp = client.get("/api/meals", params={"start_date": "2026-07-12"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # 状态过滤
    db = Database()
    _insert_meal(db, food_name="draft1", status="draft")
    db.close()
    resp = client.get("/api/meals", params={"status": "draft"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["meals"][0]["status"] == "draft"


def test_get_meal_by_id(client, db_path):
    """测试获取单条记录"""
    db = Database()
    meal_id = _insert_meal(
        db,
        food_name="拿铁咖啡",
        food_category="饮品",
        calories=180.0,
        price=28.0,
        tags="咖啡",
    )
    db.close()

    resp = client.get(f"/api/meals/{meal_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "meal" in data
    meal = data["meal"]
    assert meal["id"] == meal_id
    assert meal["food_name"] == "拿铁咖啡"
    assert meal["food_category"] == "饮品"
    assert meal["calories"] == 180.0
    assert meal["tags"] == "咖啡"


def test_get_meal_not_found(client, db_path):
    """测试获取不存在的记录返回 404"""
    resp = client.get("/api/meals/99999")
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data


def test_create_meal(client, db_path):
    """测试手动添加记录"""
    payload = {
        "date": _today(),
        "time": "12:30",
        "meal_type": "lunch",
        "source": "takeout",
        "food_name": "黄焖鸡米饭",
        "food_category": "主食",
        "calories": 640,
        "protein": 30,
        "carbs": 88,
        "fat": 18,
        "price": 30,
        "tags": "辣",
        "notes": "外卖",
    }
    resp = client.post("/api/meals", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "meal_id" in data
    assert data["meal_id"] > 0
    assert data["meal"]["food_name"] == "黄焖鸡米饭"
    assert data["meal"]["calories"] == 640
    assert data["meal"]["status"] == "confirmed"

    # 必填字段缺失应返回 422
    resp = client.post(
        "/api/meals",
        json={"date": _today(), "meal_type": "lunch"},  # 缺 source / food_name
    )
    assert resp.status_code == 422


def test_update_meal(client, db_path):
    """测试更新记录"""
    db = Database()
    meal_id = _insert_meal(db, food_name="原餐", calories=300.0, status="draft")
    db.close()

    resp = client.put(
        f"/api/meals/{meal_id}",
        json={"food_name": "改后餐", "calories": 500.0, "status": "confirmed"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["meal"]["food_name"] == "改后餐"
    assert data["meal"]["calories"] == 500.0
    assert data["meal"]["status"] == "confirmed"

    # 更新不存在的记录返回 404
    resp = client.put("/api/meals/99999", json={"calories": 100})
    assert resp.status_code == 404


def test_delete_meal(client, db_path):
    """测试删除记录"""
    db = Database()
    meal_id = _insert_meal(db, food_name="待删除")
    db.close()

    resp = client.delete(f"/api/meals/{meal_id}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 删除后查应 404
    resp = client.get(f"/api/meals/{meal_id}")
    assert resp.status_code == 404

    # 重复删除返回 404
    resp = client.delete(f"/api/meals/{meal_id}")
    assert resp.status_code == 404


def test_get_today(client, db_path):
    """测试今日统计"""
    db = Database()
    _insert_meal(
        db,
        date=_today(),
        meal_type="breakfast",
        food_name="燕麦牛奶",
        calories=400.0,
        protein=15.0,
        price=8.0,
    )
    _insert_meal(
        db,
        date=_today(),
        meal_type="lunch",
        food_name="鸡腿饭",
        calories=680.0,
        protein=32.0,
        price=32.0,
    )
    db.close()

    resp = client.get("/api/today")
    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == _today()
    assert data["meal_count"] == 2
    assert data["total_calories"] == 1080.0
    assert data["total_price"] == 40.0
    # meals 应是 dict 列表（而非 dataclass）
    assert isinstance(data["meals"], list)
    for m in data["meals"]:
        assert isinstance(m, dict)
        assert "id" in m
    # by_meal_type 中也有 items（Meal 列表），同样应被序列化为 dict
    assert isinstance(data["by_meal_type"], dict)
    for mt_data in data["by_meal_type"].values():
        for item in mt_data.get("items", []):
            assert isinstance(item, dict)


def test_get_week(client, db_path):
    """测试周报统计"""
    # 本周一
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    db = Database()
    # 周一与周三各插入一条
    _insert_meal(
        db,
        date=monday.isoformat(),
        food_name="周一餐",
        calories=500.0,
        price=20.0,
    )
    _insert_meal(
        db,
        date=(monday + timedelta(days=2)).isoformat(),
        food_name="周三餐",
        calories=600.0,
        price=30.0,
    )
    db.close()

    resp = client.get("/api/week")
    assert resp.status_code == 200
    data = resp.json()
    assert data["week_start"] == monday.isoformat()
    # 7 天
    assert len(data["daily_data"]) == 7
    assert data["meal_count"] == 2
    # daily_data 中没有 Meal 对象，但 anomalies 中可能有（meal 字段）
    for anom in data.get("anomalies", []):
        # meal 字段应是 dict 或 None
        if anom.get("meal") is not None:
            assert isinstance(anom["meal"], dict)

    # 指定 week_start
    custom_start = monday.isoformat()
    resp = client.get("/api/week", params={"week_start": custom_start})
    assert resp.status_code == 200
    assert resp.json()["week_start"] == custom_start


def test_get_recommend(client, db_path):
    """测试推荐接口"""
    db = Database()
    # 插入足够多的近7天数据以触发推荐（>=7 条）
    for i in range(7):
        _insert_meal(
            db,
            date=_days_ago(i),
            food_name=f"餐{i}",
            food_category="主食",
            calories=500.0,
            protein=20.0,
            carbs=60.0,
            fat=15.0,
            price=20.0,
            status="confirmed",
        )
    db.close()

    resp = client.get("/api/recommend")
    assert resp.status_code == 200
    data = resp.json()
    # 必须包含这些键
    assert "nutrient_gaps" in data
    assert "recommendations" in data
    assert "reminders" in data
    assert "general_advice" in data
    # nutrient_gaps / recommendations 中的 meal 应被序列化为 dict
    for gap in data["nutrient_gaps"]:
        assert "nutrient" in gap
        assert "display_name" in gap
    for rec in data["recommendations"]:
        assert "meal" in rec
        assert isinstance(rec["meal"], dict)
        assert "nutrient_value" in rec


def test_search(client, db_path):
    """测试关键词搜索"""
    db = Database()
    _insert_meal(
        db,
        date="2026-07-10",
        food_name="拿铁咖啡",
        food_category="饮品",
        calories=180.0,
        price=28.0,
        tags="咖啡",
    )
    _insert_meal(
        db,
        date="2026-07-11",
        food_name="美式咖啡",
        food_category="饮品",
        calories=10.0,
        price=22.0,
        tags="咖啡",
    )
    _insert_meal(
        db,
        date="2026-07-12",
        food_name="珍珠奶茶",
        food_category="饮品",
        calories=380.0,
        price=22.0,
        tags="奶茶",
    )
    _insert_meal(
        db,
        date="2026-07-13",
        food_name="黄焖鸡米饭",
        food_category="主食",
        calories=640.0,
        price=30.0,
        tags=None,
    )
    db.close()

    # 搜索 "咖啡"：应匹配前两条
    resp = client.post("/api/search", json={"query": "咖啡"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "咖啡"
    assert data["summary"]["total_count"] == 2
    assert data["summary"]["total_price"] == 50.0
    assert data["summary"]["total_calories"] == 190
    assert data["summary"]["date_range"] == {
        "start": "2026-07-10",
        "end": "2026-07-11",
    }
    names = {m["food_name"] for m in data["results"]}
    assert names == {"拿铁咖啡", "美式咖啡"}

    # 搜索食物类别 "主食"
    resp = client.post("/api/search", json={"query": "主食"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total_count"] == 1
    assert data["results"][0]["food_name"] == "黄焖鸡米饭"

    # 搜索无结果
    resp = client.post("/api/search", json={"query": "不存在的食物"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total_count"] == 0
    assert data["results"] == []
    assert data["summary"]["date_range"] is None


def test_init_status(client, db_path):
    """测试初始化状态"""
    # 空数据库
    resp = client.get("/api/init-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["initialized"] is False
    assert data["meal_count"] == 0
    assert data["has_demo_data"] is False

    # 插入数据后再查
    db = Database()
    _insert_meal(db, food_name="x")
    db.close()

    resp = client.get("/api/init-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["initialized"] is True
    assert data["meal_count"] == 1
    assert data["has_demo_data"] is True


def test_init_and_reset(client, db_path):
    """测试初始化与重置"""
    # 1. 空库初始化：应插入示例数据
    resp = client.post("/api/init", json={"reset": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["meal_count"] > 0
    first_count = data["meal_count"]

    # 2. 再次调用 init(reset=False)：已有数据，应跳过，数量不变
    resp = client.post("/api/init", json={"reset": False})
    assert resp.status_code == 200
    assert resp.json()["meal_count"] == first_count

    # 3. 手动插入一条额外记录，使总数变化
    db = Database()
    extra_id = _insert_meal(db, food_name="额外")
    db.close()

    # 4. reset=False 时不会清空
    resp = client.post("/api/init", json={"reset": False})
    assert resp.status_code == 200
    assert resp.json()["meal_count"] == first_count + 1

    # 5. reset=True：清空并重新插入示例数据
    resp = client.post("/api/init", json={"reset": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["meal_count"] == first_count  # 恢复到示例数据数量

    # 6. 不带 body 调用应使用默认 reset=False
    resp = client.post("/api/init", json={})
    assert resp.status_code == 200
    assert resp.json()["meal_count"] == first_count

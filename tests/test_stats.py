"""统计分析模块测试

使用 pytest 的 tmp_path + monkeypatch 设置临时数据库（DATABASE_PATH 环境变量），
stats 模块内 Database() 会读取该环境变量，从而实现测试隔离。

覆盖：
- daily_summary：每日统计 / 空数据
- weekly_summary：周报统计 / 与上周对比
- evaluate_nutrition：各营养评价规则
"""

from datetime import date, timedelta

import pytest

from foodlog import stats
from foodlog.database import Database, Meal


# ---------- 公共 fixture ----------
@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """设置临时数据库路径到 DATABASE_PATH 环境变量，并返回该路径。"""
    path = str(tmp_path / "test_stats.db")
    monkeypatch.setenv("DATABASE_PATH", path)
    return path


def _make_meal(**overrides) -> Meal:
    """构造一条测试 Meal，默认值可被 overrides 覆盖。"""
    defaults = dict(
        date="2026-07-13",
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
    )
    defaults.update(overrides)
    return Meal(**defaults)


# ---------- daily_summary ----------
def test_daily_summary(db_path):
    """测试每日统计：总量、餐次分组、标签、评价均正确。"""
    db = Database()
    db.insert_meal(
        _make_meal(
            date="2026-07-13",
            meal_type="breakfast",
            food_name="燕麦牛奶",
            food_category="主食",
            calories=400.0,
            protein=15.0,
            carbs=50.0,
            fat=10.0,
            price=10.0,
            tags="咖啡",
        )
    )
    db.insert_meal(
        _make_meal(
            date="2026-07-13",
            meal_type="lunch",
            food_name="鸡胸肉沙拉",
            food_category="蔬菜",
            calories=500.0,
            protein=40.0,
            carbs=30.0,
            fat=15.0,
            price=35.0,
        )
    )
    db.insert_meal(
        _make_meal(
            date="2026-07-13",
            meal_type="dinner",
            food_name="清蒸鱼+时蔬",
            food_category="蔬菜",
            calories=600.0,
            protein=35.0,
            carbs=20.0,
            fat=18.0,
            price=40.0,
        )
    )
    db.close()

    summary = stats.daily_summary("2026-07-13")

    assert summary["date"] == "2026-07-13"
    assert summary["meal_count"] == 3
    assert summary["total_calories"] == 1500.0
    assert summary["total_protein"] == 90.0
    assert summary["total_carbs"] == 100.0
    assert summary["total_fat"] == 43.0
    assert summary["total_price"] == 85.0
    assert len(summary["meals"]) == 3

    # tags 聚合
    assert "咖啡" in summary["tags"]
    assert summary["tags"]["咖啡"]["count"] == 1
    assert summary["tags"]["咖啡"]["total_price"] == 10.0

    # by_meal_type 四种餐次齐全
    for mt in ("breakfast", "lunch", "dinner", "snack"):
        assert mt in summary["by_meal_type"]
    assert summary["by_meal_type"]["breakfast"]["calories"] == 400.0
    assert summary["by_meal_type"]["breakfast"]["price"] == 10.0
    assert len(summary["by_meal_type"]["breakfast"]["items"]) == 1
    assert summary["by_meal_type"]["snack"]["calories"] == 0.0
    assert summary["by_meal_type"]["snack"]["items"] == []

    # 有蔬菜 → 正面评价；蛋白质充足
    assert isinstance(summary["evaluations"], list)
    assert any("蔬菜" in e and "继续" in e for e in summary["evaluations"])


def test_daily_summary_empty(db_path):
    """测试空数据的每日统计：数值为 0，评价为空。"""
    summary = stats.daily_summary("2026-07-13")

    assert summary["date"] == "2026-07-13"
    assert summary["meal_count"] == 0
    assert summary["total_calories"] == 0.0
    assert summary["total_protein"] == 0.0
    assert summary["total_carbs"] == 0.0
    assert summary["total_fat"] == 0.0
    assert summary["total_price"] == 0.0
    assert summary["meals"] == []
    assert summary["tags"] == {}
    assert summary["evaluations"] == []
    for mt in ("breakfast", "lunch", "dinner", "snack"):
        assert summary["by_meal_type"][mt]["items"] == []
        assert summary["by_meal_type"][mt]["calories"] == 0.0


# ---------- weekly_summary ----------
def test_weekly_summary(db_path):
    """测试周报统计：范围、daily_data 长度与排序、无记录天为 0、无上周数据对比为 None。"""
    week_start = "2026-07-13"  # 周一
    db = Database()
    for offset in range(3):
        d = (date.fromisoformat(week_start) + timedelta(days=offset)).isoformat()
        db.insert_meal(
            _make_meal(
                date=d,
                meal_type="lunch",
                food_name=f"餐{offset}",
                food_category="蔬菜",
                calories=600.0,
                protein=30.0,
                carbs=60.0,
                fat=20.0,
                price=30.0,
                tags="咖啡" if offset == 0 else None,
            )
        )
    db.close()

    summary = stats.weekly_summary(week_start)

    assert summary["week_start"] == "2026-07-13"
    assert summary["week_end"] == "2026-07-19"
    assert summary["meal_count"] == 3

    # daily_data 共 7 天且按日期升序
    assert len(summary["daily_data"]) == 7
    assert summary["daily_data"][0]["date"] == "2026-07-13"
    assert summary["daily_data"][6]["date"] == "2026-07-19"

    # 有记录的天
    assert summary["daily_data"][0]["meal_count"] == 1
    assert summary["daily_data"][0]["calories"] == 600.0
    assert summary["daily_data"][0]["protein"] == 30.0
    # 无记录的天数值为 0
    assert summary["daily_data"][3]["meal_count"] == 0
    assert summary["daily_data"][3]["calories"] == 0.0
    assert summary["daily_data"][3]["price"] == 0.0

    # 汇总
    assert summary["total_calories"] == 1800.0
    assert summary["avg_daily_calories"] == round(1800.0 / 7, 1)
    assert summary["avg_daily_price"] == round(90.0 / 7, 1)

    # 标签聚合
    assert "咖啡" in summary["tags"]
    assert summary["tags"]["咖啡"]["count"] == 1

    # 无上周数据 → 对比全为 None
    assert summary["comparison"]["calories_change"] is None
    assert summary["comparison"]["price_change"] is None
    assert summary["comparison"]["protein_change"] is None

    assert isinstance(summary["anomalies"], list)
    assert isinstance(summary["evaluations"], list)


def test_weekly_summary_with_comparison(db_path):
    """测试有上周数据时的对比：百分比变化计算正确。"""
    week_start = "2026-07-13"
    db = Database()
    # 上周（2026-07-06 ~ 2026-07-12）1 条记录
    db.insert_meal(
        _make_meal(
            date="2026-07-07",
            meal_type="lunch",
            food_name="上周餐",
            calories=1000.0,
            protein=50.0,
            price=50.0,
        )
    )
    # 本周 1 条记录
    db.insert_meal(
        _make_meal(
            date="2026-07-13",
            meal_type="lunch",
            food_name="本周餐",
            calories=1200.0,
            protein=60.0,
            price=60.0,
        )
    )
    db.close()

    summary = stats.weekly_summary(week_start)
    comp = summary["comparison"]

    # (1200-1000)/1000*100 = 20.0
    assert comp["calories_change"] == 20.0
    # (60-50)/50*100 = 20.0
    assert comp["protein_change"] == 20.0
    # (60-50)/50*100 = 20.0
    assert comp["price_change"] == 20.0


def test_weekly_summary_anomalies(db_path):
    """测试周报异常检测：高热量单餐、高日支出、高频标签。"""
    week_start = "2026-07-13"
    db = Database()
    # 单餐 1200kcal > 1000 → high_calorie
    db.insert_meal(
        _make_meal(
            date="2026-07-13",
            food_name="大汉堡套餐",
            food_category="肉类",
            calories=1200.0,
            protein=40.0,
            price=50.0,
        )
    )
    # 日支出 150 > 100 → high_spend
    db.insert_meal(
        _make_meal(
            date="2026-07-14",
            food_name="寿司套餐",
            food_category="主食",
            calories=580.0,
            protein=28.0,
            price=150.0,
        )
    )
    # 同一天 奶茶×2 → frequent_tag
    db.insert_meal(
        _make_meal(
            date="2026-07-15",
            food_name="珍珠奶茶",
            food_category="饮品",
            calories=380.0,
            price=22.0,
            tags="奶茶",
        )
    )
    db.insert_meal(
        _make_meal(
            date="2026-07-15",
            meal_type="snack",
            food_name="芋圆奶茶",
            food_category="饮品",
            calories=420.0,
            price=24.0,
            tags="奶茶",
        )
    )
    db.close()

    summary = stats.weekly_summary(week_start)
    types = {a["type"] for a in summary["anomalies"]}
    assert "high_calorie" in types
    assert "high_spend" in types
    assert "frequent_tag" in types

    # 校验 frequent_tag 描述格式
    ft = [a for a in summary["anomalies"] if a["type"] == "frequent_tag"]
    assert any("奶茶" in a["description"] and "×2" in a["description"] for a in ft)


# ---------- evaluate_nutrition ----------
def test_evaluate_nutrition_protein_low():
    """蛋白质 < 60g → 触发蛋白质不足评价。"""
    meals = [_make_meal(protein=30.0, food_category="蔬菜", calories=500.0, price=30.0)]
    evals = stats.evaluate_nutrition(meals, 500.0, 30.0, 60.0, 15.0, {})
    assert any("蛋白质" in e for e in evals)


def test_evaluate_nutrition_no_vegetables():
    """无蔬菜类食物 → 触发缺蔬菜评价。"""
    meals = [_make_meal(protein=70.0, food_category="主食", calories=1500.0, price=30.0)]
    evals = stats.evaluate_nutrition(meals, 1500.0, 70.0, 60.0, 15.0, {})
    assert any("蔬菜" in e for e in evals)


def test_evaluate_nutrition_too_many_drinks():
    """奶茶/咖啡 ≥ 2 次 → 触发饮料过多评价。"""
    meals = [
        _make_meal(
            food_category="蔬菜", calories=500.0, protein=70.0, price=30.0, tags="咖啡"
        ),
        _make_meal(
            food_category="蔬菜", calories=500.0, protein=70.0, price=30.0, tags="咖啡"
        ),
    ]
    tags = {"咖啡": {"count": 2, "total_price": 60.0}}
    evals = stats.evaluate_nutrition(meals, 1000.0, 140.0, 120.0, 30.0, tags)
    assert any("饮料" in e for e in evals)


def test_evaluate_nutrition_high_calorie_meal():
    """单餐热量 > 1000kcal → 触发高热量单餐评价，并包含食物名。"""
    meals = [
        _make_meal(
            food_name="大汉堡",
            food_category="肉类",
            calories=1200.0,
            protein=50.0,
            price=50.0,
        )
    ]
    evals = stats.evaluate_nutrition(meals, 1200.0, 50.0, 60.0, 30.0, {})
    assert any("热量较高" in e and "大汉堡" in e for e in evals)


def test_evaluate_nutrition_high_spend():
    """日总支出 > 100 元 → 触发高支出评价。"""
    meals = [_make_meal(food_category="蔬菜", calories=1500.0, protein=70.0, price=150.0)]
    evals = stats.evaluate_nutrition(meals, 1500.0, 70.0, 60.0, 15.0, {})
    assert any("花费" in e for e in evals)


def test_evaluate_nutrition_positive():
    """有水果/蔬菜 → 触发正面评价。"""
    meals = [
        _make_meal(
            meal_type="snack",
            food_name="水果拼盘",
            food_category="水果",
            calories=200.0,
            protein=5.0,
            price=10.0,
        ),
        _make_meal(
            food_name="清炒时蔬",
            food_category="蔬菜",
            calories=300.0,
            protein=70.0,
            price=20.0,
        ),
    ]
    evals = stats.evaluate_nutrition(meals, 500.0, 75.0, 60.0, 15.0, {})
    assert any("水果" in e for e in evals)
    assert any("蔬菜" in e and "继续" in e for e in evals)


def test_evaluate_nutrition_empty():
    """空记录 → 无评价。"""
    assert stats.evaluate_nutrition([], 0.0, 0.0, 0.0, 0.0, {}) == []

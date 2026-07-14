"""推荐引擎测试

使用 pytest 的 tmp_path + monkeypatch 设置临时数据库（DATABASE_PATH 环境变量），
recommender 模块内 Database() 会读取该环境变量，从而实现测试隔离。

覆盖：
- analyze_nutrient_gaps：缺口分析（蛋白质不足 / 全部充足）
- find_matching_meals：历史套餐检索 / 去重逻辑
- get_recommendations：有数据 / 数据不足时的推荐
- _generate_today_reminders：今日提醒逻辑
"""

from datetime import date, timedelta

import pytest

from foodlog import recommender
from foodlog.database import Database, Meal


# ---------- 公共工具 ----------
@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """设置临时数据库路径到 DATABASE_PATH 环境变量，并返回该路径。"""
    path = str(tmp_path / "test_recommender.db")
    monkeypatch.setenv("DATABASE_PATH", path)
    return path


def _days_ago(n: int) -> str:
    """返回距今 n 天前的日期字符串（YYYY-MM-DD）。"""
    return (date.today() - timedelta(days=n)).isoformat()


def _today() -> str:
    return date.today().isoformat()


def _make_meal(**overrides) -> Meal:
    """构造一条测试 Meal，默认值可被 overrides 覆盖。"""
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


# ---------- analyze_nutrient_gaps ----------
def test_analyze_nutrient_gaps_protein_low():
    """蛋白质不足：近7天日均蛋白质远低于推荐，应识别为缺口。"""
    # 7 天每天蛋白质 30g，日均 30g，推荐 60g，缺口 30g（50%，severe）
    # 其他营养素充足，确保只报蛋白质缺口
    meals = [
        _make_meal(
            date=_days_ago(i),
            food_name=f"清淡餐{i}",
            calories=2000.0,
            protein=30.0,
            carbs=250.0,
            fat=70.0,
        )
        for i in range(7)
    ]

    gaps = recommender.analyze_nutrient_gaps(meals)

    protein_gap = next((g for g in gaps if g["nutrient"] == "protein"), None)
    assert protein_gap is not None, "应识别出蛋白质缺口"
    assert protein_gap["display_name"] == "蛋白质"
    assert protein_gap["avg_intake"] == 30.0
    assert protein_gap["recommended"] == 60.0
    assert protein_gap["deficiency"] == 30.0
    assert protein_gap["severity"] == "severe"
    assert "蛋白质" in protein_gap["description"]
    assert "低于推荐" in protein_gap["description"]

    # 其他营养素充足，不应出现缺口
    nutrients = {g["nutrient"] for g in gaps}
    assert "calories" not in nutrients
    assert "carbs" not in nutrients
    assert "fat" not in nutrients


def test_analyze_nutrient_gaps_all_sufficient():
    """营养充足：所有营养素均达标，缺口列表应为空。"""
    # 7 天每天各项营养素恰好等于推荐值
    meals = [
        _make_meal(
            date=_days_ago(i),
            food_name=f"均衡餐{i}",
            calories=2000.0,
            protein=60.0,
            carbs=250.0,
            fat=70.0,
        )
        for i in range(7)
    ]

    gaps = recommender.analyze_nutrient_gaps(meals)
    assert gaps == []


def test_analyze_nutrient_gaps_empty():
    """空数据：缺口列表应为空。"""
    assert recommender.analyze_nutrient_gaps([]) == []


def test_analyze_nutrient_gaps_severity_levels():
    """缺口严重程度分级：mild / moderate / severe。"""
    # 蛋白质缺口 5%（30/60... 实际构造 mild）
    # mild: 缺口 < 10% → 日均 55g（缺口 5g，约 8.3%）
    meals_mild = [
        _make_meal(date=_days_ago(i), food_name=f"m{i}", protein=55.0,
                   calories=2000.0, carbs=250.0, fat=70.0)
        for i in range(7)
    ]
    gaps_mild = recommender.analyze_nutrient_gaps(meals_mild)
    protein_mild = next(g for g in gaps_mild if g["nutrient"] == "protein")
    assert protein_mild["severity"] == "mild"

    # moderate: 缺口 10%~30% → 日均 48g（缺口 12g，20%）
    meals_mod = [
        _make_meal(date=_days_ago(i), food_name=f"m{i}", protein=48.0,
                   calories=2000.0, carbs=250.0, fat=70.0)
        for i in range(7)
    ]
    gaps_mod = recommender.analyze_nutrient_gaps(meals_mod)
    protein_mod = next(g for g in gaps_mod if g["nutrient"] == "protein")
    assert protein_mod["severity"] == "moderate"


# ---------- find_matching_meals ----------
def test_find_matching_meals():
    """历史套餐检索：按营养素含量降序、取前3、生成文案。"""
    gap = {
        "nutrient": "protein",
        "display_name": "蛋白质",
        "avg_intake": 30.0,
        "recommended": 60.0,
        "deficiency": 30.0,
        "severity": "severe",
        "description": "...",
    }
    meals = [
        _make_meal(food_name="牛排", protein=50.0, price=128.0, date="2026-07-10"),
        _make_meal(food_name="鸡胸肉沙拉", protein=36.0, price=38.0, date="2026-07-11"),
        _make_meal(food_name="白米饭", protein=5.0, price=3.0, date="2026-07-09"),
        _make_meal(food_name="无蛋白餐", protein=None, price=10.0, date="2026-07-08"),
    ]

    results = recommender.find_matching_meals(gap, meals)

    # 无蛋白数据的记录被过滤
    names = [r["meal"].food_name for r in results]
    assert "无蛋白餐" not in names
    # 按蛋白质含量降序
    assert names == ["牛排", "鸡胸肉沙拉", "白米饭"]
    # 取前3条
    assert len(results) == 3

    # 第一条文案
    top = results[0]
    assert top["nutrient_value"] == 50.0
    assert top["last_date"] == "2026-07-10"
    assert "牛排" in top["recommendation_text"]
    assert "蛋白质" in top["recommendation_text"]
    assert "富含蛋白质" in top["reason"]


def test_find_matching_meals_dedup():
    """去重：相同 food_name 只保留最近一次（即便含量更低）。"""
    gap = {
        "nutrient": "protein",
        "display_name": "蛋白质",
        "avg_intake": 30.0,
        "recommended": 60.0,
        "deficiency": 30.0,
        "severity": "severe",
        "description": "...",
    }
    meals = [
        # 同名"黄焖鸡米饭"出现两次，含量高但日期较早
        _make_meal(food_name="黄焖鸡米饭", protein=45.0, price=25.0, date="2026-07-05"),
        # 同名"黄焖鸡米饭"，含量低但日期较近 → 应保留这条
        _make_meal(food_name="黄焖鸡米饭", protein=30.0, price=25.0, date="2026-07-12"),
        _make_meal(food_name="鸡胸肉沙拉", protein=36.0, price=38.0, date="2026-07-11"),
    ]

    results = recommender.find_matching_meals(gap, meals)

    # 去重后只剩 2 个不同 food_name
    names = [r["meal"].food_name for r in results]
    assert names.count("黄焖鸡米饭") == 1
    # 保留的是日期较近、含量较低的那条（protein=30）
    hm = next(r for r in results if r["meal"].food_name == "黄焖鸡米饭")
    assert hm["nutrient_value"] == 30.0
    assert hm["last_date"] == "2026-07-12"
    # 按含量降序：鸡胸肉沙拉(36) > 黄焖鸡米饭(30)
    assert names == ["鸡胸肉沙拉", "黄焖鸡米饭"]


def test_find_matching_meals_empty():
    """无匹配套餐：返回空列表。"""
    gap = {
        "nutrient": "protein",
        "display_name": "蛋白质",
        "avg_intake": 30.0,
        "recommended": 60.0,
        "deficiency": 30.0,
        "severity": "severe",
        "description": "...",
    }
    # 所有记录蛋白质均为 None
    meals = [_make_meal(food_name="a", protein=None)]
    assert recommender.find_matching_meals(gap, meals) == []
    # 空列表
    assert recommender.find_matching_meals(gap, []) == []


# ---------- get_recommendations ----------
def test_get_recommendations_with_data(db_path):
    """有足够数据：返回营养缺口与推荐列表。"""
    db = Database()
    # 近7天：每天1条低蛋白餐（创造蛋白质缺口），其他营养充足
    for i in range(7):
        db.insert_meal(
            _make_meal(
                date=_days_ago(i),
                food_name=f"清淡餐{i}",
                meal_type="lunch",
                food_category="主食",
                calories=2000.0,
                protein=30.0,
                carbs=250.0,
                fat=70.0,
                price=20.0,
            )
        )
    # 一条高蛋白的历史记录（10天前，不在7天窗口内但属于已确认记录）
    db.insert_meal(
        _make_meal(
            date=_days_ago(10),
            food_name="黑椒牛排",
            meal_type="dinner",
            food_category="肉类",
            calories=820.0,
            protein=50.0,
            carbs=70.0,
            fat=38.0,
            price=128.0,
        )
    )
    db.close()

    result = recommender.get_recommendations()

    # 数据充足，不应返回通用建议
    assert result["general_advice"] == ""
    # 应有蛋白质缺口
    gaps = result["nutrient_gaps"]
    assert any(g["nutrient"] == "protein" for g in gaps)
    # 应有推荐（针对蛋白质缺口）
    recs = result["recommendations"]
    assert len(recs) >= 1
    # 第一条推荐应是蛋白质含量最高的黑椒牛排
    assert recs[0]["meal"].food_name == "黑椒牛排"
    assert recs[0]["display_name"] == "蛋白质"
    assert "黑椒牛排" in recs[0]["recommendation_text"]
    # 今日提醒应存在（今天只记了午餐，缺早餐晚餐、无蔬菜水果）
    assert isinstance(result["reminders"], list)
    assert len(result["reminders"]) >= 1


def test_get_recommendations_insufficient_data(db_path):
    """数据不足：返回通用建议，缺口与推荐为空。"""
    db = Database()
    # 仅插入3条近7天记录（< 7）
    for i in range(3):
        db.insert_meal(
            _make_meal(
                date=_days_ago(i),
                food_name=f"餐{i}",
                food_category="主食",
            )
        )
    db.close()

    result = recommender.get_recommendations()

    assert result["nutrient_gaps"] == []
    assert result["recommendations"] == []
    assert "记录更多数据" in result["general_advice"]
    # 提醒仍应生成
    assert isinstance(result["reminders"], list)


def test_get_recommendations_empty_db(db_path):
    """空数据库：数据不足，返回通用建议。"""
    result = recommender.get_recommendations()

    assert result["nutrient_gaps"] == []
    assert result["recommendations"] == []
    assert result["general_advice"]
    # 今天无任何记录 → 应提醒缺餐次、蔬菜、水果
    assert len(result["reminders"]) >= 1
    assert any("还没记" in r for r in result["reminders"])


# ---------- 今日提醒 ----------
def test_today_reminders_empty():
    """今天无任何记录：提醒缺失三餐 + 蔬菜 + 水果。"""
    reminders = recommender._generate_today_reminders([])
    assert any("早餐、午餐、晚餐" in r for r in reminders)
    assert any("蔬菜" in r for r in reminders)
    assert any("水果" in r for r in reminders)


def test_today_reminders_missing_dinner():
    """只记了早午餐：提醒晚餐 + 蔬菜 + 水果。"""
    meals = [
        _make_meal(meal_type="breakfast", food_category="主食"),
        _make_meal(meal_type="lunch", food_category="主食"),
    ]
    reminders = recommender._generate_today_reminders(meals)
    assert any("晚餐" in r and "还没记" in r for r in reminders)
    assert any("蔬菜" in r for r in reminders)
    assert any("水果" in r for r in reminders)


def test_today_reminders_complete():
    """三餐齐全且有蔬菜水果：无提醒。"""
    meals = [
        _make_meal(meal_type="breakfast", food_category="水果"),
        _make_meal(meal_type="lunch", food_category="蔬菜"),
        _make_meal(meal_type="dinner", food_category="蔬菜"),
    ]
    reminders = recommender._generate_today_reminders(meals)
    assert reminders == []


def test_today_reminders_three_meals_no_veg_fruit():
    """三餐齐全但无蔬菜水果：只提醒蔬菜和水果，不提醒缺餐次。"""
    meals = [
        _make_meal(meal_type="breakfast", food_category="主食"),
        _make_meal(meal_type="lunch", food_category="主食"),
        _make_meal(meal_type="dinner", food_category="主食"),
    ]
    reminders = recommender._generate_today_reminders(meals)
    # 三餐齐全 → 不应有"还没记"提醒
    assert not any("还没记" in r for r in reminders)
    assert any("蔬菜" in r for r in reminders)
    assert any("水果" in r for r in reminders)

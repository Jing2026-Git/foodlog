"""推荐引擎

基于用户历史饮食记录，识别营养缺口并从已确认记录中
检索富含缺口营养素的套餐，给出个性化的饮食推荐。

主要函数：
- get_recommendations: 对外入口，返回推荐结果
- analyze_nutrient_gaps: 近7天营养缺口分析
- find_matching_meals: 从历史记录中检索匹配套餐
- generate_recommendations: 推荐生成主流程
"""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .database import Database, Meal

# 成人日均推荐摄入量（参考值）
_RECOMMENDED_INTAKE = {
    "calories": {"display_name": "热量", "value": 2000.0, "unit": "kcal"},
    "protein": {"display_name": "蛋白质", "value": 60.0, "unit": "g"},
    "carbs": {"display_name": "碳水", "value": 250.0, "unit": "g"},
    "fat": {"display_name": "脂肪", "value": 70.0, "unit": "g"},
}

# 主餐次（用于"缺失餐次"提醒）
_MAIN_MEAL_TYPES = ("breakfast", "lunch", "dinner")
_MEAL_TYPE_NAMES = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
}

# 数据不足时的通用建议
_GENERAL_ADVICE = (
    "记录更多数据后推荐会更精准。"
    "目前建议：保持三餐规律，注意蛋白质和蔬菜的摄入。"
)

# 触发推荐所需的最小近7天记录数
_MIN_RECORDS_FOR_RECO = 7


def _fmt_num(v: float) -> str:
    """格式化数值：整数显示为整数，否则保留1位小数。"""
    v = round(float(v), 1)
    if v == int(v):
        return str(int(v))
    return f"{v:.1f}"


def _date_key(d: Optional[str]) -> int:
    """把日期字符串转为可比较的整数键（YYYYMMDD）；None 视为最小。"""
    if not d:
        return 0
    digits = "".join(ch for ch in d[:10] if ch.isdigit())
    try:
        return int(digits) if digits else 0
    except ValueError:
        return 0


def _get_nutrient(meal: Meal, nutrient: str) -> Optional[float]:
    """从 Meal 中取某个营养素的值。"""
    return getattr(meal, nutrient, None)


def _severity_of(deficiency: float, recommended: float) -> str:
    """根据缺口占推荐量的比例判断严重程度。

    - < 10%  → mild
    - 10%~30% → moderate
    - > 30%  → severe
    """
    if recommended <= 0:
        return "mild"
    ratio = deficiency / recommended
    if ratio > 0.30:
        return "severe"
    if ratio >= 0.10:
        return "moderate"
    return "mild"


def analyze_nutrient_gaps(meals_7d: List[Meal]) -> List[Dict[str, Any]]:
    """分析近7天饮食的营养缺口。

    只报告"缺的"（实际日均 < 推荐），不报告超标的。
    返回缺口字典列表，按缺口占比降序排列。
    """
    if not meals_7d:
        return []

    days = 7
    gaps: List[Dict[str, Any]] = []

    for nutrient, info in _RECOMMENDED_INTAKE.items():
        total = 0.0
        has_data = False
        for m in meals_7d:
            v = _get_nutrient(m, nutrient)
            if v is not None:
                total += float(v)
                has_data = True

        # 该营养素完全无数据，无法判断
        if not has_data:
            continue

        avg_intake = round(total / days, 1)
        recommended = info["value"]
        deficiency = round(recommended - avg_intake, 1)

        # 只报缺口，不报超标
        if deficiency <= 0:
            continue

        unit = info["unit"]
        severity = _severity_of(deficiency, recommended)
        gaps.append(
            {
                "nutrient": nutrient,
                "display_name": info["display_name"],
                "avg_intake": avg_intake,
                "recommended": recommended,
                "deficiency": deficiency,
                "severity": severity,
                "description": (
                    f"近一周{info['display_name']}日均摄入"
                    f"{_fmt_num(avg_intake)}{unit}，"
                    f"低于推荐的{_fmt_num(recommended)}{unit}"
                ),
            }
        )

    # 按缺口占比降序
    gaps.sort(key=lambda g: g["deficiency"] / g["recommended"], reverse=True)
    return gaps


def find_matching_meals(
    gap: Dict[str, Any], confirmed_meals: List[Meal]
) -> List[Dict[str, Any]]:
    """从用户已确认的记录中筛选富含缺口营养素的套餐。

    步骤：
    1. 过滤出含有该营养素数据（>0）的记录
    2. 按 food_name 去重，相同名称只保留最近一次
    3. 按营养素含量降序、最近日期降序排序
    4. 取前3条
    5. 生成推荐文案
    """
    nutrient = gap["nutrient"]
    display_name = gap["display_name"]
    unit = _RECOMMENDED_INTAKE[nutrient]["unit"]

    # 1. 过滤有该营养素数据（>0）的记录
    candidates: List[Meal] = [
        m for m in confirmed_meals
        if _get_nutrient(m, nutrient) is not None
        and float(_get_nutrient(m, nutrient)) > 0
    ]
    if not candidates:
        return []

    # 2. 按 food_name 去重，保留最近一次（date 更大者胜出）
    best_by_name: Dict[str, Meal] = {}
    for m in candidates:
        existing = best_by_name.get(m.food_name)
        if existing is None:
            best_by_name[m.food_name] = m
        elif (m.date or "") >= (existing.date or ""):
            best_by_name[m.food_name] = m
    deduped = list(best_by_name.values())

    # 3. 排序：营养素含量降序，再按最近日期降序
    deduped.sort(
        key=lambda m: (
            -float(_get_nutrient(m, nutrient) or 0),
            -_date_key(m.date),
        )
    )

    # 4. 取前3条
    top = deduped[:3]

    # 5. 生成推荐文案
    results: List[Dict[str, Any]] = []
    for m in top:
        nutrient_value = round(float(_get_nutrient(m, nutrient)), 1)
        price_str = f"￥{_fmt_num(m.price)}" if m.price is not None else ""
        price_part = f"{price_str}, " if price_str else ""
        results.append(
            {
                "meal": m,
                "nutrient_value": nutrient_value,
                "last_date": m.date,
                "reason": f"富含{display_name}（{_fmt_num(nutrient_value)}{unit}）",
                "recommendation_text": (
                    f"你之前点过'{m.food_name}'"
                    f"({price_part}约{_fmt_num(nutrient_value)}{unit}{display_name})，"
                    f"可以考虑再来一顿"
                ),
            }
        )
    return results


def _generate_today_reminders(today_meals: List[Meal]) -> List[str]:
    """根据今日记录情况生成提醒。"""
    reminders: List[str] = []

    # 缺失的主餐次
    recorded_types = {m.meal_type for m in today_meals}
    missing = [mt for mt in _MAIN_MEAL_TYPES if mt not in recorded_types]
    if len(today_meals) < 3 and missing:
        names = "、".join(_MEAL_TYPE_NAMES.get(mt, mt) for mt in missing)
        reminders.append(f"你今天还没记{names}，别忘了记录")

    # 蔬菜
    if not any(m.food_category == "蔬菜" for m in today_meals):
        reminders.append("今天还没吃蔬菜，记得补充点蔬菜")

    # 水果
    if not any(m.food_category == "水果" for m in today_meals):
        reminders.append("今天还没吃水果，可以来点水果")

    return reminders


def generate_recommendations() -> Dict[str, Any]:
    """推荐生成主流程。

    1. 获取近7天数据
    2. 若不足 _MIN_RECORDS_FOR_RECO 条 → 返回通用建议
    3. 分析营养缺口
    4. 对每个缺口从历史记录中查找匹配套餐
    5. 生成今日提醒
    """
    today = date.today()
    start = today - timedelta(days=6)  # 近7天（含今天）

    db = Database()
    try:
        meals_7d = db.get_meals_by_date_range(start.isoformat(), today.isoformat())
        confirmed_meals = db.get_confirmed_meals()
        today_meals = db.get_meals_by_date(today.isoformat())
    finally:
        db.close()

    # 今日提醒（无论数据多少都生成）
    reminders = _generate_today_reminders(today_meals)

    # 数据不足 → 通用建议
    if len(meals_7d) < _MIN_RECORDS_FOR_RECO:
        return {
            "nutrient_gaps": [],
            "recommendations": [],
            "reminders": reminders,
            "general_advice": _GENERAL_ADVICE,
        }

    # 营养缺口
    gaps = analyze_nutrient_gaps(meals_7d)

    # 对每个缺口查找匹配套餐
    recommendations: List[Dict[str, Any]] = []
    for gap in gaps:
        for match in find_matching_meals(gap, confirmed_meals):
            recommendations.append(
                {
                    "nutrient": gap["nutrient"],
                    "display_name": gap["display_name"],
                    "meal": match["meal"],
                    "nutrient_value": match["nutrient_value"],
                    "last_date": match["last_date"],
                    "reason": match["reason"],
                    "recommendation_text": match["recommendation_text"],
                }
            )

    return {
        "nutrient_gaps": gaps,
        "recommendations": recommendations,
        "reminders": reminders,
        "general_advice": "",
    }


def get_recommendations() -> Dict[str, Any]:
    """获取推荐（对外入口）。"""
    return generate_recommendations()

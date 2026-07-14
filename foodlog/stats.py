"""统计分析模块

提供每日/每周饮食数据的汇总统计与营养评价。

主要函数：
- daily_summary: 某天的统计汇总
- weekly_summary: 某周（周一到周日）的统计汇总
- evaluate_nutrition: 营养评价规则引擎
"""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .database import Database, Meal

# 标准餐次顺序
_MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")

# 饮料类标签（用于"饮料过多"评价）
_DRINK_TAGS = ("奶茶", "咖啡")


def _aggregate_tags(meals: List[Meal]) -> Dict[str, Dict[str, Any]]:
    """聚合 meals 的 tags，返回 {tag: {"count": int, "total_price": float}}。

    price 为 None 时按 0 处理；total_price 保留 1 位小数。
    """
    agg: Dict[str, Dict[str, Any]] = {}
    for m in meals:
        if not m.tags:
            continue
        for tag in m.tags.split(","):
            tag = tag.strip()
            if not tag:
                continue
            entry = agg.setdefault(tag, {"count": 0, "total_price": 0.0})
            entry["count"] += 1
            entry["total_price"] += float(m.price or 0)
    for entry in agg.values():
        entry["total_price"] = round(entry["total_price"], 1)
    return agg


def _fmt_num_clean(v: Optional[float]) -> str:
    """格式化数值：整数显示为整数，否则保留 1 位小数；None 视为 0。"""
    if v is None:
        v = 0.0
    v = round(float(v), 1)
    if v == int(v):
        return str(int(v))
    return f"{v:.1f}"


def evaluate_nutrition(
    meals: List[Meal],
    total_calories: float,
    total_protein: float,
    total_carbs: float,
    total_fat: float,
    tags: Dict[str, Dict[str, Any]],
) -> List[str]:
    """营养评价规则引擎，返回评价文案列表。

    规则：
    - 蛋白质 < 60g/天 → "蛋白质不足，建议补充肉蛋奶"
    - 无蔬菜类食物 → "今天没吃蔬菜，建议补充"
    - 奶茶/咖啡 tag ≥ 2次/天 → "今天饮料有点多"
    - 单餐热量 > 1000kcal → "这顿热量较高：{食物名}（{热量}kcal）"
    - 日总支出 > 100元 → "今天餐饮花费较高（￥{金额}）"
    - 热量 < 1200kcal → "今天吃得太少了，注意营养均衡"
    - 热量 > 2500kcal → "今天热量摄入偏高"
    - 有水果类食物 → "今天吃了水果，不错！"
    - 有蔬菜类食物 → "蔬菜摄入达标，继续保持"

    空记录（无 meals）返回空列表。
    """
    if not meals:
        return []

    evaluations: List[str] = []
    total_price = sum(float(m.price or 0) for m in meals)

    has_vegetable = any(m.food_category == "蔬菜" for m in meals)
    has_fruit = any(m.food_category == "水果" for m in meals)

    # 1. 蛋白质不足
    if total_protein < 60:
        evaluations.append("蛋白质不足，建议补充肉蛋奶")

    # 2. 无蔬菜
    if not has_vegetable:
        evaluations.append("今天没吃蔬菜，建议补充")

    # 3. 饮料过多（奶茶/咖啡 >= 2）
    drink_count = sum(tags.get(t, {}).get("count", 0) for t in _DRINK_TAGS)
    if drink_count >= 2:
        evaluations.append("今天饮料有点多")

    # 4. 单餐热量过高
    for m in meals:
        if (m.calories or 0) > 1000:
            evaluations.append(
                f"这顿热量较高：{m.food_name}（{_fmt_num_clean(m.calories)}kcal）"
            )

    # 5. 日支出过高
    if total_price > 100:
        evaluations.append(f"今天餐饮花费较高（￥{_fmt_num_clean(total_price)}）")

    # 6. 热量过低
    if total_calories < 1200:
        evaluations.append("今天吃得太少了，注意营养均衡")

    # 7. 热量过高
    if total_calories > 2500:
        evaluations.append("今天热量摄入偏高")

    # 8. 正面：有水果
    if has_fruit:
        evaluations.append("今天吃了水果，不错！")

    # 9. 正面：有蔬菜
    if has_vegetable:
        evaluations.append("蔬菜摄入达标，继续保持")

    return evaluations


def daily_summary(date_str: Optional[str] = None) -> Dict[str, Any]:
    """返回某天的统计汇总。不传 date_str 时默认今天。"""
    if date_str is None:
        date_str = date.today().isoformat()

    db = Database()
    try:
        meals = db.get_meals_by_date(date_str)

        total_calories = round(sum(float(m.calories or 0) for m in meals), 1)
        total_protein = round(sum(float(m.protein or 0) for m in meals), 1)
        total_carbs = round(sum(float(m.carbs or 0) for m in meals), 1)
        total_fat = round(sum(float(m.fat or 0) for m in meals), 1)
        total_price = round(sum(float(m.price or 0) for m in meals), 1)

        tags = _aggregate_tags(meals)

        # 按餐次分组
        by_meal_type: Dict[str, Dict[str, Any]] = {
            mt: {"calories": 0.0, "price": 0.0, "items": []}
            for mt in _MEAL_TYPES
        }
        for m in meals:
            mt = m.meal_type
            if mt not in by_meal_type:
                by_meal_type[mt] = {"calories": 0.0, "price": 0.0, "items": []}
            by_meal_type[mt]["calories"] += float(m.calories or 0)
            by_meal_type[mt]["price"] += float(m.price or 0)
            by_meal_type[mt]["items"].append(m)
        for mt_data in by_meal_type.values():
            mt_data["calories"] = round(mt_data["calories"], 1)
            mt_data["price"] = round(mt_data["price"], 1)

        evaluations = evaluate_nutrition(
            meals, total_calories, total_protein, total_carbs, total_fat, tags
        )

        return {
            "date": date_str,
            "total_calories": total_calories,
            "total_protein": total_protein,
            "total_carbs": total_carbs,
            "total_fat": total_fat,
            "total_price": total_price,
            "meal_count": len(meals),
            "meals": meals,
            "tags": tags,
            "by_meal_type": by_meal_type,
            "evaluations": evaluations,
        }
    finally:
        db.close()


def weekly_summary(week_start: Optional[str] = None) -> Dict[str, Any]:
    """返回某周（周一到周日）的统计汇总。不传 week_start 时默认本周一。"""
    if week_start is None:
        today = date.today()
        start = today - timedelta(days=today.weekday())
    else:
        start = date.fromisoformat(week_start)
    end = start + timedelta(days=6)
    week_start_str = start.isoformat()
    week_end_str = end.isoformat()

    db = Database()
    try:
        meals = db.get_meals_by_date_range(week_start_str, week_end_str)

        # 按日期分组
        by_date: Dict[str, List[Meal]] = {}
        for m in meals:
            by_date.setdefault(m.date, []).append(m)

        # daily_data：7 天，按日期排序，无记录的天数值为 0
        daily_data: List[Dict[str, Any]] = []
        total_calories = 0.0
        total_price = 0.0
        total_protein = 0.0
        for i in range(7):
            d = (start + timedelta(days=i)).isoformat()
            day_meals = by_date.get(d, [])
            dc = round(sum(float(m.calories or 0) for m in day_meals), 1)
            dp = round(sum(float(m.price or 0) for m in day_meals), 1)
            dpr = round(sum(float(m.protein or 0) for m in day_meals), 1)
            daily_data.append(
                {
                    "date": d,
                    "calories": dc,
                    "price": dp,
                    "meal_count": len(day_meals),
                    "protein": dpr,
                }
            )
            total_calories += dc
            total_price += dp
            total_protein += dpr

        total_calories = round(total_calories, 1)
        total_price = round(total_price, 1)
        total_protein = round(total_protein, 1)
        avg_daily_calories = round(total_calories / 7, 1)
        avg_daily_price = round(total_price / 7, 1)
        avg_protein = round(total_protein / 7, 1)

        tags = _aggregate_tags(meals)

        # 异常检测
        anomalies: List[Dict[str, Any]] = []
        # 单餐热量过高
        for m in meals:
            if (m.calories or 0) > 1000:
                anomalies.append(
                    {
                        "type": "high_calorie",
                        "date": m.date,
                        "description": f"单餐热量较高（{_fmt_num_clean(m.calories)}kcal）",
                        "meal": m,
                    }
                )
        # 日支出过高
        for d_entry in daily_data:
            if d_entry["price"] > 100:
                anomalies.append(
                    {
                        "type": "high_spend",
                        "date": d_entry["date"],
                        "description": f"日餐饮花费较高（￥{_fmt_num_clean(d_entry['price'])}）",
                        "meal": None,
                    }
                )
        # 同一天同一标签出现 >= 2 次
        for d_str, day_meals in by_date.items():
            day_tags = _aggregate_tags(day_meals)
            for tag, info in day_tags.items():
                if info["count"] >= 2:
                    anomalies.append(
                        {
                            "type": "frequent_tag",
                            "date": d_str,
                            "description": f"{tag}×{info['count']}",
                            "meal": None,
                        }
                    )

        # 与上周对比
        last_start = start - timedelta(days=7)
        last_end = start - timedelta(days=1)
        last_meals = db.get_meals_by_date_range(
            last_start.isoformat(), last_end.isoformat()
        )
        if last_meals:
            last_calories = sum(float(m.calories or 0) for m in last_meals)
            last_price = sum(float(m.price or 0) for m in last_meals)
            last_protein = sum(float(m.protein or 0) for m in last_meals)

            def _pct(curr: float, prev: float) -> Optional[float]:
                if prev == 0:
                    return None
                return round((curr - prev) / prev * 100, 1)

            comparison = {
                "calories_change": _pct(total_calories, last_calories),
                "price_change": _pct(total_price, last_price),
                "protein_change": _pct(total_protein, last_protein),
            }
        else:
            comparison = {
                "calories_change": None,
                "price_change": None,
                "protein_change": None,
            }

        # 周报评价
        evaluations: List[str] = []
        if avg_protein < 60:
            evaluations.append("本周蛋白质平均摄入不足")
        # 连续 3 天以上（含 3 天）无蔬菜
        max_streak = 0
        streak = 0
        for d_entry in daily_data:
            day_meals = by_date.get(d_entry["date"], [])
            if not day_meals:
                # 无记录的天不计入也不打断
                continue
            if any(m.food_category == "蔬菜" for m in day_meals):
                streak = 0
            else:
                streak += 1
                if streak > max_streak:
                    max_streak = streak
        if max_streak >= 3:
            evaluations.append("本周蔬菜摄入太少")
        # 饮料总次数 > 7
        drink_total = sum(tags.get(t, {}).get("count", 0) for t in _DRINK_TAGS)
        if drink_total > 7:
            evaluations.append("本周饮料摄入频繁")

        return {
            "week_start": week_start_str,
            "week_end": week_end_str,
            "total_calories": total_calories,
            "avg_daily_calories": avg_daily_calories,
            "total_price": total_price,
            "avg_daily_price": avg_daily_price,
            "total_protein": total_protein,
            "avg_protein": avg_protein,
            "meal_count": len(meals),
            "daily_data": daily_data,
            "tags": tags,
            "anomalies": anomalies,
            "comparison": comparison,
            "evaluations": evaluations,
        }
    finally:
        db.close()

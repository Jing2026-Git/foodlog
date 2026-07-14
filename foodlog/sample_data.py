"""示例数据生成

为 `foodlog init` 命令提供 14 天（两周）的模拟饮食记录，
覆盖外卖/自炊/下馆子、各餐次、多种食物类别与标签。

数据设计要点：
- 近 7 天（第 1~7 天）蛋白质摄入偏低（日均 < 60g），以便推荐引擎
  识别蛋白质缺口并从更早的高蛋白历史记录中给出推荐。
- 第 8~14 天营养相对均衡，且包含黄焖鸡米饭、黑椒牛排、鸡胸肉沙拉、
  韩式烤肉饭等富含蛋白质的套餐，作为推荐引擎的候选来源。
- 涵盖咖啡/奶茶/大餐/聚餐标签、高热量单餐、高支出日、奶茶同日两次
  等异常场景，以完整展示统计与异常标注功能。
"""

from datetime import date, timedelta
from typing import List

from .database import Meal


def _ddays_ago(days: int) -> str:
    """返回距今 days 天前的日期字符串（YYYY-MM-DD）"""
    return (date.today() - timedelta(days=days)).isoformat()


def generate_sample_meals() -> List[Meal]:
    """生成 14 天的示例饮食记录。

    覆盖：
    - 来源：takeout / home / restaurant
    - 餐次：breakfast / lunch / dinner / snack
    - 标签：咖啡 / 奶茶 / 大餐 / 聚餐
    - 食物类别：主食 / 肉类 / 蔬菜 / 饮品 / 水果 / 其他
    - 热量、蛋白质、碳水、脂肪、价格合理
    """
    # 每条记录字段顺序：
    # date, time, meal_type, source, food_name, food_category,
    # staple_food, meat_type, vegetable_type, taste,
    # calories, protein, carbs, fat, price, tags, notes
    raw = [
        # ========== 第 8~14 天（较早一周，营养较均衡，含高蛋白历史套餐）==========

        # ---------- 第 14 天 ---------- 含黄焖鸡米饭（高蛋白，推荐候选）
        (_ddays_ago(13), "08:00", "breakfast", "home", "燕麦牛奶+水煮蛋",
         "主食", None, "蛋类,奶类", None, "清淡", 350, 18, 42, 10, 5, None, "自炊早餐"),
        (_ddays_ago(13), "12:30", "lunch", "takeout", "黄焖鸡米饭",
         "主食", "米饭", "鸡鸭", None, "清淡", 640, 38, 88, 18, 30, None, "外卖"),
        (_ddays_ago(13), "19:00", "dinner", "home", "番茄炒蛋+白米饭",
         "蔬菜", "米饭", "蛋or植物", "瓜果茄", "清淡", 520, 16, 78, 14, 8, None, "自炊"),

        # ---------- 第 13 天 ---------- 黑椒牛排大餐（高蛋白，推荐候选），高支出
        (_ddays_ago(12), "08:10", "breakfast", "takeout", "拿铁咖啡+三明治",
         "饮品", None, "奶类", None, None, 420, 18, 45, 18, 28, "咖啡", "早餐外带"),
        (_ddays_ago(12), "13:00", "lunch", "restaurant", "黑椒牛排+意面",
         "肉类", "意面", "牛羊", None, "清淡", 820, 48, 70, 38, 128, "大餐", "周末犒劳自己"),
        (_ddays_ago(12), "20:00", "dinner", "takeout", "麻辣烫",
         "蔬菜", None, "牛羊,鱼虾", "叶子菜,菌菇", "辣", 560, 24, 50, 26, 35, None, "外卖"),

        # ---------- 第 12 天 ---------- 鸡胸肉沙拉（高蛋白，推荐候选），奶茶
        (_ddays_ago(11), "07:50", "breakfast", "home", "豆浆+油条",
         "主食", "其他", None, None, None, 420, 12, 52, 20, 6, None, "自炊早餐"),
        (_ddays_ago(11), "12:40", "lunch", "takeout", "鸡胸肉沙拉",
         "蔬菜", None, "鸡鸭", "叶子菜", "清淡", 320, 36, 18, 12, 38, None, "轻食"),
        (_ddays_ago(11), "15:30", "snack", "takeout", "珍珠奶茶",
         "饮品", None, "奶类", None, "甜", 380, 4, 65, 12, 22, "奶茶", "下午茶"),
        (_ddays_ago(11), "19:00", "dinner", "home", "红烧肉+炒青菜+米饭",
         "肉类", "米饭", "猪肉", "叶子菜", "油", 760, 34, 72, 38, 12, None, "自炊"),

        # ---------- 第 11 天 ---------- 韩式烤肉饭大餐（高蛋白，推荐候选），高支出
        (_ddays_ago(10), "08:30", "breakfast", "takeout", "美式咖啡+可颂",
         "饮品", "面包", None, None, None, 380, 8, 38, 22, 30, "咖啡", None),
        (_ddays_ago(10), "12:30", "lunch", "restaurant", "韩式烤肉饭",
         "肉类", "米饭", "牛羊", None, "清淡", 780, 42, 72, 32, 88, "大餐", "下馆子"),
        (_ddays_ago(10), "19:00", "dinner", "home", "清蒸鱼+时蔬",
         "蔬菜", None, "鱼虾", "叶子菜", "清淡", 420, 38, 22, 14, 25, None, "清淡晚餐"),

        # ---------- 第 10 天 ---------- 低支出自炊，水果
        (_ddays_ago(9), "08:00", "breakfast", "home", "小米粥+咸蛋",
         "其他", "米饭", "蛋or植物", None, "清淡", 280, 12, 40, 8, 4, None, "自炊"),
        (_ddays_ago(9), "12:30", "lunch", "home", "蛋炒饭",
         "主食", "米饭", "蛋or植物", None, "清淡", 480, 14, 70, 16, 5, None, "自炊"),
        (_ddays_ago(9), "15:00", "snack", "home", "时令水果拼盘",
         "水果", None, None, None, None, 180, 2, 46, 1, 8, None, "健康加餐"),

        # ---------- 第 9 天 ----------
        (_ddays_ago(8), "08:20", "breakfast", "takeout", "拿铁咖啡+贝果",
         "饮品", "面包", "奶类", None, None, 360, 10, 52, 14, 32, "咖啡", None),
        (_ddays_ago(8), "12:50", "lunch", "takeout", "照烧鸡腿饭",
         "主食", "米饭", "鸡鸭", None, "清淡", 680, 32, 95, 16, 32, None, "外卖"),
        (_ddays_ago(8), "19:10", "dinner", "home", "宫保鸡丁+米饭",
         "肉类", "米饭", "鸡鸭", None, "油", 620, 30, 75, 22, 10, None, "自炊"),

        # ---------- 第 8 天 ---------- 寿司聚餐，奶茶
        (_ddays_ago(7), "07:40", "breakfast", "home", "鸡蛋三明治+牛奶",
         "主食", "面包", "蛋类,奶类", None, "清淡", 400, 22, 38, 16, 7, None, None),
        (_ddays_ago(7), "12:30", "lunch", "restaurant", "寿司套餐",
         "主食", None, "鱼虾", None, "清淡", 580, 28, 90, 14, 98, "聚餐", "朋友聚餐"),
        (_ddays_ago(7), "15:00", "snack", "takeout", "芋圆奶茶",
         "饮品", None, "奶类", None, "甜", 420, 5, 70, 14, 24, "奶茶", None),
        (_ddays_ago(7), "20:00", "dinner", "takeout", "汉堡套餐",
         "肉类", "汉堡披萨", "牛肉", None, "油", 880, 32, 88, 44, 45, None, "外卖"),

        # ========== 第 1~7 天（近 7 天，蛋白质偏低以触发推荐缺口）==========

        # ---------- 第 7 天 ---------- 蛋白质偏低
        (_ddays_ago(6), "08:10", "breakfast", "takeout", "拿铁咖啡+三明治",
         "饮品", "面包", "奶类", None, None, 420, 10, 45, 18, 28, "咖啡", "早餐外带"),
        (_ddays_ago(6), "12:30", "lunch", "takeout", "照烧鸡腿饭",
         "主食", "米饭", "鸡鸭", None, "清淡", 680, 22, 95, 16, 32, None, "外卖午餐"),
        (_ddays_ago(6), "19:20", "dinner", "home", "番茄炒蛋+白米饭",
         "蔬菜", "米饭", "蛋or植物", "瓜果茄", "清淡", 520, 8, 78, 14, 8, None, "自炊"),

        # ---------- 第 6 天 ---------- 低支出自炊为主
        (_ddays_ago(5), "07:50", "breakfast", "home", "燕麦牛奶+水煮蛋",
         "主食", None, "蛋类,奶类", None, "清淡", 350, 12, 42, 10, 5, None, "自炊早餐"),
        (_ddays_ago(5), "13:00", "lunch", "home", "鸡肉卷饼",
         "其他", "其他", "鸡鸭", None, "清淡", 380, 18, 40, 16, 8, None, "自炊"),
        (_ddays_ago(5), "20:00", "dinner", "home", "蔬菜豆腐汤",
         "蔬菜", None, None, "豆类", "清淡", 320, 12, 18, 10, 6, None, "清淡自炊"),

        # ---------- 第 5 天 ---------- 奶茶×2（异常），无蔬菜，高支出
        (_ddays_ago(4), "08:30", "breakfast", "takeout", "美式咖啡+可颂",
         "饮品", "面包", None, None, None, 380, 6, 38, 22, 30, "咖啡", None),
        (_ddays_ago(4), "12:40", "lunch", "takeout", "意面",
         "主食", "意面", None, None, "清淡", 520, 14, 78, 18, 28, None, "外卖"),
        (_ddays_ago(4), "15:30", "snack", "takeout", "珍珠奶茶",
         "饮品", None, "奶类", None, "甜", 380, 4, 65, 12, 22, "奶茶", "下午茶"),
        (_ddays_ago(4), "16:30", "snack", "takeout", "芋圆奶茶",
         "饮品", None, "奶类", None, "甜", 420, 4, 70, 14, 24, "奶茶", "又一杯"),

        # ---------- 第 4 天 ---------- 火锅大餐>1000kcal，聚餐，高支出
        (_ddays_ago(3), "07:40", "breakfast", "home", "豆浆+油条",
         "主食", "其他", None, None, None, 420, 8, 52, 20, 6, None, None),
        (_ddays_ago(3), "12:20", "lunch", "restaurant", "麻辣火锅套餐",
         "肉类", None, "牛羊,鱼虾", "叶子菜,菌菇", "辣", 1100, 40, 60, 72, 168, "聚餐,大餐", "同事聚餐"),
        (_ddays_ago(3), "19:30", "dinner", "home", "清蒸鱼+时蔬",
         "蔬菜", None, "鱼虾", "叶子菜", "清淡", 420, 20, 22, 14, 25, None, "清淡晚餐"),

        # ---------- 第 3 天 ---------- 无蔬菜，有水果
        (_ddays_ago(2), "08:00", "breakfast", "takeout", "美式咖啡+贝果",
         "饮品", "面包", None, None, None, 360, 6, 52, 14, 32, "咖啡", None),
        (_ddays_ago(2), "12:50", "lunch", "takeout", "蛋炒饭",
         "主食", "米饭", "蛋or植物", None, "清淡", 520, 12, 75, 16, 15, None, "外卖"),
        (_ddays_ago(2), "16:00", "snack", "home", "时令水果拼盘",
         "水果", None, None, None, None, 180, 2, 46, 1, 8, None, "健康加餐"),
        (_ddays_ago(2), "19:10", "dinner", "takeout", "汉堡套餐",
         "肉类", "汉堡披萨", "牛肉", None, "油", 880, 24, 88, 44, 45, None, "外卖"),

        # ---------- 第 2 天 ---------- 低支出全自炊，无蔬菜
        (_ddays_ago(1), "07:30", "breakfast", "home", "鸡蛋三明治+牛奶",
         "主食", "面包", "蛋类,奶类", None, "清淡", 400, 14, 38, 16, 7, None, None),
        (_ddays_ago(1), "12:30", "lunch", "home", "蛋炒饭",
         "主食", "米饭", "蛋or植物", None, "清淡", 520, 12, 75, 16, 5, None, "自炊"),
        (_ddays_ago(1), "20:00", "dinner", "home", "清汤面+煎蛋",
         "其他", "汤面汤粉", "蛋or植物", None, "清淡", 380, 10, 55, 12, 6, None, "自炊"),

        # ---------- 第 1 天（今天）---------- 无蔬菜，大餐>1000kcal，高支出
        (_ddays_ago(0), "08:20", "breakfast", "takeout", "拿铁咖啡+可颂",
         "饮品", "面包", "奶类", None, None, 400, 8, 42, 20, 32, "咖啡", None),
        (_ddays_ago(0), "12:40", "lunch", "home", "番茄牛腩面",
         "主食", "汤面汤粉", "牛肉", None, "清淡", 620, 20, 72, 18, 14, None, "自炊午餐"),
        (_ddays_ago(0), "19:30", "dinner", "restaurant", "川菜双人套餐",
         "肉类", None, "猪肉,鸡鸭", None, "辣", 1050, 28, 70, 56, 158, "大餐", "下馆子"),
    ]

    meals: List[Meal] = []
    for (
        d, t, meal_type, source, food_name, food_category,
        staple_food, meat_type, vegetable_type, taste,
        calories, protein, carbs, fat, price, tags, notes,
    ) in raw:
        meals.append(
            Meal(
                date=d,
                time=t,
                meal_type=meal_type,
                source=source,
                food_name=food_name,
                food_category=food_category,
                staple_food=staple_food,
                meat_type=meat_type,
                vegetable_type=vegetable_type,
                taste=taste,
                calories=calories,
                protein=protein,
                carbs=carbs,
                fat=fat,
                price=price,
                tags=tags,
                notes=notes,
            )
        )
    return meals

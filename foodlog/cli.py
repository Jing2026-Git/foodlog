"""饭记 CLI 入口

基于 typer 实现的命令行工具，提供所有子命令入口。
"""

import csv
import os
import sqlite3
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .database import Database, Meal
from .sample_data import generate_sample_meals

app = typer.Typer(
    name="foodlog",
    help="🍚 饭记 - 日常饮食记录平台",
    no_args_is_help=True,
)

console = Console()


# ----------------------------------------------------------------------
# 内部工具：数据库就绪检查与友好错误提示
# ----------------------------------------------------------------------


def _db_path() -> str:
    """获取当前数据库路径（环境变量优先）"""
    return os.environ.get("DATABASE_PATH", "data/foodlog.db")


def _check_db_ready() -> bool:
    """检查数据库是否存在且有数据，无数据时打印引导提示并返回 False。"""
    path = _db_path()
    if not os.path.exists(path):
        console.print(
            Panel.fit(
                "[yellow]⚠️  数据库尚未初始化[/yellow]\n\n"
                f"[dim]未找到数据库文件：{path}[/dim]\n"
                "[dim]请先运行 [bold]foodlog init[/bold] 创建数据库并加载示例数据。[/dim]",
                border_style="yellow",
            )
        )
        return False
    try:
        db = Database(db_path=path)
        try:
            count = db.get_meal_count()
        finally:
            db.close()
    except sqlite3.Error as e:
        console.print(
            Panel.fit(
                f"[red]❌ 数据库读取失败[/red]\n\n[red]{e}[/red]\n\n"
                f"[dim]数据库文件可能已损坏：{path}[/dim]\n"
                "[dim]可删除该文件后重新运行 [bold]foodlog init[/bold]。[/dim]",
                border_style="red",
            )
        )
        return False
    if count == 0:
        console.print(
            Panel.fit(
                "[yellow]⚠️  数据库中还没有记录[/yellow]\n\n"
                "[dim]请先运行 [bold]foodlog init[/bold] 加载示例数据，[/dim]\n"
                "[dim]或使用 [bold]foodlog add[/bold] 添加第一条记录。[/dim]",
                border_style="yellow",
            )
        )
        return False
    return True


def _print_db_error(e: Exception) -> None:
    """打印数据库操作失败的友好错误（不暴露完整堆栈）"""
    console.print(
        Panel.fit(
            f"[red]❌ 数据库操作失败[/red]\n\n[red]{e}[/red]\n\n"
            "[dim]请检查数据库文件权限或稍后重试。[/dim]",
            border_style="red",
        )
    )


@app.command()
def init():
    """初始化数据库和示例数据"""
    db_path = _db_path()

    console.print(
        Panel.fit(
            "[bold]🍚 饭记初始化[/bold]\n创建数据库并准备示例数据",
            border_style="green",
        )
    )

    # 创建/打开数据库（自动建表、自动建目录）
    try:
        db = Database(db_path=db_path)
    except sqlite3.Error as e:
        _print_db_error(e)
        raise typer.Exit(code=1)
    try:
        existing = db.get_meal_count()

        if existing > 0:
            # 数据库已有数据，跳过示例数据插入，避免重复
            console.print(
                f"\n[yellow]⚠️  数据库已存在且包含 {existing} 条记录，跳过示例数据插入。[/yellow]"
            )
            console.print(
                f"[dim]如需重新初始化，请删除 {db_path} 后再执行 foodlog init。[/dim]"
            )
        else:
            meals = generate_sample_meals()
            inserted = 0
            for meal in meals:
                db.insert_meal(meal)
                inserted += 1

            console.print(
                f"\n[green]✅ 数据库已创建：[/green] [bold]{db_path}[/bold]"
            )
            console.print(
                f"[green]✅ 已插入示例数据：[/green] [bold]{inserted}[/bold] 条记录"
            )

        # 展示初始化后的统计概览
        _print_summary(db)
    except sqlite3.Error as e:
        _print_db_error(e)
        raise typer.Exit(code=1)
    finally:
        db.close()


def _print_summary(db: Database) -> None:
    """用 rich 打印数据库初始化后的统计概览"""
    total = db.get_meal_count()
    confirmed = db.get_confirmed_meals()

    # 来源统计
    source_counts: dict = {}
    category_counts: dict = {}
    total_calories = 0.0
    total_price = 0.0
    for m in confirmed:
        source_counts[m.source] = source_counts.get(m.source, 0) + 1
        if m.food_category:
            category_counts[m.food_category] = category_counts.get(m.food_category, 0) + 1
        if m.calories:
            total_calories += m.calories
        if m.price:
            total_price += m.price

    console.print("\n[bold cyan]📊 数据概览[/bold cyan]")

    info = Table(show_header=False, box=None, padding=(0, 1))
    info.add_column("key", style="dim")
    info.add_column("value", style="bold")
    info.add_row("总记录数", str(total))
    info.add_row("已确认记录", str(len(confirmed)))
    info.add_row("累计热量", f"{total_calories:.0f} kcal")
    info.add_row("累计支出", f"¥ {total_price:.2f}")
    console.print(info)

    # 来源分布
    src_table = Table(title="来源分布", show_lines=False)
    src_table.add_column("来源", style="cyan")
    src_table.add_column("记录数", justify="right")
    for src in ("takeout", "home", "restaurant"):
        src_table.add_row(src, str(source_counts.get(src, 0)))
    console.print(src_table)

    # 食物类别分布
    if category_counts:
        cat_table = Table(title="食物类别分布", show_lines=False)
        cat_table.add_column("类别", style="yellow")
        cat_table.add_column("记录数", justify="right")
        for cat, cnt in sorted(
            category_counts.items(), key=lambda x: (-x[1], x[0])
        ):
            cat_table.add_row(cat, str(cnt))
        console.print(cat_table)

    # 标签统计
    tags = db.get_all_tags()
    if tags:
        tag_table = Table(title="标签统计")
        tag_table.add_column("标签", style="magenta")
        tag_table.add_column("次数", justify="right")
        tag_table.add_column("累计支出", justify="right", style="green")
        for t in tags:
            tag_table.add_row(t["tag"], str(t["count"]), f"¥ {t['total_price']:.2f}")
        console.print(tag_table)

    console.print("\n[green]🎉 初始化完成！使用 [bold]foodlog --help[/bold] 查看可用命令。[/green]")


def _prompt_float_required(prompt_text: str) -> float:
    """提示用户输入必填的数值，无效时重新提示。"""
    while True:
        raw = typer.prompt(prompt_text)
        try:
            return float(raw)
        except (ValueError, TypeError):
            console.print(
                f"[red]⚠️  无效的数字 “{raw}”，请重新输入。[/red]"
            )


def _prompt_float_optional(prompt_text: str) -> Optional[float]:
    """提示用户输入可跳过的数值，回车返回 None，无效时重新提示。"""
    while True:
        raw = typer.prompt(prompt_text, default="")
        if raw.strip() == "":
            return None
        try:
            return float(raw.strip())
        except (ValueError, TypeError):
            console.print(
                f"[red]⚠️  无效的数字 “{raw}”，请重新输入（或直接回车跳过）。[/red]"
            )


def _collect_meal_input() -> Meal:
    """交互式收集一条饮食记录，返回 Meal 对象（不含 id 与时间戳）。"""
    now = datetime.now()
    date_str = typer.prompt(
        "日期 (YYYY-MM-DD，回车默认今天)", default=now.strftime("%Y-%m-%d")
    )
    time_str = typer.prompt(
        "时间 (HH:MM，回车默认现在)", default=now.strftime("%H:%M")
    )
    meal_type = typer.prompt(
        "餐次 [breakfast/lunch/dinner/snack] (回车默认lunch)", default="lunch"
    )
    source = typer.prompt(
        "来源 [takeout/home/restaurant] (回车默认takeout)", default="takeout"
    )
    food_name = typer.prompt("食物名称")
    food_category_raw = typer.prompt(
        "食物类别 [主食/肉类/蔬菜/饮品/水果/其他]", default=""
    )
    food_category = food_category_raw.strip() or None
    calories = _prompt_float_required("热量 (kcal)")
    protein = _prompt_float_optional("蛋白质 (g，可跳过)")
    carbs = _prompt_float_optional("碳水 (g，可跳过)")
    fat = _prompt_float_optional("脂肪 (g，可跳过)")
    price = _prompt_float_required("价格 (元)")
    tags_raw = typer.prompt("标签 (逗号分隔，可跳过)", default="")
    tags = tags_raw.strip() or None
    notes_raw = typer.prompt("备注 (可跳过)", default="")
    notes = notes_raw.strip() or None

    return Meal(
        date=date_str,
        time=time_str,
        meal_type=meal_type,
        source=source,
        food_name=food_name,
        food_category=food_category,
        calories=calories,
        protein=protein,
        carbs=carbs,
        fat=fat,
        price=price,
        tags=tags,
        notes=notes,
        status="confirmed",
    )


@app.command()
def add():
    """交互式添加记录"""
    console.print("\n[bold cyan]📝 添加饮食记录[/bold cyan]\n")

    meal = _collect_meal_input()

    db = Database(db_path=_db_path())
    try:
        meal_id = db.insert_meal(meal)
    except sqlite3.Error as e:
        _print_db_error(e)
        raise typer.Exit(code=1)
    finally:
        db.close()

    console.print(
        f"\n[green]✅ 已保存记录 #{meal_id}:[/green] [bold]{meal.food_name}[/bold]"
    )


@app.command()
def screenshot(
    path: str = typer.Argument(..., help="截图文件路径"),
):
    """识别截图并生成草稿记录"""
    from .ai_recognizer import recognize_screenshot
    from .database import Meal

    # 文件存在性检查（在调用 AI 前给出友好提示）
    if not os.path.exists(path):
        console.print(
            Panel.fit(
                f"[red]❌ 文件不存在[/red]\n\n[red]{path}[/red]\n\n"
                "[dim]请确认文件路径是否正确。[/dim]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    console.print(f"[cyan]📸 正在识别截图:[/cyan] {path}")

    result = recognize_screenshot(path)

    if not result.get("success"):
        err = result.get("error", "未知错误")
        err_type = result.get("error_type", "unknown")
        console.print(
            Panel.fit(
                f"[bold red]❌ 识别失败[/bold red]\n\n"
                f"[red]{err}[/red]\n\n"
                f"[dim]错误类型: {err_type}[/dim]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    data = result["data"]
    raw_response = result.get("raw_response", "")

    # 写入数据库（status=draft）
    db = Database(db_path=_db_path())
    try:
        meal = Meal(
            date=datetime.now().strftime("%Y-%m-%d"),
            time=datetime.now().strftime("%H:%M"),
            meal_type=data.get("meal_type") or "snack",
            source=data.get("source") or "takeout",
            food_name=data.get("food_name") or "未识别",
            food_category=data.get("food_category"),
            staple_food=data.get("staple_food"),
            meat_type=data.get("meat_type"),
            vegetable_type=data.get("vegetable_type"),
            taste=data.get("taste"),
            calories=data.get("calories"),
            protein=data.get("protein"),
            carbs=data.get("carbs"),
            fat=data.get("fat"),
            price=data.get("price"),
            tags=data.get("tags"),
            notes=data.get("notes"),
            screenshot_path=path,
            ai_raw_response=raw_response,
            status="draft",
        )
        meal_id = db.insert_meal(meal)
    except sqlite3.Error as e:
        _print_db_error(e)
        raise typer.Exit(code=1)
    finally:
        db.close()

    # 打印识别结果
    console.print(
        Panel.fit(
            "[bold green]✅ 识别成功（已存为草稿，可用 foodlog 确认）[/bold green]",
            border_style="green",
        )
    )

    table = Table(title="识别结果", show_lines=False)
    table.add_column("字段", style="cyan", no_wrap=True)
    table.add_column("值", style="white")
    table.add_row("记录ID", f"#{meal_id}")
    table.add_row("食物名称", str(data.get("food_name", "")))
    table.add_row("食物类别", str(data.get("food_category", "")))
    table.add_row("热量", _fmt_num(data.get("calories"), "kcal"))
    table.add_row("蛋白质", _fmt_num(data.get("protein"), "g"))
    table.add_row("碳水", _fmt_num(data.get("carbs"), "g"))
    table.add_row("脂肪", _fmt_num(data.get("fat"), "g"))
    table.add_row("价格", _fmt_price(data.get("price")))
    table.add_row("来源", str(data.get("source", "")))
    table.add_row("餐次", str(data.get("meal_type", "")))
    table.add_row("标签", str(data.get("tags", "")))
    table.add_row("备注", str(data.get("notes", "")))
    console.print(table)


def _fmt_num(v, unit: str) -> str:
    """格式化数值显示"""
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.1f} {unit}"
    return f"{v} {unit}"


def _fmt_price(v) -> str:
    """格式化价格显示"""
    if v is None:
        return "-"
    try:
        return f"¥ {float(v):.2f}"
    except (TypeError, ValueError):
        return "-"


_MEAL_TYPE_NAMES = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
}

# 营养素单位（用于推荐展示）
_NUTRIENT_UNITS = {
    "calories": "kcal",
    "protein": "g",
    "carbs": "g",
    "fat": "g",
}

# 营养缺口严重程度展示
_SEVERITY_NAMES = {"mild": "轻微", "moderate": "中等", "severe": "严重"}
_SEVERITY_STYLES = {"mild": "yellow", "moderate": "red", "severe": "bold red"}


@app.command()
def today():
    """查看今日饮食总结"""
    from foodlog.stats import daily_summary

    if not _check_db_ready():
        raise typer.Exit(code=1)

    try:
        summary = daily_summary()
    except sqlite3.Error as e:
        _print_db_error(e)
        raise typer.Exit(code=1)

    # 1. 日期标题
    console.print(
        Panel.fit(
            f"[bold cyan]🍚 今日饮食总结 · {summary['date']}[/bold cyan]",
            border_style="cyan",
        )
    )

    # 2. 统计卡片
    stat_table = Table(show_header=False, box=None, padding=(0, 2))
    stat_table.add_column("key", style="bold")
    stat_table.add_column("value", style="white")
    for label, value in (
        ("总热量", f"{summary['total_calories']:.0f} kcal"),
        ("总支出", f"¥ {summary['total_price']:.1f}"),
        ("蛋白质", f"{summary['total_protein']:.1f} g"),
        ("碳水", f"{summary['total_carbs']:.1f} g"),
        ("脂肪", f"{summary['total_fat']:.1f} g"),
        ("餐数", str(summary["meal_count"])),
    ):
        stat_table.add_row(label, value)
    console.print(Panel(stat_table, title="📊 营养概览", border_style="blue"))

    # 3. 各餐次明细
    meal_table = Table(title="🍽️ 各餐次明细", show_lines=False)
    meal_table.add_column("餐次", style="cyan", no_wrap=True)
    meal_table.add_column("食物名", style="white")
    meal_table.add_column("热量", justify="right")
    meal_table.add_column("蛋白质", justify="right")
    meal_table.add_column("价格", justify="right", style="green")
    meal_table.add_column("标签", style="magenta")

    has_items = False
    for mt in ("breakfast", "lunch", "dinner", "snack"):
        mt_data = summary["by_meal_type"].get(mt, {})
        for item in mt_data.get("items", []):
            has_items = True
            meal_table.add_row(
                _MEAL_TYPE_NAMES.get(mt, mt),
                item.food_name,
                f"{(item.calories or 0):.0f}",
                f"{(item.protein or 0):.1f}",
                f"¥ {(item.price or 0):.1f}",
                item.tags or "",
            )
    if has_items:
        console.print(meal_table)
    else:
        console.print("[dim]今天还没有记录哦～[/dim]")

    # 4. 营养评价
    if summary["evaluations"]:
        eval_text = "\n".join(f"• {e}" for e in summary["evaluations"])
        console.print(Panel(eval_text, title="💡 营养评价", border_style="yellow"))

    # 5. tag 统计
    if summary["tags"]:
        tag_table = Table(title="🏷️ 标签统计", show_lines=False)
        tag_table.add_column("标签", style="magenta")
        tag_table.add_column("次数", justify="right")
        tag_table.add_column("累计支出", justify="right", style="green")
        for tag, info in summary["tags"].items():
            tag_table.add_row(tag, str(info["count"]), f"¥ {info['total_price']:.1f}")
        console.print(tag_table)


@app.command()
def week():
    """查看本周饮食报告"""
    from foodlog.stats import weekly_summary

    if not _check_db_ready():
        raise typer.Exit(code=1)

    try:
        summary = weekly_summary()
    except sqlite3.Error as e:
        _print_db_error(e)
        raise typer.Exit(code=1)

    # 1. 周范围标题
    console.print(
        Panel.fit(
            f"[bold cyan]📅 本周饮食报告 · "
            f"{summary['week_start']} ~ {summary['week_end']}[/bold cyan]",
            border_style="cyan",
        )
    )

    # 2. 周报概览
    overview = Table(show_header=False, box=None, padding=(0, 2))
    overview.add_column("a", style="bold")
    overview.add_column("b", style="bold")
    overview.add_row(
        f"总热量: {summary['total_calories']:.0f} kcal",
        f"日均: {summary['avg_daily_calories']:.0f} kcal",
    )
    overview.add_row(
        f"总支出: ¥ {summary['total_price']:.1f}",
        f"日均: ¥ {summary['avg_daily_price']:.1f}",
    )
    overview.add_row(
        f"总蛋白质: {summary['total_protein']:.1f} g",
        f"日均: {summary['avg_protein']:.1f} g",
    )
    console.print(Panel(overview, title="📊 周报概览", border_style="blue"))

    # 3. 本周无记录时的友好提示
    if summary["meal_count"] == 0:
        console.print(
            Panel(
                "[dim]本周还没有记录哦～ 使用 [bold]foodlog add[/bold] 或上传截图开始记录。[/dim]",
                title="📝 暂无数据",
                border_style="yellow",
            )
        )
        return

    # 4. 每日热量趋势
    daily_table = Table(title="📈 每日趋势", show_lines=False)
    daily_table.add_column("日期", style="cyan")
    daily_table.add_column("热量", justify="right")
    daily_table.add_column("支出", justify="right", style="green")
    daily_table.add_column("餐数", justify="right")
    daily_table.add_column("蛋白质", justify="right")
    for d in summary["daily_data"]:
        daily_table.add_row(
            d["date"],
            f"{d['calories']:.0f}",
            f"¥ {d['price']:.1f}",
            str(d["meal_count"]),
            f"{d['protein']:.1f}",
        )
    console.print(daily_table)

    # 4. tag 统计
    if summary["tags"]:
        tag_table = Table(title="🏷️ 标签统计", show_lines=False)
        tag_table.add_column("标签", style="magenta")
        tag_table.add_column("次数", justify="right")
        tag_table.add_column("累计支出", justify="right", style="green")
        for tag, info in summary["tags"].items():
            tag_table.add_row(tag, str(info["count"]), f"¥ {info['total_price']:.1f}")
        console.print(tag_table)

    # 5. 异常标注
    if summary["anomalies"]:
        anom_text = "\n".join(
            f"• [{a['date']}] {a['description']}" for a in summary["anomalies"]
        )
        console.print(Panel(anom_text, title="⚠️ 异常标注", border_style="red"))

    # 6. 与上周对比
    comp = summary["comparison"]
    has_comp = any(v is not None for v in comp.values())
    if has_comp:
        comp_table = Table(title="🔄 与上周对比", show_lines=False)
        comp_table.add_column("指标", style="cyan")
        comp_table.add_column("变化", justify="right")
        for label, key in (
            ("热量", "calories_change"),
            ("支出", "price_change"),
            ("蛋白质", "protein_change"),
        ):
            val = comp[key]
            if val is None:
                disp = "-"
            elif val >= 0:
                disp = f"[red]+{val:.1f}%[/red]"
            else:
                disp = f"[green]{val:.1f}%[/green]"
            comp_table.add_row(label, disp)
        console.print(comp_table)

    # 7. 营养评价
    if summary["evaluations"]:
        eval_text = "\n".join(f"• {e}" for e in summary["evaluations"])
        console.print(Panel(eval_text, title="💡 营养评价", border_style="yellow"))


@app.command()
def recommend():
    """获取饮食推荐"""
    from foodlog.recommender import get_recommendations

    if not _check_db_ready():
        raise typer.Exit(code=1)

    try:
        result = get_recommendations()
    except sqlite3.Error as e:
        _print_db_error(e)
        raise typer.Exit(code=1)

    # 1. 通用建议（数据不足时）
    if result.get("general_advice"):
        console.print(
            Panel(
                result["general_advice"],
                title="💡 通用建议",
                border_style="yellow",
            )
        )

    # 2. 营养缺口分析
    gaps = result.get("nutrient_gaps") or []
    if gaps:
        gap_table = Table(title="📊 营养缺口分析", show_lines=False)
        gap_table.add_column("营养素", style="cyan")
        gap_table.add_column("日均摄入", justify="right")
        gap_table.add_column("推荐", justify="right")
        gap_table.add_column("缺口", justify="right", style="red")
        gap_table.add_column("严重程度", justify="center")

        for g in gaps:
            unit = _NUTRIENT_UNITS.get(g["nutrient"], "")
            sev = g["severity"]
            style = _SEVERITY_STYLES.get(sev, "white")
            gap_table.add_row(
                g["display_name"],
                _fmt_num(g["avg_intake"], unit),
                _fmt_num(g["recommended"], unit),
                _fmt_num(g["deficiency"], unit),
                f"[{style}]{_SEVERITY_NAMES.get(sev, sev)}[/{style}]",
            )
        console.print(gap_table)
        for g in gaps:
            console.print(f"  [dim]• {g['description']}[/dim]")

    # 3. 推荐列表（每个推荐一张卡片）
    recs = result.get("recommendations") or []
    if recs:
        for rec in recs:
            meal = rec["meal"]
            detail = (
                f"[bold green]{rec['recommendation_text']}[/bold green]\n"
                f"[dim]上次记录：{rec['last_date']}"
                f" · {_MEAL_TYPE_NAMES.get(meal.meal_type, meal.meal_type)}"
                f" · {meal.food_category or '未分类'}"
                f" · {_fmt_price(meal.price)}[/dim]\n"
                f"[dim]推荐理由：{rec['reason']}[/dim]"
            )
            console.print(
                Panel(
                    detail,
                    title=f"🍽️ {rec['display_name']}推荐",
                    border_style="green",
                )
            )

    # 4. 今日提醒
    reminders = result.get("reminders") or []
    if reminders:
        rem_text = "\n".join(f"• {r}" for r in reminders)
        console.print(Panel(rem_text, title="⏰ 今日提醒", border_style="yellow"))

    # 兜底：什么都没有
    if not (result.get("general_advice") or gaps or recs or reminders):
        console.print("[dim]暂无推荐信息，继续记录饮食以获取个性化推荐。[/dim]")


@app.command()
def export(
    output: str = typer.Option(
        "foodlog_export.csv", "--output", "-o", help="输出文件路径"
    ),
    start_date: str = typer.Option(
        None, "--start", "-s", help="开始日期 YYYY-MM-DD"
    ),
    end_date: str = typer.Option(None, "--end", "-e", help="结束日期 YYYY-MM-DD"),
):
    """导出饮食记录为CSV"""
    db = Database(db_path=_db_path())
    try:
        if start_date and end_date:
            meals = db.get_meals_by_date_range(start_date, end_date)
        elif start_date:
            meals = db.get_meals_by_date_range(start_date, "9999-12-31")
        elif end_date:
            meals = db.get_meals_by_date_range("0000-01-01", end_date)
        else:
            meals = db.get_all_meals(limit=10**9, offset=0)
    except sqlite3.Error as e:
        _print_db_error(e)
        raise typer.Exit(code=1)
    finally:
        db.close()

    if not meals:
        console.print(
            "[yellow]⚠️  没有符合条件的记录可导出。[/yellow]"
        )
        raise typer.Exit(code=0)

    columns = [
        "id",
        "date",
        "time",
        "meal_type",
        "source",
        "food_name",
        "food_category",
        "calories",
        "protein",
        "carbs",
        "fat",
        "price",
        "tags",
        "notes",
        "status",
        "created_at",
    ]

    # utf-8-sig 让 Excel 正确识别中文
    try:
        with open(output, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for m in meals:
                writer.writerow(
                    ["" if getattr(m, col) is None else getattr(m, col) for col in columns]
                )
    except OSError as e:
        console.print(
            Panel.fit(
                f"[red]❌ 文件写入失败[/red]\n\n[red]{e}[/red]\n\n"
                f"[dim]输出路径：{output}[/dim]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    console.print(
        f"[green]✅ 已导出 [/green][bold]{len(meals)}[/bold][green] 条记录到[/green] "
        f"[bold]{output}[/bold]"
    )


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="监听地址"),
    port: int = typer.Option(None, "--port", "-p", help="端口"),
    reload: bool = typer.Option(False, "--reload", help="开发模式热重载"),
):
    """启动Web服务"""
    import uvicorn

    # 端口优先级：--port > WEB_PORT 环境变量 > 8000
    if port is None:
        port = int(os.environ.get("WEB_PORT", "8000"))

    # 启动前检查数据库是否已初始化
    db_path = _db_path()
    if not os.path.exists(db_path):
        console.print(
            f"[red]❌ 数据库尚未初始化：{db_path}[/red]"
        )
        console.print(
            "[yellow]请先运行 [bold]foodlog init[/bold] 初始化数据库。[/yellow]"
        )
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            f"[bold cyan]🌐 饭记 Web 服务[/bold cyan]\n"
            f"访问地址: http://127.0.0.1:{port}"
            + (f"\n监听: {host}:{port}" if host != "0.0.0.0" else ""),
            border_style="cyan",
        )
    )

    uvicorn.run(
        "foodlog.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    app()

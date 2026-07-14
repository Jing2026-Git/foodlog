"""FastAPI Web应用

提供饮食记录的查询、增删改查接口，以及截图识别、统计分析、
推荐、搜索、初始化等完整 API。所有业务接口前缀为 ``/api``。

依赖：
- FastAPI / Starlette：Web 框架
- python-multipart：UploadFile 文件上传
- Jinja2Templates：为后续前端页面准备（当前主页返回占位 HTML）
"""

import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from foodlog.database import Database, Meal
from foodlog.sample_data import generate_sample_meals

# ----------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------

# 模板目录（为后续前端准备，当前主页直接返回占位 HTML）
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# 截图保存目录
SCREENSHOTS_DIR = Path("data/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# 创建 Meal 时允许的字段（除 id / created_at / updated_at 外）
_MEAL_WRITABLE_FIELDS = {
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
}

# 手动添加记录时的必填字段
_MEAL_REQUIRED_FIELDS = ("date", "meal_type", "source", "food_name")


# ----------------------------------------------------------------------
# 应用与中间件
# ----------------------------------------------------------------------

app = FastAPI(
    title="饭记 API",
    description="日常饮食记录平台 - 截图识别、营养分析、智能推荐",
    version="0.1.0",
)

# CORS：开发期允许所有源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------
# 全局异常处理：统一错误返回格式
# ----------------------------------------------------------------------


@app.exception_handler(sqlite3.Error)
async def database_exception_handler(request: Request, exc: sqlite3.Error):
    """数据库异常统一返回 500 + 结构化错误"""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": f"数据库错误: {exc}",
            "error_type": "database",
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """未捕获异常统一返回 500，避免暴露堆栈"""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "服务器内部错误，请稍后重试",
            "error_type": "server",
        },
    )


# ----------------------------------------------------------------------
# 内部工具
# ----------------------------------------------------------------------


def _get_db() -> Database:
    """获取数据库连接（每次请求新建，由调用方负责关闭）。

    路径优先级：环境变量 DATABASE_PATH > 默认 data/foodlog.db
    """
    db_path = os.environ.get("DATABASE_PATH", "data/foodlog.db")
    return Database(db_path=db_path)


def _serialize(obj: Any) -> Any:
    """递归地将结果中的 Meal 对象转为 dict。

    stats / recommender 等模块返回的字典中可能嵌套 Meal 对象（如
    daily_summary 的 ``meals``、weekly_summary 的 ``anomalies[].meal``、
    recommender 的 ``recommendations[].meal``）。FastAPI 无法直接序列化
    dataclass，需要先转 dict。
    """
    if isinstance(obj, Meal):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(item) for item in obj]
    return obj


def _error_response(message: str, error_type: str = "unknown") -> Dict[str, Any]:
    """构造统一的错误返回结构"""
    return {"success": False, "error": message, "error_type": error_type}


# ----------------------------------------------------------------------
# 主页
# ----------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index():
    """返回主页 HTML（单页应用）"""
    template_path = Path(__file__).parent / "templates" / "index.html"
    return HTMLResponse(template_path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# 1. 截图上传 + AI 识别
# ----------------------------------------------------------------------


@app.post("/api/screenshot")
async def upload_screenshot(file: UploadFile = File(...)):
    """上传截图，AI识别后生成草稿记录

    流程：
    1. 保存上传的图片到 data/screenshots/
    2. 调用 recognize_screenshot 识别
    3. 识别成功则创建 Meal（status="draft"）存入数据库
    4. 返回识别结果和 meal_id
    """
    if not file or not file.filename:
        return _error_response("未提供文件", "validation")

    # 1. 保存上传文件
    ext = Path(file.filename).suffix.lower() or ".jpg"
    filename = f"{int(time.time() * 1000)}{ext}"
    filepath = SCREENSHOTS_DIR / filename
    try:
        content = await file.read()
        with open(filepath, "wb") as f:
            f.write(content)
    except OSError as e:
        return _error_response(f"保存文件失败: {e}", "io")

    # 2. AI 识别
    try:
        from foodlog.ai_recognizer import recognize_screenshot

        result = recognize_screenshot(str(filepath))
    except Exception as e:  # noqa: BLE001 - 兜底，避免崩溃
        return _error_response(f"AI识别调用失败: {e}", "unknown")

    if not result.get("success"):
        return _error_response(
            result.get("error", "AI识别失败"),
            result.get("error_type", "unknown"),
        )

    data = result.get("data", {}) or {}
    raw_response = result.get("raw_response", "")

    # 3. 写入数据库（status=draft）
    now = datetime.now()
    meal = Meal(
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M"),
        meal_type=data.get("meal_type") or "snack",
        source=data.get("source") or "takeout",
        food_name=data.get("food_name") or "未识别",
        food_category=data.get("food_category") or None,
        staple_food=data.get("staple_food") or None,
        meat_type=data.get("meat_type") or None,
        vegetable_type=data.get("vegetable_type") or None,
        taste=data.get("taste") or None,
        calories=data.get("calories"),
        protein=data.get("protein"),
        carbs=data.get("carbs"),
        fat=data.get("fat"),
        price=data.get("price"),
        tags=data.get("tags") or None,
        notes=data.get("notes") or None,
        screenshot_path=str(filepath),
        ai_raw_response=raw_response,
        status="draft",
    )

    db = _get_db()
    try:
        meal_id = db.insert_meal(meal)
    finally:
        db.close()

    return {
        "success": True,
        "meal_id": meal_id,
        "data": data,
        "screenshot_path": str(filepath),
    }


# ----------------------------------------------------------------------
# 2. 记录列表
# ----------------------------------------------------------------------


@app.get("/api/meals")
async def get_meals(
    date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """获取记录列表

    支持按日期 (date) 或日期范围 (start_date ~ end_date) 过滤，
    支持 status (draft/confirmed) 过滤，支持分页。
    """
    db = _get_db()
    try:
        # 1. 按日期条件查询
        if date:
            all_matching = db.get_meals_by_date(date)
        elif start_date or end_date:
            sd = start_date or "0000-01-01"
            ed = end_date or "9999-12-31"
            all_matching = db.get_meals_by_date_range(sd, ed)
        else:
            all_matching = db.get_all_meals(limit=10 ** 9, offset=0)

        # 2. 状态过滤（在内存中）
        if status:
            all_matching = [m for m in all_matching if m.status == status]

        total = len(all_matching)

        # 3. 分页
        meals = all_matching[offset: offset + limit]
    finally:
        db.close()

    return {"meals": [m.to_dict() for m in meals], "total": total}


# ----------------------------------------------------------------------
# 3. 单条记录
# ----------------------------------------------------------------------


@app.get("/api/meals/{meal_id}")
async def get_meal_by_id(meal_id: int):
    """获取单条记录，不存在返回 404"""
    db = _get_db()
    try:
        meal = db.get_meal_by_id(meal_id)
    finally:
        db.close()
    if meal is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"meal": meal.to_dict()}


# ----------------------------------------------------------------------
# 4. 更新记录
# ----------------------------------------------------------------------


@app.put("/api/meals/{meal_id}")
async def update_meal(meal_id: int, updates: dict = Body(...)):
    """更新记录字段（不允许更新 id）"""
    db = _get_db()
    try:
        existing = db.get_meal_by_id(meal_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="记录不存在")

        ok = db.update_meal(meal_id, updates)
        updated = db.get_meal_by_id(meal_id)
    finally:
        db.close()

    if not ok or updated is None:
        return _error_response("更新失败", "unknown")
    return {"success": True, "meal": updated.to_dict()}


# ----------------------------------------------------------------------
# 5. 删除记录
# ----------------------------------------------------------------------


@app.delete("/api/meals/{meal_id}")
async def delete_meal(meal_id: int):
    """删除记录"""
    db = _get_db()
    try:
        existing = db.get_meal_by_id(meal_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        ok = db.delete_meal(meal_id)
    finally:
        db.close()
    return {"success": ok}


# ----------------------------------------------------------------------
# 6. 手动添加记录
# ----------------------------------------------------------------------


@app.post("/api/meals")
async def create_meal(meal_data: dict = Body(...)):
    """手动添加一条饮食记录"""
    # 过滤允许的字段
    clean: Dict[str, Any] = {
        k: v for k, v in meal_data.items() if k in _MEAL_WRITABLE_FIELDS
    }

    # 必填字段检查
    for field in _MEAL_REQUIRED_FIELDS:
        val = clean.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            raise HTTPException(
                status_code=422, detail=f"缺少必填字段: {field}"
            )

    try:
        meal = Meal(**clean)
    except TypeError as e:
        raise HTTPException(status_code=422, detail=f"字段错误: {e}")

    db = _get_db()
    try:
        meal_id = db.insert_meal(meal)
        created = db.get_meal_by_id(meal_id)
    finally:
        db.close()

    if created is None:
        return _error_response("插入失败", "unknown")
    return {"success": True, "meal_id": meal_id, "meal": created.to_dict()}


# ----------------------------------------------------------------------
# 7. 今日统计
# ----------------------------------------------------------------------


@app.get("/api/today")
async def get_today():
    """今日统计（daily_summary 结果，meals 已转 dict）"""
    from foodlog.stats import daily_summary

    summary = daily_summary()
    return _serialize(summary)


# ----------------------------------------------------------------------
# 8. 周报统计
# ----------------------------------------------------------------------


@app.get("/api/week")
async def get_week(week_start: Optional[str] = None):
    """周报统计（weekly_summary 结果，anomalies 中的 meal 已转 dict）"""
    from foodlog.stats import weekly_summary

    summary = weekly_summary(week_start)
    return _serialize(summary)


# ----------------------------------------------------------------------
# 9. 推荐
# ----------------------------------------------------------------------


@app.get("/api/recommend")
async def get_recommend():
    """饮食推荐（get_recommendations 结果，recommendations 中的 meal 已转 dict）"""
    from foodlog.recommender import get_recommendations

    result = get_recommendations()
    return _serialize(result)


# ----------------------------------------------------------------------
# 10. 关键词搜索
# ----------------------------------------------------------------------


@app.post("/api/search")
async def search(query: str = Body(..., embed=True)):
    """关键词搜索饮食记录

    在 food_name / tags / notes / food_category 字段中搜索关键词，
    返回匹配记录列表和统计汇总（总数、总价格、总热量、日期范围）。
    """
    if not query or not query.strip():
        return {
            "query": query or "",
            "results": [],
            "summary": {
                "total_count": 0,
                "total_price": 0.0,
                "total_calories": 0,
                "date_range": None,
            },
        }

    keyword = query.strip()
    like = f"%{keyword}%"

    db = _get_db()
    try:
        cursor = db.conn.execute(
            """
            SELECT * FROM meals
            WHERE food_name LIKE ?
               OR tags LIKE ?
               OR notes LIKE ?
               OR food_category LIKE ?
               OR staple_food LIKE ?
               OR meat_type LIKE ?
               OR vegetable_type LIKE ?
               OR taste LIKE ?
            ORDER BY date DESC, time IS NULL, time DESC, id DESC
            """,
            (like, like, like, like, like, like, like, like),
        )
        meals: List[Meal] = [Meal.from_db_row(row) for row in cursor.fetchall()]
    finally:
        db.close()

    total_price = round(sum(float(m.price or 0) for m in meals), 2)
    total_calories = int(sum(float(m.calories or 0) for m in meals))

    if meals:
        dates = sorted(d for d in (m.date for m in meals) if d)
        date_range = {"start": dates[0], "end": dates[-1]} if dates else None
    else:
        date_range = None

    return {
        "query": query,
        "results": [m.to_dict() for m in meals],
        "summary": {
            "total_count": len(meals),
            "total_price": total_price,
            "total_calories": total_calories,
            "date_range": date_range,
        },
    }


# ----------------------------------------------------------------------
# 11. 初始化状态
# ----------------------------------------------------------------------


@app.get("/api/init-status")
async def get_init_status():
    """检查数据库初始化状态"""
    db = _get_db()
    try:
        count = db.get_meal_count()
    finally:
        db.close()
    return {
        "initialized": count > 0,
        "meal_count": count,
        "has_demo_data": count > 0,
    }


# ----------------------------------------------------------------------
# 12. 初始化 / 重置
# ----------------------------------------------------------------------


@app.post("/api/init")
async def init_database(reset: bool = Body(False, embed=True)):
    """初始化数据库，可选重置

    - reset=False：若已有数据则跳过，否则插入示例数据
    - reset=True：清空所有数据，重新插入示例数据
    """
    db = _get_db()
    try:
        existing = db.get_meal_count()

        if reset:
            db.conn.execute("DELETE FROM meals")
            # 重置自增 id，避免重置后 id 继续递增
            db.conn.execute("DELETE FROM sqlite_sequence WHERE name='meals'")
            db.conn.commit()
            existing = 0

        if existing > 0:
            return {"success": True, "meal_count": existing}

        # 插入示例数据
        meals = generate_sample_meals()
        for meal in meals:
            db.insert_meal(meal)

        final_count = db.get_meal_count()
    finally:
        db.close()

    return {"success": True, "meal_count": final_count}


# ----------------------------------------------------------------------
# 13. AI 配置：获取 / 保存 / 测试 / 提供商列表
# ----------------------------------------------------------------------

# 有效的 AI 提供商
_VALID_PROVIDERS = {"openai", "anthropic", "aliyun", "openrouter", "custom"}


@app.get("/api/settings")
async def get_settings():
    """获取 AI API 配置

    出于安全考虑，API Key 仅返回掩码（前 4 位 + 后 4 位）。
    """
    from foodlog.config_store import get_config, is_configured, mask_api_key

    config = get_config()
    masked_key = mask_api_key(config["ai_api_key"])
    return {
        "provider": config["ai_api_provider"],
        "api_key_masked": masked_key,
        "api_key_set": bool(config["ai_api_key"]),
        "base_url": config["ai_api_base_url"],
        "model": config["ai_model"],
        "is_configured": is_configured(),
    }


@app.post("/api/settings")
async def save_settings(settings: dict = Body(...)):
    """保存 AI API 配置

    - provider 必须是有效值之一
    - api_key 若为空字符串或包含 ``*``（掩码格式），保留原有 key
    """
    from foodlog.config_store import get_config, save_config

    provider = (settings.get("provider") or "").strip().lower()
    if provider and provider not in _VALID_PROVIDERS:
        return _error_response(
            f"不支持的提供商: {provider}，可选: openrouter/openai/anthropic/aliyun/custom",
            "validation",
        )

    api_key = settings.get("api_key") or ""
    base_url = settings.get("base_url") or ""
    model = settings.get("model") or ""

    # 如果 api_key 为空或为掩码格式（包含 *），保留原有 key
    existing = get_config()
    if not api_key or "*" in api_key:
        api_key = existing["ai_api_key"]

    config = {
        "ai_api_provider": provider,
        "ai_api_key": api_key,
        "ai_api_base_url": base_url,
        "ai_model": model,
    }
    ok = save_config(config)
    if not ok:
        return _error_response("保存配置文件失败", "io")
    return {"success": True}


@app.post("/api/settings/test")
async def test_settings():
    """测试当前 AI 配置是否可用

    使用当前已保存的配置，构造一张 1x1 测试图片调用 AIRecognizer，
    返回 ``{"success": bool, "message": str}``。
    """
    import tempfile

    from foodlog.ai_recognizer import AIConfig, AIRecognizer
    from foodlog.config_store import get_config

    cfg = get_config()
    if not cfg["ai_api_provider"] or not cfg["ai_api_key"]:
        return {
            "success": False,
            "message": "未配置 AI API，请先在设置页面填写提供商和 API Key",
        }

    config = AIConfig(
        provider=cfg["ai_api_provider"],
        api_key=cfg["ai_api_key"],
        base_url=cfg["ai_api_base_url"],
        model=cfg["ai_model"],
    )
    err = config.validate()
    if err:
        return {"success": False, "message": err}

    # 构造一张 1x1 测试图片
    try:
        from PIL import Image

        img = Image.new("RGB", (8, 8), color="white")
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                img.save(f, format="PNG")
                tmp_path = f.name
            recognizer = AIRecognizer(config)
            result = recognizer.recognize(tmp_path)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        if result.get("success"):
            return {
                "success": True,
                "message": "AI 配置测试成功！可以正常使用截图识别功能",
            }
        return {
            "success": False,
            "message": result.get("error", "AI 测试失败，请检查配置"),
        }
    except Exception as e:  # noqa: BLE001 - 兜底
        return {"success": False, "message": f"测试过程出错: {e}"}


@app.get("/api/providers")
async def get_providers():
    """获取支持的 AI API 提供商列表（含默认 base_url 与模型列表）"""
    return {
        "providers": [
            {
                "value": "openrouter",
                "label": "OpenRouter（推荐，支持多种模型）",
                "default_model": "",
                "default_base_url": "https://openrouter.ai/api/v1",
                "models": [
                    "x-ai/grok-vision-76b",
                    "google/gemini-2.0-flash-exp:free",
                    "meta-llama/llama-3.2-90b-vision-instruct",
                    "qwen/qwen-2-vl-72b-instruct",
                ],
            },
            {
                "value": "openai",
                "label": "OpenAI",
                "default_model": "gpt-4o",
                "default_base_url": "https://api.openai.com/v1",
                "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-vision-preview"],
            },
            {
                "value": "anthropic",
                "label": "Anthropic (Claude)",
                "default_model": "claude-sonnet-4-20250514",
                "default_base_url": "https://api.anthropic.com/v1",
                "models": [
                    "claude-sonnet-4-20250514",
                    "claude-3-5-haiku-20241022",
                ],
            },
            {
                "value": "aliyun",
                "label": "阿里云百炼 (通义千问)",
                "default_model": "qwen-vl-max",
                "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "models": ["qwen-vl-max", "qwen-vl-plus"],
            },
            {
                "value": "custom",
                "label": "自定义 (OpenAI兼容接口)",
                "default_model": "",
                "default_base_url": "",
                "models": [],
            },
        ]
    }

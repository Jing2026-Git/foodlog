"""AI截图识别模块

支持多种 AI API 提供商（openai / anthropic / aliyun / openrouter / custom），
统一通过 :func:`recognize_screenshot` 识别食物截图并返回结构化结果。

设计要点：
- 配置优先从 :mod:`foodlog.config_store`（JSON 文件）读取，环境变量作为 fallback；
  未配置时不立即报错，延迟到调用时报错。
- 图片预处理：超过 1920x1080 等比缩小；PNG 透明通道合成白底；统一转 JPEG q85。
- 错误分类：timeout / auth / parse / network / unknown，友好提示中文文案。
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
from typing import Optional

import httpx
from PIL import Image

try:
    # 可选依赖：python-dotenv 已在 pyproject 中声明
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv 缺失时退化为仅读环境变量
    load_dotenv = None


# ----------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------

# 各 provider 的默认模型
DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "aliyun": "qwen-vl-max",
    "openrouter": "x-ai/grok-vision-76b",  # 用户可自选任意模型
    "custom": "",  # custom 必须由用户指定
}

# 各 provider 的默认 base_url
DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "aliyun": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "custom": "",
}

# 兼容 OpenAI 接口的 provider（base_url 已包含 /v1 时不重复拼接）
OPENAI_COMPATIBLE_PROVIDERS = {"openai", "aliyun", "openrouter", "custom"}

# 识别 prompt
RECOGNIZE_PROMPT = """你是一个饮食记录助手。请分析这张图片（可能是外卖订单截图、食物照片等），识别以下信息。这些字段是用户自定义的分类标签，请尽量匹配已有标签值，也可以根据图片内容给出更精确的标签：

1. food_name: 食物名称（如"黄焖鸡米饭"、"拿铁咖啡"）
2. food_category: 食物类别（主食/肉类/蔬菜/饮品/水果/其他）
3. staple_food: 主食类型（优先匹配：米饭/包子饺子/粗粮低GI/汤面汤粉/汉堡披萨。如果没有则null）
4. meat_type: 蛋白来源（优先匹配：鱼虾/猪肉/鸡鸭/牛羊/奶类/蛋or植物，可多选用逗号分隔。如果没有则null）
5. vegetable_type: 蔬菜类型（优先匹配：叶子菜/菌菇/瓜果茄/根茎类/豆类，可多选用逗号分隔。如果没有则null）
6. taste: 口味（优先匹配：清淡/重口/油/辣/甜/咸。如果没有则null）
7. calories: 估算热量(kcal)（整数）
8. protein: 蛋白质(g)（估算，保留1位小数）
9. carbs: 碳水(g)（估算，保留1位小数）
10. fat: 脂肪(g)（估算，保留1位小数）
11. price: 价格(元)（从截图中提取，如果没有则null）
12. source: 来源类型（takeout外卖/home自炊/restaurant下馆子，根据截图特征判断）
13. meal_type: 餐次（breakfast/lunch/dinner/snack，根据截图中的时间或食物类型推断）
14. tags: 标签（逗号分隔，如"咖啡,奶茶,大餐"）
15. notes: 备注（任何值得记录的信息）

注意：
- 截图中的饮品（奶茶/咖啡/果汁等），food_category 设为"饮品"，同时在 tags 中标记"奶茶"/"咖啡"/"果汁"
- 奶类饮品（牛奶、奶茶等），meat_type 中标记"奶类"
- 鸡蛋/鸭蛋等，meat_type 中用"蛋or植物"
- 如果一顿饭里既有主食又有菜，请把主食归到 staple_food，蛋白质归到 meat_type，蔬菜归到 vegetable_type

请只返回JSON格式，不要包含其他文字：
{"food_name": "...", "food_category": "...", "staple_food": "...", "meat_type": "...", "vegetable_type": "...", "taste": "...", "calories": 000, ...}
"""

# 图片预处理参数
_MAX_WIDTH = 1920
_MAX_HEIGHT = 1080
_JPEG_QUALITY = 85
_REQUEST_TIMEOUT = 30.0  # 秒


# ----------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------


class AIConfig:
    """AI API 配置

    通过 :meth:`from_config_store` 从配置文件+环境变量加载（推荐，
    Web 端修改的配置由此读取），或 :meth:`from_env` 仅从环境变量加载，
    也支持直接构造用于测试。
    """

    def __init__(
        self,
        provider: str = "openai",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.provider = (provider or "openai").strip().lower()
        self.api_key = api_key.strip() if api_key else ""
        # base_url 未提供时按 provider 取默认值
        if base_url and base_url.strip():
            self.base_url = base_url.strip().rstrip("/")
        else:
            self.base_url = DEFAULT_BASE_URLS.get(self.provider, "")
        # model 未提供时按 provider 取默认值
        if model and model.strip():
            self.model = model.strip()
        else:
            self.model = DEFAULT_MODELS.get(self.provider, "")

    @classmethod
    def from_config_store(cls) -> "AIConfig":
        """从 config_store 读取配置（配置文件优先，环境变量作为 fallback）

        Web 端修改的配置保存在 ``data/ai_config.json``，由
        :mod:`foodlog.config_store` 统一管理。
        """
        # 延迟导入以避免循环依赖
        from foodlog.config_store import get_config

        cfg = get_config()
        return cls(
            provider=cfg["ai_api_provider"],
            api_key=cfg["ai_api_key"],
            base_url=cfg["ai_api_base_url"],
            model=cfg["ai_model"],
        )

    @classmethod
    def from_env(cls) -> "AIConfig":
        """从环境变量读取配置（fallback，不读取配置文件）

        读取项：AI_API_PROVIDER / AI_API_KEY / AI_API_BASE_URL / AI_MODEL
        """
        provider = os.environ.get("AI_API_PROVIDER", "openai")
        api_key = os.environ.get("AI_API_KEY", "")
        base_url = os.environ.get("AI_API_BASE_URL", "")
        model = os.environ.get("AI_MODEL", "")
        return cls(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    def validate(self) -> Optional[str]:
        """校验配置，返回错误描述；返回 None 表示配置可用。"""
        if self.provider not in DEFAULT_MODELS:
            return f"不支持的 AI_API_PROVIDER: {self.provider}"
        if not self.api_key:
            return "未配置 AI_API_KEY，请在设置页面或 .env 中配置"
        if not self.model:
            return (
                "未配置 AI_MODEL，custom provider 需要显式指定模型名称"
            )
        if not self.base_url:
            return (
                "未配置 AI_API_BASE_URL，custom provider 需要显式指定 base_url"
            )
        return None

    def is_configured(self) -> bool:
        """仅判断 provider/api_key/model/base_url 是否齐备（不做合法性校验）"""
        return bool(self.api_key and self.model and self.base_url)


# ----------------------------------------------------------------------
# 识别器
# ----------------------------------------------------------------------


class AIRecognizer:
    """AI 截图识别器

    使用方式：

    >>> recognizer = AIRecognizer()  # 自动从 config_store 加载配置（文件优先，env fallback）
    >>> result = recognizer.recognize("/path/to/food.png")
    """

    def __init__(self, config: Optional[AIConfig] = None):
        # 未传 config 时从 config_store 加载（配置文件优先，环境变量作为 fallback）；
        # 配置未填写时不报错，延迟到调用 recognize 时报错
        self.config = (
            config if config is not None else AIConfig.from_config_store()
        )

    # ---- 对外主入口 ----
    def recognize(self, image_path: str) -> dict:
        """识别截图，返回结构化结果"""
        # 1. 检查配置
        err = self.config.validate()
        if err:
            return {
                "success": False,
                "error": err,
                "error_type": "auth" if "AI_API_KEY" in err else "unknown",
            }

        # 2. 检查文件
        if not os.path.exists(image_path):
            return {
                "success": False,
                "error": "图片文件不存在",
                "error_type": "unknown",
            }
        if not os.path.isfile(image_path):
            return {
                "success": False,
                "error": "图片文件不存在",
                "error_type": "unknown",
            }

        # 3. 图片预处理
        try:
            image_b64 = self._process_image(image_path)
        except FileNotFoundError:
            return {
                "success": False,
                "error": "图片文件不存在",
                "error_type": "unknown",
            }
        except (Image.UnidentifiedImageError, OSError, ValueError) as e:
            return {
                "success": False,
                "error": "不支持的图片格式",
                "error_type": "unknown",
            }
        except Exception:  # pragma: no cover - 兜底
            return {
                "success": False,
                "error": "不支持的图片格式",
                "error_type": "unknown",
            }

        # 4. 调用 API
        try:
            if self.config.provider == "anthropic":
                raw_text = self._call_anthropic(image_b64, RECOGNIZE_PROMPT)
            else:
                # openai / aliyun / openrouter / custom 都走 OpenAI 兼容接口
                raw_text = self._call_openai(image_b64, RECOGNIZE_PROMPT)
        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "AI识别超时，请重试",
                "error_type": "timeout",
            }
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (401, 403):
                return {
                    "success": False,
                    "error": "API密钥无效或权限不足，请检查.env配置",
                    "error_type": "auth",
                }
            return {
                "success": False,
                "error": f"AI服务返回错误: {status}",
                "error_type": "network",
            }
        except (httpx.ConnectError, httpx.NetworkError, httpx.ConnectTimeout):
            return {
                "success": False,
                "error": "网络连接失败，请检查网络",
                "error_type": "network",
            }
        except httpx.HTTPError:
            return {
                "success": False,
                "error": "网络连接失败，请检查网络",
                "error_type": "network",
            }
        except Exception:  # pragma: no cover - 兜底
            return {
                "success": False,
                "error": "AI识别失败，请稍后重试",
                "error_type": "unknown",
            }

        # 5. 解析返回
        parsed = self._parse_response(raw_text)
        if parsed is None:
            return {
                "success": False,
                "error": "AI返回格式异常",
                "error_type": "parse",
                "raw_response": raw_text,
            }

        return {
            "success": True,
            "data": parsed,
            "raw_response": raw_text,
        }

    # ---- 图片预处理 ----
    def _process_image(self, image_path: str) -> str:
        """打开图片并预处理，返回 base64 编码的 JPEG 字符串

        - 超过 1920x1080 时等比缩小
        - PNG 透明通道合成白色背景
        - 转 JPEG q85 并 base64
        """
        with Image.open(image_path) as img:
            img = img.convert("RGBA") if img.mode in ("RGBA", "LA") else img
            # 透明通道合成白底
            if img.mode == "RGBA":
                background = Image.new("RGBA", img.size, (255, 255, 255, 255))
                background.alpha_composite(img)
                img = background.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # 等比缩小
            w, h = img.size
            if w > _MAX_WIDTH or h > _MAX_HEIGHT:
                ratio = min(_MAX_WIDTH / w, _MAX_HEIGHT / h)
                new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
                img = img.resize(new_size, Image.LANCZOS)

            # 编码为 JPEG
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
            data = buffer.getvalue()

        return base64.b64encode(data).decode("ascii")

    # ---- OpenAI 兼容接口 ----
    def _call_openai(self, image_b64: str, prompt: str) -> str:
        """调用 OpenAI 兼容接口（openai / aliyun / openrouter / custom）

        OpenRouter 使用与 OpenAI 一致的 ``/chat/completions`` 接口与
        ``Authorization: Bearer <key>`` 鉴权，可直接复用本方法。
        """
        base_url = self.config.base_url
        # 兼容用户填了不同形式的 base_url：
        # - https://api.openai.com            -> /v1/chat/completions
        # - https://api.openai.com/v1         -> /chat/completions
        # - https://.../compatible-mode/v1    -> /chat/completions
        if base_url.endswith("/v1"):
            url = f"{base_url}/chat/completions"
        else:
            url = f"{base_url}/v1/chat/completions"

        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 1024,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        # 兼容 OpenAI 响应结构
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ValueError("OpenAI 兼容接口返回结构异常")

    # ---- Anthropic 接口 ----
    def _call_anthropic(self, image_b64: str, prompt: str) -> str:
        """调用 Anthropic Messages API"""
        base_url = self.config.base_url
        if base_url.endswith("/v1"):
            url = f"{base_url}/messages"
        else:
            url = f"{base_url}/v1/messages"

        payload = {
            "model": self.config.model,
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        try:
            # content 是一个 list，每项有 type/text
            blocks = data.get("content", [])
            texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
            return "".join(texts)
        except (AttributeError, TypeError):
            raise ValueError("Anthropic 接口返回结构异常")

    # ---- 解析 ----
    def _parse_response(self, response_text: str) -> Optional[dict]:
        """解析 AI 返回的 JSON，失败返回 None

        兼容三种情况：
        1. 直接是 JSON
        2. 包裹在 ```json ... ``` 代码块中
        3. 文本中夹杂一段 JSON（取第一个平衡的 {...}）
        """
        if not response_text:
            return None

        text = response_text.strip()

        # 1. 直接尝试
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return self._normalize(obj)
        except json.JSONDecodeError:
            pass

        # 2. markdown 代码块
        code_block_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE
        )
        if code_block_match:
            try:
                obj = json.loads(code_block_match.group(1))
                if isinstance(obj, dict):
                    return self._normalize(obj)
            except json.JSONDecodeError:
                pass

        # 3. 取首个 {...} 片段（非贪婪到第一个右大括号，逐步放宽）
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            candidate = brace_match.group(0)
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return self._normalize(obj)
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _normalize(obj: dict) -> dict:
        """将 AI 返回的字段规范化为统一 schema"""
        def to_float(v):
            if v is None or v == "":
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def to_int(v):
            if v is None or v == "":
                return None
            try:
                return int(v)
            except (TypeError, ValueError):
                try:
                    return int(float(v))
                except (TypeError, ValueError):
                    return None

        return {
            "food_name": str(obj.get("food_name", "")).strip() or "",
            "food_category": str(obj.get("food_category", "")).strip() or "",
            "calories": to_int(obj.get("calories")),
            "protein": to_float(obj.get("protein")),
            "carbs": to_float(obj.get("carbs")),
            "fat": to_float(obj.get("fat")),
            "price": to_float(obj.get("price")),
            "source": str(obj.get("source", "")).strip() or "",
            "meal_type": str(obj.get("meal_type", "")).strip() or "",
            "tags": str(obj.get("tags", "")).strip() or "",
            "notes": str(obj.get("notes", "")).strip() or "",
        }


# ----------------------------------------------------------------------
# 便捷函数
# ----------------------------------------------------------------------


def recognize_screenshot(image_path: str) -> dict:
    """便捷函数：识别截图，等价于 ``AIRecognizer().recognize(image_path)``"""
    recognizer = AIRecognizer()
    return recognizer.recognize(image_path)

"""AI 识别模块测试

覆盖：
- AIConfig.from_env 配置加载
- AIRecognizer._process_image 图片预处理
- AIRecognizer._parse_response JSON 解析（含 markdown 代码块）
- AIRecognizer.recognize 在未配置 / 文件不存在 / 文件不可识别等错误场景下的行为

所有外部 API 调用均通过 unittest.mock 模拟，不发起真实网络请求。
"""

from __future__ import annotations

import base64
import io
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from PIL import Image

from foodlog.ai_recognizer import (
    AIConfig,
    AIRecognizer,
    DEFAULT_BASE_URLS,
    DEFAULT_MODELS,
    recognize_screenshot,
)


# ----------------------------------------------------------------------
# 公共工具
# ----------------------------------------------------------------------


def _make_image(path, size=(100, 100), color="red", mode="RGB"):
    """创建一张测试图片并保存到 path"""
    img = Image.new(mode, size, color=color)
    img.save(path)
    img.close()


def _ok_config(provider="openai", **overrides):
    """构造一个通过 validate 的 AIConfig"""
    defaults = dict(
        provider=provider,
        api_key="sk-test-key",
        base_url="https://api.example.com",
        model="test-model",
    )
    defaults.update(overrides)
    return AIConfig(**defaults)


# ----------------------------------------------------------------------
# AIConfig
# ----------------------------------------------------------------------


def test_ai_config_from_env(monkeypatch):
    """测试从环境变量加载配置"""
    monkeypatch.setenv("AI_API_PROVIDER", "anthropic")
    monkeypatch.setenv("AI_API_KEY", "sk-ant-test")
    monkeypatch.setenv("AI_API_BASE_URL", "https://api.anthropic.com")
    monkeypatch.setenv("AI_MODEL", "claude-test-model")

    config = AIConfig.from_env()
    assert config.provider == "anthropic"
    assert config.api_key == "sk-ant-test"
    assert config.base_url == "https://api.anthropic.com"
    assert config.model == "claude-test-model"
    assert config.validate() is None


def test_ai_config_defaults(monkeypatch):
    """测试默认模型与 base_url"""
    # 清空相关环境变量
    for k in ("AI_API_PROVIDER", "AI_API_KEY", "AI_API_BASE_URL", "AI_MODEL"):
        monkeypatch.delenv(k, raising=False)

    config = AIConfig.from_env()
    assert config.provider == "openai"
    # 默认模型
    assert config.model == DEFAULT_MODELS["openai"]
    # 默认 base_url
    assert config.base_url == DEFAULT_BASE_URLS["openai"]
    # api_key 为空 -> 校验失败
    assert config.validate() is not None


def test_ai_config_provider_defaults():
    """测试各 provider 的默认值"""
    # aliyun
    cfg = AIConfig(provider="aliyun", api_key="k")
    assert cfg.base_url == DEFAULT_BASE_URLS["aliyun"]
    assert cfg.model == DEFAULT_MODELS["aliyun"]
    assert cfg.validate() is None

    # anthropic
    cfg = AIConfig(provider="anthropic", api_key="k")
    assert cfg.model == DEFAULT_MODELS["anthropic"]
    assert cfg.validate() is None

    # custom 必须指定 model 和 base_url
    cfg = AIConfig(provider="custom", api_key="k")
    assert cfg.model == ""
    assert cfg.base_url == ""
    assert cfg.validate() is not None

    cfg = AIConfig(
        provider="custom", api_key="k", model="m", base_url="https://x.example.com"
    )
    assert cfg.validate() is None


def test_ai_config_invalid_provider():
    """测试不支持的 provider"""
    cfg = AIConfig(provider="unknown", api_key="k")
    err = cfg.validate()
    assert err is not None
    assert "unknown" in err


# ----------------------------------------------------------------------
# _process_image
# ----------------------------------------------------------------------


def test_process_image_jpeg(tmp_path):
    """测试 JPEG 图片预处理"""
    img_path = tmp_path / "test.jpg"
    _make_image(img_path, size=(200, 150), color="blue")

    recognizer = AIRecognizer(_ok_config())
    b64_str = recognizer._process_image(str(img_path))

    # 返回值是字符串
    assert isinstance(b64_str, str)
    # 能解码回 bytes
    raw = base64.b64decode(b64_str)
    assert len(raw) > 0

    # 解码后应是 JPEG 图片
    img = Image.open(io.BytesIO(raw))
    assert img.format == "JPEG"
    img.close()


def test_process_image_png_with_alpha(tmp_path):
    """测试 PNG 透明通道合成白底"""
    img_path = tmp_path / "test.png"
    _make_image(img_path, size=(120, 120), color=(255, 0, 0, 128), mode="RGBA")

    recognizer = AIRecognizer(_ok_config())
    b64_str = recognizer._process_image(str(img_path))
    raw = base64.b64decode(b64_str)

    # 应转成 RGB JPEG
    img = Image.open(io.BytesIO(raw))
    assert img.format == "JPEG"
    assert img.mode == "RGB"
    img.close()


def test_process_image_downscale(tmp_path):
    """测试超过 1920x1080 时等比缩小"""
    img_path = tmp_path / "big.png"
    _make_image(img_path, size=(3000, 2000), color="green")

    recognizer = AIRecognizer(_ok_config())
    b64_str = recognizer._process_image(str(img_path))
    raw = base64.b64decode(b64_str)
    img = Image.open(io.BytesIO(raw))
    # 缩小后不应超过 1920x1080
    assert img.size[0] <= 1920
    assert img.size[1] <= 1080
    # 应该确实被缩小了
    assert img.size[0] < 3000
    assert img.size[1] < 2000
    img.close()


# ----------------------------------------------------------------------
# _parse_response
# ----------------------------------------------------------------------


def test_parse_response_success():
    """测试标准 JSON 返回的解析"""
    payload = {
        "food_name": "黄焖鸡米饭",
        "food_category": "主食",
        "calories": 650,
        "protein": 35.0,
        "carbs": 80.0,
        "fat": 15.0,
        "price": 25.0,
        "source": "takeout",
        "meal_type": "lunch",
        "tags": "外卖,大餐",
        "notes": "微辣",
    }
    recognizer = AIRecognizer(_ok_config())
    result = recognizer._parse_response(json.dumps(payload, ensure_ascii=False))

    assert result is not None
    assert result["food_name"] == "黄焖鸡米饭"
    assert result["food_category"] == "主食"
    assert result["calories"] == 650
    assert result["protein"] == 35.0
    assert result["carbs"] == 80.0
    assert result["fat"] == 15.0
    assert result["price"] == 25.0
    assert result["source"] == "takeout"
    assert result["meal_type"] == "lunch"
    assert result["tags"] == "外卖,大餐"
    assert result["notes"] == "微辣"


def test_parse_response_with_markdown():
    """测试从 markdown 代码块中提取 JSON"""
    raw = """好的，这是分析结果：

```json
{
    "food_name": "拿铁咖啡",
    "food_category": "饮品",
    "calories": 180,
    "protein": 4.0,
    "carbs": 24.0,
    "fat": 8.0,
    "price": 28.0,
    "source": "takeout",
    "meal_type": "breakfast",
    "tags": "咖啡",
    "notes": ""
}
```

希望对你有帮助！
"""
    recognizer = AIRecognizer(_ok_config())
    result = recognizer._parse_response(raw)
    assert result is not None
    assert result["food_name"] == "拿铁咖啡"
    assert result["food_category"] == "饮品"
    assert result["calories"] == 180
    assert result["price"] == 28.0


def test_parse_response_with_text_wrapping():
    """测试 JSON 被自然语言包裹"""
    raw = '识别完成：{"food_name": "苹果", "food_category": "水果", "calories": 80, "protein": 0.5, "carbs": 20.0, "fat": 0.3, "price": null, "source": "home", "meal_type": "snack", "tags": "水果", "notes": ""} 以上。'
    recognizer = AIRecognizer(_ok_config())
    result = recognizer._parse_response(raw)
    assert result is not None
    assert result["food_name"] == "苹果"
    assert result["price"] is None


def test_parse_response_failure():
    """测试非 JSON 返回"""
    recognizer = AIRecognizer(_ok_config())
    assert recognizer._parse_response("这不是 JSON") is None
    assert recognizer._parse_response("") is None
    assert recognizer._parse_response("```plain\ntext\n```") is None
    assert recognizer._parse_response("{invalid json}") is None


def test_parse_response_null_values():
    """测试 null/缺失字段的规范化"""
    raw = '{"food_name": "水", "price": null}'
    recognizer = AIRecognizer(_ok_config())
    result = recognizer._parse_response(raw)
    assert result is not None
    assert result["food_name"] == "水"
    assert result["price"] is None
    # 缺失字段应为空字符串或 None
    assert result["food_category"] == ""
    assert result["calories"] is None
    assert result["protein"] is None


# ----------------------------------------------------------------------
# recognize 错误场景
# ----------------------------------------------------------------------


def test_recognize_no_config(monkeypatch):
    """测试未配置 API 时的错误"""
    for k in ("AI_API_PROVIDER", "AI_API_KEY", "AI_API_BASE_URL", "AI_MODEL"):
        monkeypatch.delenv(k, raising=False)

    recognizer = AIRecognizer()
    result = recognizer.recognize("/tmp/whatever.png")

    assert result["success"] is False
    assert "AI_API_KEY" in result["error"]
    assert result["error_type"] == "auth"


def test_recognize_file_not_found(tmp_path):
    """测试文件不存在"""
    recognizer = AIRecognizer(_ok_config())
    result = recognizer.recognize(str(tmp_path / "nonexistent.png"))

    assert result["success"] is False
    assert result["error"] == "图片文件不存在"
    assert result["error_type"] == "unknown"


def test_recognize_unsupported_format(tmp_path):
    """测试不支持的图片格式"""
    bad = tmp_path / "not_an_image.txt"
    bad.write_text("hello, not an image")

    recognizer = AIRecognizer(_ok_config())
    result = recognizer.recognize(str(bad))

    assert result["success"] is False
    assert result["error"] == "不支持的图片格式"
    assert result["error_type"] == "unknown"


# ----------------------------------------------------------------------
# recognize 成功路径（mock API）
# ----------------------------------------------------------------------


def _mock_openai_response(text: str) -> httpx.Response:
    """构造一个 OpenAI 风格的成功响应"""
    payload = {
        "choices": [
            {"message": {"role": "assistant", "content": text}}
        ]
    }
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    return httpx.Response(
        status_code=200,
        json=payload,
        request=request,
    )


def test_recognize_openai_success(tmp_path):
    """测试 OpenAI provider 成功识别（mock）"""
    img_path = tmp_path / "food.png"
    _make_image(img_path, size=(80, 80), color="orange")

    ai_response = json.dumps(
        {
            "food_name": "黄焖鸡米饭",
            "food_category": "主食",
            "calories": 650,
            "protein": 35.0,
            "carbs": 80.0,
            "fat": 15.0,
            "price": 25.0,
            "source": "takeout",
            "meal_type": "lunch",
            "tags": "",
            "notes": "",
        },
        ensure_ascii=False,
    )

    config = _ok_config(provider="openai")
    recognizer = AIRecognizer(config)

    with patch.object(recognizer, "_call_openai", return_value=ai_response) as mocked:
        result = recognizer.recognize(str(img_path))

    assert mocked.called
    assert result["success"] is True
    assert result["data"]["food_name"] == "黄焖鸡米饭"
    assert result["data"]["calories"] == 650
    assert result["data"]["price"] == 25.0
    assert result["raw_response"] == ai_response


def test_recognize_anthropic_success(tmp_path):
    """测试 Anthropic provider 走 _call_anthropic 分支"""
    img_path = tmp_path / "food.png"
    _make_image(img_path, size=(80, 80), color="orange")

    ai_response = json.dumps(
        {"food_name": "拿铁", "food_category": "饮品", "calories": 180},
        ensure_ascii=False,
    )

    config = _ok_config(provider="anthropic")
    recognizer = AIRecognizer(config)

    with patch.object(
        recognizer, "_call_anthropic", return_value=ai_response
    ) as mocked_anthropic, patch.object(
        recognizer, "_call_openai", return_value=""
    ) as mocked_openai:
        result = recognizer.recognize(str(img_path))

    assert mocked_anthropic.called
    assert not mocked_openai.called
    assert result["success"] is True
    assert result["data"]["food_name"] == "拿铁"


def test_recognize_aliyun_uses_openai_endpoint(tmp_path):
    """测试 aliyun provider 走 OpenAI 兼容接口"""
    img_path = tmp_path / "food.png"
    _make_image(img_path)

    config = _ok_config(provider="aliyun")
    recognizer = AIRecognizer(config)

    with patch.object(
        recognizer, "_call_openai", return_value='{"food_name":"米饭"}'
    ) as mocked_openai, patch.object(
        recognizer, "_call_anthropic", return_value=""
    ) as mocked_anthropic:
        result = recognizer.recognize(str(img_path))

    assert mocked_openai.called
    assert not mocked_anthropic.called
    assert result["success"] is True


# ----------------------------------------------------------------------
# recognize 错误路径（mock API 异常）
# ----------------------------------------------------------------------


def test_recognize_timeout(tmp_path):
    """测试请求超时"""
    img_path = tmp_path / "food.png"
    _make_image(img_path)

    recognizer = AIRecognizer(_ok_config())

    with patch.object(
        recognizer,
        "_call_openai",
        side_effect=httpx.TimeoutException("timeout"),
    ):
        result = recognizer.recognize(str(img_path))

    assert result["success"] is False
    assert result["error"] == "AI识别超时，请重试"
    assert result["error_type"] == "timeout"


def test_recognize_auth_error(tmp_path):
    """测试 401/403 鉴权失败"""
    img_path = tmp_path / "food.png"
    _make_image(img_path)

    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(status_code=401, request=request)
    exc = httpx.HTTPStatusError("401", request=request, response=response)

    recognizer = AIRecognizer(_ok_config())

    with patch.object(recognizer, "_call_openai", side_effect=exc):
        result = recognizer.recognize(str(img_path))

    assert result["success"] is False
    assert result["error"] == "API密钥无效或权限不足，请检查.env配置"
    assert result["error_type"] == "auth"


def test_recognize_network_error(tmp_path):
    """测试网络错误"""
    img_path = tmp_path / "food.png"
    _make_image(img_path)

    recognizer = AIRecognizer(_ok_config())

    with patch.object(
        recognizer, "_call_openai", side_effect=httpx.ConnectError("no network")
    ):
        result = recognizer.recognize(str(img_path))

    assert result["success"] is False
    assert result["error"] == "网络连接失败，请检查网络"
    assert result["error_type"] == "network"


def test_recognize_parse_failure(tmp_path):
    """测试 AI 返回非 JSON"""
    img_path = tmp_path / "food.png"
    _make_image(img_path)

    recognizer = AIRecognizer(_ok_config())

    with patch.object(recognizer, "_call_openai", return_value="这不是JSON"):
        result = recognizer.recognize(str(img_path))

    assert result["success"] is False
    assert result["error"] == "AI返回格式异常"
    assert result["error_type"] == "parse"
    assert result["raw_response"] == "这不是JSON"


# ----------------------------------------------------------------------
# _call_openai / _call_anthropic 单元测试（mock httpx.Client）
# ----------------------------------------------------------------------


def test_call_openai_request_structure():
    """测试 _call_openai 构造的请求结构正确"""
    config = _ok_config(provider="openai")
    recognizer = AIRecognizer(config)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "hello"}}]
    }
    mock_response.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = mock_response

    with patch("foodlog.ai_recognizer.httpx.Client", return_value=mock_client):
        text = recognizer._call_openai("base64data", "prompt")

    assert text == "hello"
    # 验证请求参数
    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    url = args[0] if args else kwargs.get("url")
    assert url.endswith("/v1/chat/completions")
    payload = kwargs.get("json", {})
    assert payload["model"] == "test-model"
    assert payload["messages"][0]["role"] == "user"
    content = payload["messages"][0]["content"]
    # 应包含 text 和 image_url 两部分
    assert any(c["type"] == "text" for c in content)
    assert any(c["type"] == "image_url" for c in content)
    # headers 应包含 Authorization
    headers = kwargs.get("headers", {})
    assert headers["Authorization"] == "Bearer sk-test-key"


def test_call_openai_url_with_v1_suffix():
    """测试 base_url 已带 /v1 时不重复拼接"""
    config = _ok_config(provider="openai", base_url="https://api.example.com/v1")
    recognizer = AIRecognizer(config)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "ok"}}]
    }
    mock_response.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = mock_response

    with patch("foodlog.ai_recognizer.httpx.Client", return_value=mock_client):
        recognizer._call_openai("base64data", "prompt")

    args, kwargs = mock_client.post.call_args
    url = args[0] if args else kwargs.get("url")
    # 不应出现 /v1/v1
    assert "/v1/v1" not in url
    assert url == "https://api.example.com/v1/chat/completions"


def test_call_anthropic_request_structure():
    """测试 _call_anthropic 构造的请求结构正确"""
    config = _ok_config(provider="anthropic")
    recognizer = AIRecognizer(config)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": [
            {"type": "text", "text": "hello from claude"},
            {"type": "text", "text": " more"},
        ]
    }
    mock_response.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = mock_response

    with patch("foodlog.ai_recognizer.httpx.Client", return_value=mock_client):
        text = recognizer._call_anthropic("base64data", "prompt")

    assert text == "hello from claude more"
    args, kwargs = mock_client.post.call_args
    url = args[0] if args else kwargs.get("url")
    assert url.endswith("/v1/messages")
    headers = kwargs.get("headers", {})
    assert headers["x-api-key"] == "sk-test-key"
    assert headers["anthropic-version"] == "2023-06-01"
    payload = kwargs.get("json", {})
    # content 中应包含 image 与 text 两类
    content = payload["messages"][0]["content"]
    assert any(c["type"] == "image" for c in content)
    assert any(c["type"] == "text" for c in content)


# ----------------------------------------------------------------------
# 便捷函数
# ----------------------------------------------------------------------


def test_recognize_screenshot_function_uses_recognizer(tmp_path, monkeypatch):
    """测试 recognize_screenshot 便捷函数"""
    img_path = tmp_path / "food.png"
    _make_image(img_path)

    # 通过环境变量提供配置
    monkeypatch.setenv("AI_API_PROVIDER", "openai")
    monkeypatch.setenv("AI_API_KEY", "sk-test")
    monkeypatch.setenv("AI_API_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("AI_MODEL", "gpt-4o")

    ai_response = '{"food_name":"米饭"}'

    with patch.object(AIRecognizer, "_call_openai", return_value=ai_response):
        result = recognize_screenshot(str(img_path))

    assert result["success"] is True
    assert result["data"]["food_name"] == "米饭"

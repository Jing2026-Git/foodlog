"""配置存储 - 管理 AI API 配置

支持从 JSON 配置文件读取 AI API 配置，使 Web 端可以动态修改。
环境变量作为 fallback：当配置文件不存在或字段为空时，从环境变量补充。

配置文件路径默认为 ``data/ai_config.json``（相对当前工作目录），
字段：ai_api_provider / ai_api_key / ai_api_base_url / ai_model。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict

# 配置文件路径（相对当前工作目录）
CONFIG_FILE = "data/ai_config.json"

# 默认配置（所有字段为空，表示未配置）
DEFAULT_CONFIG: Dict[str, str] = {
    "ai_api_provider": "",      # openai / anthropic / aliyun / openrouter / custom
    "ai_api_key": "",
    "ai_api_base_url": "",
    "ai_model": "",
}

# 字段到环境变量名的映射
_ENV_KEYS = {
    "ai_api_provider": "AI_API_PROVIDER",
    "ai_api_key": "AI_API_KEY",
    "ai_api_base_url": "AI_API_BASE_URL",
    "ai_model": "AI_MODEL",
}


def get_config() -> Dict[str, str]:
    """获取 AI 配置，优先从配置文件读取，其次从环境变量

    返回包含 ai_api_provider / ai_api_key / ai_api_base_url / ai_model 的 dict。
    任意来源（文件或环境变量）的非空值都会被采用，文件优先于环境变量。
    """
    config = {k: "" for k in DEFAULT_CONFIG}

    # 1. 读取配置文件
    file_config = _read_file()
    if file_config:
        for k in config:
            v = file_config.get(k)
            if v:
                config[k] = v

    # 2. 配置文件未提供的字段，从环境变量补充
    for k, env_key in _ENV_KEYS.items():
        if not config[k]:
            env_val = os.environ.get(env_key, "")
            if env_val:
                config[k] = env_val

    return config


def _read_file() -> Dict[str, str]:
    """读取配置文件，不存在或损坏时返回空 dict"""
    try:
        path = Path(CONFIG_FILE)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        # 只保留已知字段，且值统一转为字符串
        return {k: str(v) for k, v in data.items() if k in DEFAULT_CONFIG and v}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def save_config(config: Dict[str, str]) -> bool:
    """保存 AI 配置到文件

    仅保存已知字段，自动创建父目录。返回是否保存成功。
    """
    try:
        path = Path(CONFIG_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        # 只保留已知字段
        clean = {k: str(config.get(k, "")) for k in DEFAULT_CONFIG}
        with path.open("w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def is_configured() -> bool:
    """检查是否已配置（有 provider 和 api_key）"""
    config = get_config()
    return bool(config["ai_api_provider"] and config["ai_api_key"])


def clear_config() -> bool:
    """清除配置文件"""
    try:
        path = Path(CONFIG_FILE)
        if path.exists():
            path.unlink()
        return True
    except OSError:
        return False


def mask_api_key(key: str) -> str:
    """掩码 API Key，仅显示前 4 位和后 4 位

    短 key 全部掩码；空 key 返回空字符串。
    """
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]

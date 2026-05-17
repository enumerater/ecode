"""模型工厂：从 config.yaml 或环境变量读取配置，创建 LLM 实例。

优先级：config.yaml > 环境变量 (ECODE_API_KEY / ECODE_MODEL / ECODE_BASE_URL)
两者都没有时，raise 引导用户运行 /init。
"""
import os
from dotenv import load_dotenv

_ECODE_DIR = os.path.join(os.getcwd(), ".ecode")
_CONFIG_PATH = os.path.join(_ECODE_DIR, "config.yaml")
load_dotenv(os.path.join(_ECODE_DIR, ".env"))

import yaml
from langchain_openai import ChatOpenAI


def _load_config_yaml() -> dict | None:
    """尝试从 config.yaml 加载 LLM 配置，文件不存在返回 None。"""
    if not os.path.exists(_CONFIG_PATH):
        return None
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not raw:
        return None
    llm_cfg = raw.get("llm", {})
    active = llm_cfg.get("active", "")
    configs = llm_cfg.get("configs", {})
    if not active or active not in configs:
        raise ValueError(
            f"config.yaml: llm.active='{active}' 无效。"
            f" 可选值: {list(configs.keys())}"
        )
    return configs[active]


def _load_from_env() -> dict | None:
    """从环境变量读取配置。"""
    api_key = os.environ.get("ECODE_API_KEY")
    model = os.environ.get("ECODE_MODEL")
    base_url = os.environ.get("ECODE_BASE_URL")
    if not all([api_key, model, base_url]):
        return None
    return {
        "provider": "openai",
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "temperature": 0,
        "streaming": True,
        "stream_usage": True,
    }


def load_llm_config() -> dict:
    """加载 LLM 配置，优先 config.yaml，其次环境变量。"""
    cfg = _load_config_yaml()
    if cfg:
        return cfg
    cfg = _load_from_env()
    if cfg:
        return cfg
    raise ValueError(
        "未找到 LLM 配置。请执行以下操作之一：\n"
        "  1. 运行 /init 命令进行交互式配置\n"
        "  2. 设置环境变量: ECODE_API_KEY, ECODE_MODEL, ECODE_BASE_URL\n"
        "  3. 创建 .ecode/config.yaml（参考 config.yaml.example）"
    )


def create_llm():
    """根据配置创建 LLM 实例。"""
    cfg = load_llm_config()
    provider = cfg.get("provider", "openai")

    if provider == "openai":
        # 支持直接传 api_key（环境变量模式）或 api_key_env（config.yaml 模式）
        api_key = cfg.get("api_key") or os.environ.get(cfg.get("api_key_env", ""), "")
        if not api_key:
            raise ValueError(f"环境变量 {cfg.get('api_key_env', 'ECODE_API_KEY')} 未设置")
        # ChatOpenAI 会自动拼 /chat/completions，如果用户已填完整路径则去掉尾部
        base_url = cfg["base_url"].rstrip("/")
        for suffix in ["/chat/completions", "/chat", "/completions"]:
            if base_url.endswith(suffix):
                base_url = base_url[: -len(suffix)]
                break
        return ChatOpenAI(
            model=cfg["model"],
            api_key=api_key,
            base_url=base_url,
            temperature=cfg.get("temperature", 0),
            streaming=cfg.get("streaming", True),
            stream_usage=cfg.get("stream_usage", False),
        )
    else:
        raise ValueError(f"不支持的 provider: {provider}")


def has_llm_config() -> bool:
    """检查是否有可用的 LLM 配置（不抛异常）。"""
    try:
        load_llm_config()
        return True
    except ValueError:
        return False


# ── 延迟初始化单例 ────────────────────────────────────────────────────────
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = create_llm()
    return _llm


def __getattr__(name):
    if name == "llm":
        return _get_llm()
    raise AttributeError(f"module 'model' has no attribute {name!r}")


if __name__ == "__main__":
    res = _get_llm().invoke("你好")
    print(res)

"""模型工厂：从 config.yaml 读取配置，按 active 字段创建 LLM 实例。

新增模型只需在 config.yaml 的 llm.configs 下添加配置块，
修改 active 字段即可切换，无需改动代码。
"""
from dotenv import load_dotenv  # 新增
load_dotenv()  # 自动读取 .env 文件  新增


import os
import yaml
from langchain_openai import ChatOpenAI

# ── 配置加载 ──────────────────────────────────────────────────────────────

def load_llm_config():
    """从 config.yaml 加载 LLM 配置。"""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    llm_cfg = raw.get("llm", {})
    active = llm_cfg.get("active", "")
    configs = llm_cfg.get("configs", {})
    if not active or active not in configs:
        raise ValueError(
            f"config.yaml: llm.active='{active}' 无效。"
            f" 可选值: {list(configs.keys())}"
        )
    return configs[active]


def create_llm():
    """根据配置创建 LLM 实例。"""
    cfg = load_llm_config()
    provider = cfg.get("provider", "openai")

    if provider == "openai":
        api_key = os.environ.get(cfg["api_key_env"])
        if not api_key:
            raise ValueError(f"环境变量 {cfg['api_key_env']} 未设置")
        return ChatOpenAI(
            model=cfg["model"],
            api_key=api_key,
            base_url=cfg["base_url"],
            temperature=cfg.get("temperature", 0),
            streaming=cfg.get("streaming", True),
            stream_usage=cfg.get("stream_usage", False),
        )
    else:
        raise ValueError(f"不支持的 provider: {provider}")


# ── 单例 ──────────────────────────────────────────────────────────────────
llm = create_llm()

if __name__ == "__main__":
    res = llm.invoke("你好")
    print(res)
import os

from langchain_openai import ChatOpenAI
import dotenv

dotenv.load_dotenv()

ALI = os.environ.get("ALI")
MIMO = os.environ.get("MIMO")

# llm = ChatOpenAI(
#     model="qwen-plus",
#     api_key=ALI,
#     base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
#     temperature=0,
#     streaming=True,  # 必须开！
# )

llm = ChatOpenAI(
    model="mimo-v2.5-pro",
    api_key=MIMO,
    base_url="https://token-plan-cn.xiaomimimo.com/v1",
    streaming=True,
)

if __name__ == "__main__":
    res = llm.invoke("你好")
    print( res)
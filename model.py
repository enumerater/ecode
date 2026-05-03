import os

from langchain_openai import ChatOpenAI
import dotenv

dotenv.load_dotenv()

ALI = os.environ.get("ALI")

llm = ChatOpenAI(
    model="qwen-plus",
    api_key=ALI,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature=0,
    streaming=True,  # 必须开！
)
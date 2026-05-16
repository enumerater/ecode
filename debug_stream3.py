"""Debug: test the exact pending_tools logic from chat.py."""
import sys
import json
import time
sys.stdout.reconfigure(encoding='utf-8')

from agent import build_graph
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AIMessageChunk

graph = build_graph()
import uuid

thread_id = str(uuid.uuid4())
config = {'configurable': {'thread_id': thread_id}}
input_data = {
    'messages': [HumanMessage(content='列出当前目录的文件')],
    'project_root': 'E:\\work\\ecode',
    'permission_mode': 'auto_approve',
    'plan_mode': False,
}

# Exact same logic as chat.py
pending_tools = {}

for chunk in graph.stream(input_data, stream_mode=['messages', 'updates'], config=config, version='v2'):
    if isinstance(chunk, dict):
        typ = chunk.get('type', '')
        data = chunk.get('data')
    elif isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
        typ, data = chunk
    else:
        continue

    if typ == 'messages':
        try:
            msg, metadata = data
            node = metadata.get('langgraph_node', '')

            # AI 消息：注册工具调用
            if isinstance(msg, AIMessage) and getattr(msg, 'tool_calls', None):
                for tc in msg.tool_calls:
                    tc_id = tc.get('id', '')
                    tc_name = tc.get('name', '')
                    tc_args = tc.get('args', {})
                    pending_tools[tc_id] = {
                        'name': tc_name,
                        'args': tc_args,
                        'start_time': time.time(),
                    }
                    print(f'REGISTERED: id={tc_id} name={tc_name}', flush=True)

            # 工具结果
            elif isinstance(msg, ToolMessage):
                tc_id = msg.tool_call_id
                tool_info = pending_tools.pop(tc_id, {})
                tool_name = tool_info.get('name', '') or getattr(msg, 'name', '')
                print(f'TOOL_RESULT: call_id={tc_id} found_in_pending={tc_id in pending_tools or bool(tool_info)} tool_name={tool_name}', flush=True)
                print(f'  pending_tools keys: {list(pending_tools.keys())}', flush=True)

        except Exception as e:
            print(f'ERROR: {e}', flush=True)

    elif typ == 'updates' and isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict) and 'messages' in v:
                for m in v['messages']:
                    if isinstance(m, AIMessage) and getattr(m, 'tool_calls', None):
                        for tc in m.tool_calls:
                            print(f'UPDATE_TC: node={k} name={tc.get("name","")}', flush=True)

print(f'\nFinal pending_tools: {list(pending_tools.keys())}', flush=True)

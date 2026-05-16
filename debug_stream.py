"""Debug script to inspect LangGraph stream output format."""
import sys
import json
sys.stdout.reconfigure(encoding='utf-8')

from agent import build_graph
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

graph = build_graph()

import uuid
thread_id = str(uuid.uuid4())
project_root = 'E:\\work\\ecode'
config = {'configurable': {'thread_id': thread_id}}

input_data = {
    'messages': [HumanMessage(content='列出当前目录的文件')],
    'project_root': project_root,
    'permission_mode': 'auto_approve',
    'plan_mode': False,
}

print('Starting stream...', flush=True)
chunk_count = 0
for chunk in graph.stream(
    input_data,
    stream_mode=['messages', 'updates'],
    config=config,
    version='v2',
):
    chunk_count += 1
    if isinstance(chunk, dict):
        typ = chunk.get('type', '')
        data = chunk.get('data')
    elif isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
        typ, data = chunk
    else:
        print(f'UNKNOWN CHUNK: {type(chunk)}', flush=True)
        continue

    if typ == 'messages':
        try:
            msg, metadata = data
            msg_type = type(msg).__name__
            node = metadata.get('langgraph_node', '')
            has_tc = hasattr(msg, 'tool_calls') and bool(msg.tool_calls)
            print(f'MSG: type={msg_type} node={node} has_tool_calls={has_tc}', flush=True)
            if has_tc:
                for tc in msg.tool_calls:
                    tc_id = tc.get('id', '')
                    tc_name = tc.get('name', '')
                    print(f'  TOOL_CALL: id={tc_id} name={tc_name}', flush=True)
            if isinstance(msg, ToolMessage):
                tc_id = msg.tool_call_id
                tc_name = getattr(msg, 'name', '')
                print(f'  TOOL_RESULT: call_id={tc_id} name={tc_name}', flush=True)
            if isinstance(msg, AIMessage) and msg.content:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)[:80]
                print(f'  AI_TEXT: {content[:80]}', flush=True)
        except Exception as e:
            print(f'MSG_PARSE_ERROR: {e}', flush=True)
    elif typ == 'updates':
        if isinstance(data, dict):
            for k, v in data.items():
                if k == '__interrupt__':
                    print(f'INTERRUPT', flush=True)
                elif isinstance(v, dict) and 'messages' in v:
                    for msg in v['messages']:
                        print(f'UPDATE_NODE={k}: {type(msg).__name__}', flush=True)

    if chunk_count > 30:
        print('...stopping', flush=True)
        break

print(f'Total chunks: {chunk_count}', flush=True)

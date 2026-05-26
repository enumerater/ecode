"""Deep debug: inspect exact message structure."""
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent import build_graph
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AIMessageChunk

graph = build_graph()
import uuid

# Check class hierarchy
print(f'AIMessageChunk is subclass of AIMessage: {issubclass(AIMessageChunk, AIMessage)}', flush=True)

thread_id = str(uuid.uuid4())
config = {'configurable': {'thread_id': thread_id}}
input_data = {
    'messages': [HumanMessage(content='列出当前目录的文件')],
    'project_root': 'E:\\work\\ecode',
    'permission_mode': 'auto_approve',
    'plan_mode': False,
}

print('\n--- Stream start ---', flush=True)
for chunk in graph.stream(input_data, stream_mode=['messages', 'updates'], config=config, version='v2'):
    if isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
        typ, data = chunk
    elif isinstance(chunk, dict):
        typ = chunk.get('type', '')
        data = chunk.get('data')
    else:
        continue

    if typ == 'messages':
        msg, metadata = data
        node = metadata.get('langgraph_node', '')

        # Check if it's an AI message with tool calls
        is_ai = isinstance(msg, (AIMessage, AIMessageChunk))
        has_tc = bool(getattr(msg, 'tool_calls', None))

        if isinstance(msg, ToolMessage):
            print(f'TOOL_MSG: call_id={msg.tool_call_id} name={getattr(msg, "name", "N/A")} content[:80]={(msg.content or "")[:80]}', flush=True)
        elif is_ai and has_tc:
            for tc in msg.tool_calls:
                print(f'AI_TC: node={node} id={tc.get("id","")} name={tc.get("name","")} args_keys={list(tc.get("args",{}).keys())}', flush=True)
        elif is_ai and msg.content:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)[:50]
            if content.strip():
                print(f'AI_TEXT: node={node} len={len(content)} preview={content[:60]}', flush=True)

    elif typ == 'updates' and isinstance(data, dict):
        for k, v in data.items():
            if k == '__interrupt__':
                print(f'INTERRUPT', flush=True)
            elif isinstance(v, dict):
                if 'usage' in v:
                    print(f'USAGE: node={k} {v["usage"]}', flush=True)
                if 'messages' in v:
                    for m in v['messages']:
                        is_ai = isinstance(m, (AIMessage, AIMessageChunk))
                        has_tc = bool(getattr(m, 'tool_calls', None))
                        if isinstance(m, ToolMessage):
                            print(f'UPD_TOOL: node={k} name={getattr(m, "name", "N/A")}', flush=True)
                        elif is_ai and has_tc:
                            for tc in m.tool_calls:
                                print(f'UPD_AI_TC: node={k} name={tc.get("name","")}', flush=True)

print('\n--- Done ---', flush=True)

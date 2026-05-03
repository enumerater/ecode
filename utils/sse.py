import json

def sse(event: str, data: dict):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
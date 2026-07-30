"""Debug: run one rollout and dump the full message format to see why _extract_queries finds nothing."""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from benchmax.platform.client import RolloutClient

PROJECT_DIR = Path(__file__).parent

from src.bundles import require_bundle

client = RolloutClient(api_key=os.environ.get("PLATFORM_API_KEY", ""))

raw_example = {
    "prompt": "Credit cards offer various rewards programs. Chase Sapphire Preferred earns 2X points on travel and dining. Points can be transferred to airline and hotel partners. The annual fee is $95. Chase Freedom Unlimited earns 1.5% cash back on all purchases with no annual fee. Both cards participate in Ultimate Rewards. You can combine points from multiple Chase cards into one account.",
    "target_n": 1,
    "reasoning_mode": "",
}

env_cls_file, env_metadata_file = require_bundle("linker_env")

env_cls_bytes = env_cls_file.read_bytes()
env_metadata_bytes = env_metadata_file.read_bytes()

print("Running one rollout...")
result = client.stream_rollout(
    raw_example=raw_example,
    env_cls_bytes=env_cls_bytes,
    env_metadata_bytes=env_metadata_bytes,
    llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
    llm_model="gpt-5.4",
    llm_api_key=os.environ["LLM_API_KEY"],
    max_turns=4,
    max_tool_calls=4,
    max_completion_tokens=3072,
    capture_messages=True,
    full_messages=True,
    include_event_meta=True,
)

print("\n" + "=" * 60)
print("RESULT KEYS:", list(result.keys()))
print("=" * 60)

messages = result.get("messages", [])
print(f"\nTotal messages: {len(messages)}")

for i, msg in enumerate(messages):
    print(f"\n--- Message {i} ---")
    print(f"  keys: {list(msg.keys())}")
    print(f"  role: {msg.get('role')}")
    content = msg.get("content")
    print(f"  content type: {type(content).__name__}")
    if isinstance(content, list):
        print(f"  content length: {len(content)}")
        for j, block in enumerate(content):
            if isinstance(block, dict):
                print(f"    block[{j}] type={block.get('type')} keys={list(block.keys())}")
                if block.get("type") == "tool_use":
                    print(f"    block[{j}] input={json.dumps(block.get('input', {}))[:200]}")
            else:
                print(f"    block[{j}] = {str(block)[:100]}")
    elif isinstance(content, str):
        print(f"  content (chars={len(content)}): {content[:200]}")
    else:
        print(f"  content: {content}")

    tool_calls = msg.get("tool_calls")
    if tool_calls is not None:
        print(f"  tool_calls type: {type(tool_calls).__name__}")
        if isinstance(tool_calls, list):
            for j, tc in enumerate(tool_calls):
                print(f"    tc[{j}] keys={list(tc.keys()) if isinstance(tc, dict) else type(tc)}")
                if isinstance(tc, dict):
                    func = tc.get("function")
                    if func:
                        print(f"    tc[{j}] function keys={list(func.keys()) if isinstance(func, dict) else type(func)}")
                        print(f"    tc[{j}] function.name={func.get('name') if isinstance(func, dict) else '?'}")
                        raw_args = func.get("arguments", "{}") if isinstance(func, dict) else "{}"
                        print(f"    tc[{j}] function.arguments type={type(raw_args).__name__}: {str(raw_args)[:200]}")
                    name = tc.get("name")
                    inp = tc.get("input")
                    if name:
                        print(f"    tc[{j}] name={name}")
                    if inp:
                        print(f"    tc[{j}] input={json.dumps(inp) if isinstance(inp, dict) else str(inp)[:200]}")

    for extra_key in msg:
        if extra_key not in ("role", "content", "tool_calls"):
            val = msg[extra_key]
            print(f"  {extra_key}: {str(val)[:200]}")

# Now test _extract_queries on these messages
from benchmax.rag.qa_generation.search_agent_linker import _extract_queries
queries = _extract_queries(messages)
print(f"\n{'='*60}")
print(f"_extract_queries result: {queries}")
print(f"{'='*60}")

# Also try assistant_messages
assistant_messages = result.get("assistant_messages", [])
queries2 = _extract_queries(assistant_messages)
print(f"_extract_queries on assistant_messages: {queries2}")

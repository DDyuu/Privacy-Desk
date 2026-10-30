import json

import httpx
import pytest

from app.llm.client import LLMError, NullLLM, OllamaLLM, OpenAICompatLLM, parse_json_array


def test_parse_json_array_with_code_fence():
    content = '```json\n[{"type":"NAME_CN","text":"张三","confidence":0.9}]\n```'
    items = parse_json_array(content)
    assert items[0]["text"] == "张三"


def test_parse_json_array_returns_empty_on_garbage():
    assert parse_json_array("抱歉，我无法识别") == []


def test_openai_client_sends_zero_temperature_and_parses():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["temperature"] == 0
        assert payload["model"] == "test-model"
        assert request.headers["Authorization"] == "Bearer sk-test"
        content = '[{"type":"NAME_CN","text":"张三","confidence":0.9,"reason":"人名"}]'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatLLM("https://api.test/v1", "sk-test", "test-model", client=client)
    items = llm.extract("张三来了", [{"code": "NAME_CN", "name": "姓名", "hint": "中文人名"}])
    assert llm.available() is True
    assert items[0]["text"] == "张三"


def test_openai_client_streams_sse_and_caps_output():
    parts = [
        json.dumps({"choices": [{"delta": {"content": '[{"type":"NAME_CN",'}}]}),
        json.dumps({"choices": [{"delta": {"content": '"text":"张三","confidence":0.9}]'}}]}),
    ]
    body = "".join(f"data: {part}\n\n" for part in parts) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["max_tokens"] > 0
        # 抽取任务关闭推理，避免推理模型把额度消耗在 reasoning_content 上
        assert payload["reasoning_effort"] == "none"
        return httpx.Response(
            200, text=body, headers={"content-type": "text/event-stream"}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatLLM("https://api.test/v1", "sk-test", "test-model", client=client)
    items = llm.extract("张三来了", [{"code": "NAME_CN", "name": "姓名"}])
    assert items[0]["text"] == "张三"
    assert llm.last_raw == '[{"type":"NAME_CN","text":"张三","confidence":0.9}]'


def test_openai_client_accepts_message_event_in_stream():
    event = {
        "choices": [
            {"message": {"content": '[{"type":"NAME_CN","text":"张三","confidence":0.9}]'}}
        ]
    }
    body = f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text=body, headers={"content-type": "text/event-stream"}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatLLM("https://api.test/v1", "sk-test", "test-model", client=client)
    items = llm.extract("张三", [])
    assert items[0]["text"] == "张三"


def test_openai_empty_content_keeps_raw_stream_for_diagnosis():
    event = {"choices": [{"delta": {"reasoning_content": "先分析一下"}}]}
    body = f"data: {json.dumps(event, ensure_ascii=False)}\n\ndata: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text=body, headers={"content-type": "text/event-stream"}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatLLM("https://api.test/v1", "sk-test", "test-model", client=client)
    with pytest.raises(LLMError) as excinfo:
        llm.extract("张三", [])
    assert "reasoning_content" in llm.last_raw
    assert "推理模型" in str(excinfo.value)


def test_openai_drops_reasoning_effort_when_service_rejects_it():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload)
        if "reasoning_effort" in payload:
            return httpx.Response(400, json={"error": "unknown parameter"})
        body = 'data: {"choices":[{"delta":{"content":"[]"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatLLM("https://api.test/v1", "sk-test", "test-model", client=client)
    assert llm.extract("张三", []) == []
    assert "reasoning_effort" in seen[0]
    assert "reasoning_effort" not in seen[1]


def test_openai_timeout_is_not_retried():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.ReadTimeout("slow model", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatLLM("https://api.test/v1", "sk-test", "test-model", client=client)
    with pytest.raises(LLMError):
        llm.extract("张三", [])
    assert calls["count"] == 1


def test_ollama_client_uses_json_format():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["format"]["type"] == "array"
        assert payload["options"]["num_predict"] > 0
        assert payload["options"]["repeat_penalty"] >= 1.3
        return httpx.Response(
            200,
            json={"message": {"content": '[{"type":"NAME_CN","text":"李四","confidence":0.8}]'}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OllamaLLM("http://127.0.0.1:11434", "qwen2.5:7b", client=client)
    items = llm.extract("李四", [{"code": "NAME_CN", "name": "姓名"}])
    assert items[0]["text"] == "李四"


def test_null_llm_is_unavailable():
    assert NullLLM().available() is False
    assert NullLLM().extract("abc", []) == []


def test_non_string_content_raises_llm_error():
    from app.llm.client import LLMError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OpenAICompatLLM("https://api.test/v1", "sk-test", "test-model", client=client)
    with pytest.raises(LLMError):
        llm.extract("张三", [])


def test_parse_single_object_wrapped():
    assert parse_json_array('{"type":"NAME_CN","text":"张三"}')[0]["text"] == "张三"


def test_ollama_timeout_is_not_retried():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.ReadTimeout("slow model", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = OllamaLLM("http://127.0.0.1:11434", "qwen2.5:7b", client=client)
    with pytest.raises(LLMError):
        llm.extract("张三", [])
    assert calls["count"] == 1

import json

import httpx
import pytest

from app.llm.client import NullLLM, OllamaLLM, OpenAICompatLLM, parse_json_array


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


def test_ollama_client_uses_json_format():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["format"] == "json"
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

import httpx

from app.llm.client import probe_ollama


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_probe_reports_models_and_present_model():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200, json={"models": [{"name": "qwen2.5:7b"}, {"name": "llama3:8b"}]}
        )

    result = probe_ollama(
        "http://127.0.0.1:11434", "qwen2.5:7b", client=_client(httpx.MockTransport(handler))
    )
    assert result["reachable"] is True
    assert result["models"] == ["qwen2.5:7b", "llama3:8b"]
    assert result["model_present"] is True
    assert result["message"] == ""


def test_probe_flags_missing_model():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "llama3:8b"}]})

    result = probe_ollama(
        "http://127.0.0.1:11434/", "qwen2.5:7b", client=_client(httpx.MockTransport(handler))
    )
    assert result["reachable"] is True
    assert result["model_present"] is False
    assert "ollama pull qwen2.5:7b" in result["message"]


def test_probe_unreachable_reports_message():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    result = probe_ollama(
        "http://127.0.0.1:11434", "qwen2.5:7b", client=_client(httpx.MockTransport(handler))
    )
    assert result["reachable"] is False
    assert result["models"] == []
    assert "无法连接" in result["message"]


def test_probe_empty_url_skips_request():
    result = probe_ollama("", "qwen2.5:7b")
    assert result["reachable"] is False
    assert result["message"] == "请先填写 Ollama 地址"

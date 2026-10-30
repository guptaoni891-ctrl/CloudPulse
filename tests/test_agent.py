import httpx
import pytest
from cloudpulse_agent.main import collect, send


def test_real_collection(tmp_path):
    result = collect(str(tmp_path))
    assert 0 <= result["cpu"] <= 100 and 0 <= result["memory"] <= 100
    assert 0 <= result["disk"] <= 100 and result["network_sent_bytes"] >= 0
    assert result["timestamp"].endswith("+00:00")


def test_retry_reuses_sample():
    bodies = []

    def handler(request):
        bodies.append(request.content)
        return httpx.Response(503 if len(bodies) == 1 else 202)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert send(client, "https://example.com", {"sample_id": "one"}, sleep=lambda _: None)
    assert len(bodies) == 2 and bodies[0] == bodies[1]


def test_auth_errors_stop_without_retry():
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(401))) as client:
        with pytest.raises(RuntimeError):
            send(client, "https://example.com", {"sample_id": "one"}, sleep=lambda _: None)


def test_exhaustion_is_bounded():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert not send(
            client, "https://example.com", {"sample_id": "one"}, attempts=3, sleep=lambda _: None
        )
    assert len(requests) == 3


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://localhost?key=secret",
        "https://example.com/#fragment",
        "http://localhost:bad",
        "https://user:password@example.com",
        "http://localhost:0",
        "http://local\nhost",
    ],
)
def test_invalid_server_urls_fail_before_sending_credentials(url):
    from cloudpulse_agent.main import server_url

    with pytest.raises(ValueError):
        server_url(url)


@pytest.mark.parametrize("status", [301, 400, 405, 413])
def test_permanent_http_errors_stop_without_retry(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError):
            send(client, "https://example.com", {"sample_id": "one"}, sleep=lambda _: None)
    assert len(calls) == 1


def test_cli_canonicalizes_host_uuid(monkeypatch):
    import sys
    from uuid import uuid4

    from cloudpulse_agent import main as module

    host_id = str(uuid4())
    captured = []
    monkeypatch.setenv("CLOUDPULSE_HOST_ID", host_id.upper())
    monkeypatch.setenv("CLOUDPULSE_AGENT_KEY", "test-key")
    monkeypatch.setenv("CLOUDPULSE_SERVER", "http://127.0.0.1:8000")
    monkeypatch.setattr(sys, "argv", ["cloudpulse-agent", "--once"])
    monkeypatch.setattr(module, "collect", lambda _: {"sample_id": "test"})
    monkeypatch.setattr(module, "send", lambda client, url, payload: captured.append(url) or True)
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 0
    assert captured == [f"http://127.0.0.1:8000/api/v1/hosts/{host_id}/metrics"]

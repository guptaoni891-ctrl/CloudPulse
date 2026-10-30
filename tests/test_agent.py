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

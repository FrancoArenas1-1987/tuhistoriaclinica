"""Real registration protocol and distinct network identities for integration tests."""
import itertools
import time
from fastapi.testclient import TestClient as FastAPITestClient

_id = itertools.count(1)


def test_client(app, ip=None, **kwargs):
    n = next(_id)
    ip = ip or f"198.18.{n // 250}.{n % 250 + 1}"
    async def with_client(scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "client": (ip, 50000)}
        await app(scope, receive, send)
    return FastAPITestClient(with_client, **kwargs)


def register(client, *, json):
    response = client.get("/api/auth/registration-form")
    if response.status_code != 200:
        return response
    form = response.json()
    time.sleep(form["minimum_seconds"] + .05)
    return client.post("/api/auth/register", json={**json, "form_token": form["token"], "website": ""})

import importlib.util
from pathlib import Path

import pytest


PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "platforms" / "43chat"
spec = importlib.util.spec_from_file_location("chat43_client", PLUGIN_DIR / "chat43_client.py")
client_mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(client_mod)


class FakeResponse:
    def __init__(self, status, text, payload=None):
        self.status = status
        self._text = text
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return self._text

    async def json(self, content_type=None):
        return self._payload


class FakeSession:
    def __init__(self):
        self.closed = False
        self.urls = []

    def request(self, method, url, **kwargs):
        self.urls.append(url)
        if url.startswith("https://predn.43chat.cn/"):
            return FakeResponse(405, "blocked")
        return FakeResponse(200, '{"code":0}', {"code": 0, "data": {"message_id": "sent"}})


@pytest.mark.asyncio
async def test_message_send_retries_canonical_host_after_405():
    client = client_mod.Chat43APIClient(
        client_mod.Chat43APIConfig(api_key="sk-test", base_url="https://predn.43chat.cn")
    )
    session = FakeSession()
    client._session = session

    message_id = await client.send_private_message("12373", "hello")

    assert message_id == "sent"
    assert session.urls == [
        "https://predn.43chat.cn/open/message/private/send",
        "https://43chat.cn/open/message/private/send",
    ]

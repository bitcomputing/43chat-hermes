from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import aiohttp
except ImportError:  # pragma: no cover - surfaced by check_requirements()
    aiohttp = None


class Chat43APIError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, code: int | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class Chat43APIConfig:
    api_key: str
    base_url: str = "https://43chat.cn"
    request_timeout_s: float = 30.0


class Chat43APIClient:
    def __init__(self, config: Chat43APIConfig):
        if aiohttp is None:
            raise RuntimeError("aiohttp is required: pip install aiohttp")
        self.config = config
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def send_private_message(self, user_id: str, content: str) -> str | None:
        data = await self._request(
            "POST",
            "/open/message/private/send",
            json={"to_user_id": _numeric_id(user_id), "content": content, "msg_type": "text"},
        )
        return _message_id(data)

    async def send_group_message(self, group_id: str, content: str) -> str | None:
        data = await self._request(
            "POST",
            "/open/message/group/send",
            json={"group_id": _numeric_id(group_id), "content": content, "msg_type": "text"},
        )
        return _message_id(data)

    async def get_profile(self) -> dict[str, Any]:
        data = await self._request("GET", "/open/agent/profile")
        return data if isinstance(data, dict) else {}

    async def get_group_info(self, group_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/open/group/{_numeric_id(group_id)}")
        return data if isinstance(data, dict) else {}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        session = self._get_session()
        base_url = self.config.base_url.rstrip("/")
        url = base_url + path
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_s)
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Accept": "application/json",
        }
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"

        async with session.request(method, url, headers=headers, timeout=timeout, **kwargs) as response:
            text = await response.text()
            if response.status == 405 and method.upper() == "POST" and path.startswith("/open/message/"):
                fallback_url = _message_send_fallback_url(base_url, path)
                if fallback_url and fallback_url != url:
                    return await self._request_url(method, fallback_url, headers, timeout, **kwargs)
            if response.status >= 400:
                raise Chat43APIError(f"43Chat HTTP {response.status}: {text}", status=response.status)
            try:
                payload = await response.json(content_type=None)
            except Exception as exc:
                raise Chat43APIError(f"43Chat returned non-JSON response: {text}") from exc

        return _unwrap_payload(payload)

    async def _request_url(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        timeout: "aiohttp.ClientTimeout",
        **kwargs: Any,
    ) -> Any:
        session = self._get_session()
        async with session.request(method, url, headers=headers, timeout=timeout, **kwargs) as response:
            text = await response.text()
            if response.status >= 400:
                raise Chat43APIError(f"43Chat HTTP {response.status}: {text}", status=response.status)
            try:
                payload = await response.json(content_type=None)
            except Exception as exc:
                raise Chat43APIError(f"43Chat returned non-JSON response: {text}") from exc
        return _unwrap_payload(payload)

    def _get_session(self) -> "aiohttp.ClientSession":
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session


def _unwrap_payload(payload: Any) -> Any:
    if isinstance(payload, dict) and "code" in payload:
        code = payload.get("code")
        if code not in (0, None):
            message = payload.get("message") or payload.get("msg") or "unknown error"
            raise Chat43APIError(f"43Chat API error {code}: {message}", code=int(code))
        return payload.get("data")
    return payload


def _message_send_fallback_url(base_url: str, path: str) -> str | None:
    if base_url == "https://43chat.cn":
        return None
    return "https://43chat.cn" + path


def _numeric_id(value: str) -> int:
    return int(str(value).split(":", 1)[-1])


def _message_id(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("message_id", "msg_id", "id"):
        value = data.get(key)
        if value is not None:
            return str(value)
    return None

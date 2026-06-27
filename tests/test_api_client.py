import httpx
import pytest

from print_desktop.services.api_client import ApiClient


class FakeHttpClient:
    def __init__(self):
        self.posts = []

    async def post(self, path: str, json: dict):
        self.posts.append((path, json))
        return httpx.Response(
            202,
            request=httpx.Request("POST", f"https://print-calc.homelab{path}"),
            json={
                "id": 1,
                "import_id": 1,
                "url": json["url"],
                "status": "pending",
                "model_id": None,
                "error_message": None,
                "at": "2026-06-27T08:00:00+00:00",
            },
        )


@pytest.mark.asyncio
async def test_import_makerworld_sends_empty_cookie_when_unset():
    client = ApiClient("https://print-calc.homelab")
    fake = FakeHttpClient()
    client._client = fake

    await client.import_makerworld("https://makerworld.com/en/models/123")

    assert fake.posts == [
        (
            "/api/makerworld/import",
            {
                "url": "https://makerworld.com/en/models/123",
                "session_cookie": "",
            },
        )
    ]


@pytest.mark.asyncio
async def test_import_makerworld_uses_saved_cookie():
    client = ApiClient("https://print-calc.homelab")
    fake = FakeHttpClient()
    client._client = fake
    client.set_makerworld_cookie("foo=bar")

    await client.import_makerworld("https://makerworld.com/en/models/456")

    assert fake.posts[0][1]["session_cookie"] == "foo=bar"

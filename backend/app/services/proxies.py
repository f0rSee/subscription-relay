from __future__ import annotations

from urllib.parse import urlsplit

from ..models import UpstreamProxy
from ..schemas import ProxyResponse
from ..security import SecretBox


def validate_proxy_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and parsed.port != 0
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and not any(char.isspace() for char in url)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "Proxy URL must be a valid http(s) URL without a path or query"
        )


def proxy_response(proxy: UpstreamProxy, secret_box: SecretBox) -> ProxyResponse:
    try:
        parsed = urlsplit(secret_box.decrypt(proxy.url_ciphertext))
        url_hint = f"{parsed.scheme}://{parsed.netloc.rsplit('@', 1)[-1]}"
    except ValueError:
        url_hint = "Encrypted value unavailable"
    return ProxyResponse(
        id=proxy.id,
        name=proxy.name,
        url_hint=url_hint,
        created_at=proxy.created_at,
        updated_at=proxy.updated_at,
    )

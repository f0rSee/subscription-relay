import base64

import pytest

from backend.app.services.subscriptions import (
    MAX_TRAFFIC_VALUE,
    parse_subscription,
    parse_subscription_userinfo,
)


@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize(
    "broken_uri",
    [
        "vless://id@[broken:443",
        "trojan://password@[not-an-ip]:443",
        *(
            "vmess://" + base64.b64encode(payload).decode()
            for payload in [b"[]", b"null", b"42", b'"text"', b"{invalid"]
        ),
        "vmess://%%%",
    ],
)
def test_skips_malformed_nodes_and_preserves_valid_order(broken_uri, encoded):
    valid = ["vless://id@one.example:443#One", "trojan://pw@two.example:443#Two"]
    body = f"{valid[0]}\n{broken_uri}\n{valid[1]}\n".encode()
    if encoded:
        body = base64.b64encode(body)

    nodes = parse_subscription(body)

    assert [node.uri for node in nodes] == valid
    assert [node.position for node in nodes] == [0, 1]
    assert [node.name for node in nodes] == ["One", "Two"]


def test_vmess_fragment_does_not_corrupt_base64_payload():
    payload = base64.b64encode(b'{"add":"vmess.example","ps":"Node"}').decode()
    uri = f"vmess://{payload}#external-name"

    nodes = parse_subscription(uri.encode())

    assert len(nodes) == 1
    assert nodes[0].uri == uri
    assert nodes[0].name == "Node"
    assert nodes[0].host == "vmess.example"


@pytest.mark.parametrize(
    "value",
    ["1e1000000000", str(MAX_TRAFFIC_VALUE + 1), "Infinity", "NaN", "-1"],
)
def test_invalid_traffic_values_do_not_discard_other_fields(value):
    usage = parse_subscription_userinfo(f"upload={value}; download=12; total=100")

    assert usage is not None
    assert usage.upload == 0
    assert usage.download == 12
    assert usage.total == 100


@pytest.mark.parametrize("suffix", ["", ".9"])
def test_traffic_value_boundary_preserves_fraction_truncation(suffix):
    usage = parse_subscription_userinfo(f"upload={MAX_TRAFFIC_VALUE}{suffix}")

    assert usage is not None
    assert usage.upload == MAX_TRAFFIC_VALUE

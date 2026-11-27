"""AWS Signature Version 4 for S3, using the standard library.

The canonical request, the string to sign, and the signature follow the
published header and presigned-URL examples. Nothing here opens a socket.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import quote

ALGORITHM = "AWS4-HMAC-SHA256"
EMPTY_PAYLOAD_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def amz_date(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _encode(value: str) -> str:
    return quote(value, safe="-_.~")


def _canonical_headers(headers: list[tuple[str, str]]) -> tuple[str, str]:
    folded: dict[str, str] = {}
    for name, value in headers:
        key = name.strip().lower()
        folded[key] = " ".join(value.split())
    names = sorted(folded)
    block = "".join(f"{name}:{folded[name]}\n" for name in names)
    return block, ";".join(names)


def canonical_request(
    method: str,
    uri: str,
    query: list[tuple[str, str]],
    headers: list[tuple[str, str]],
    payload_hash: str,
) -> str:
    """Build the canonical request. ``query`` is encoded and sorted here."""

    encoded = sorted((_encode(name), _encode(value)) for name, value in query)
    query_string = "&".join(f"{name}={value}" for name, value in encoded)
    header_block, signed = _canonical_headers(headers)
    return f"{method.upper()}\n{uri}\n{query_string}\n{header_block}\n{signed}\n{payload_hash}"


def string_to_sign(canonical: str, *, amz: str, region: str, service: str = "s3") -> str:
    scope = f"{amz[:8]}/{region}/{service}/aws4_request"
    digest = sha256_hex(canonical.encode("utf-8"))
    return f"{ALGORITHM}\n{amz}\n{scope}\n{digest}"


def signing_key(secret: str, date_stamp: str, region: str, service: str = "s3") -> bytes:
    def _mac(key: bytes, message: str) -> bytes:
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()

    key = _mac(f"AWS4{secret}".encode("utf-8"), date_stamp)
    key = _mac(key, region)
    key = _mac(key, service)
    return _mac(key, "aws4_request")


def signature_hex(to_sign: str, *, secret: str, date_stamp: str, region: str, service: str = "s3") -> str:
    key = signing_key(secret, date_stamp, region, service)
    return hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()


def authorization_header(
    *,
    access_key: str,
    signed_header_names: str,
    signature: str,
    amz: str,
    region: str,
    service: str = "s3",
) -> str:
    scope = f"{amz[:8]}/{region}/{service}/aws4_request"
    return (
        f"{ALGORITHM} Credential={access_key}/{scope},"
        f"SignedHeaders={signed_header_names},"
        f"Signature={signature}"
    )


def sign_headers(
    *,
    method: str,
    host: str,
    uri: str,
    region: str,
    access_key: str,
    secret: str,
    payload: bytes,
    content_type: str | None,
    now: datetime,
    extra_headers: list[tuple[str, str]] | None = None,
) -> dict[str, str]:
    """Headers for one signed request. The payload hash covers ``payload``."""

    amz = amz_date(now)
    payload_hash = sha256_hex(payload)
    headers = [
        ("host", host),
        ("x-amz-content-sha256", payload_hash),
        ("x-amz-date", amz),
    ]
    if content_type:
        headers.append(("content-type", content_type))
    if extra_headers:
        headers.extend(extra_headers)
    canonical = canonical_request(method, uri, [], headers, payload_hash)
    to_sign = string_to_sign(canonical, amz=amz, region=region)
    signed = signature_hex(to_sign, secret=secret, date_stamp=amz[:8], region=region)
    _, names = _canonical_headers(headers)
    sent = {name.lower(): value for name, value in headers}
    sent["authorization"] = authorization_header(
        access_key=access_key,
        signed_header_names=names,
        signature=signed,
        amz=amz,
        region=region,
    )
    return sent


def presign_url(
    *,
    method: str,
    host: str,
    uri: str,
    region: str,
    access_key: str,
    secret: str,
    now: datetime,
    expires: int,
    scheme: str = "https",
    extra_query: list[tuple[str, str]] | None = None,
) -> str:
    """A presigned URL. The payload is ``UNSIGNED-PAYLOAD``, as in the S3 example."""

    amz = amz_date(now)
    scope = f"{amz[:8]}/{region}/s3/aws4_request"
    query = [
        ("X-Amz-Algorithm", ALGORITHM),
        ("X-Amz-Credential", f"{access_key}/{scope}"),
        ("X-Amz-Date", amz),
        ("X-Amz-Expires", str(int(expires))),
        ("X-Amz-SignedHeaders", "host"),
    ]
    if extra_query:
        query.extend(extra_query)
    canonical = canonical_request(method, uri, query, [("host", host)], "UNSIGNED-PAYLOAD")
    to_sign = string_to_sign(canonical, amz=amz, region=region)
    signed = signature_hex(to_sign, secret=secret, date_stamp=amz[:8], region=region)
    encoded = sorted((_encode(name), _encode(value)) for name, value in query)
    query_string = "&".join(f"{name}={value}" for name, value in encoded)
    return f"{scheme}://{host}{uri}?{query_string}&X-Amz-Signature={signed}"

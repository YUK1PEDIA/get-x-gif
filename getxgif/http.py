from __future__ import annotations

import os
import ssl
import urllib.error
import urllib.request
from typing import Optional

from .errors import TweetError

USER_AGENT = (
    'Mozilla/5.0 (compatible; Googlebot/2.1; '
    '+http://www.google.com/bot.html)'
)


def _candidate_ca_files():
    """按优先级列出可用的 CA 证书 bundle 路径"""
    paths: list[Optional[str]] = []
    try:
        import certifi  # type: ignore[import-not-found]

        paths.append(certifi.where())
    except Exception:
        pass
    paths += [
        '/etc/ssl/cert.pem',
        '/etc/ssl/certs/ca-certificates.crt',
        '/usr/local/etc/openssl/cert.pem',
        '/usr/local/etc/openssl@3/cert.pem',
        '/opt/homebrew/etc/openssl/cert.pem',
        '/opt/homebrew/etc/openssl@3/cert.pem',
    ]
    seen: set[str] = set()
    for p in paths:
        if p and p not in seen and os.path.exists(p):
            seen.add(p)
            yield p


def _is_cert_verification_error(exc) -> bool:
    """判断异常是否由 TLS 证书验证失败引起"""
    if isinstance(exc, urllib.error.URLError):
        exc = exc.reason
    return isinstance(exc, ssl.SSLCertVerificationError)


def open_url(
    url: str,
    timeout: float = 20.0,
    insecure: bool = False,
    headers: Optional[dict] = None,
):
    """打开 URL，返回文件类响应对象（配合 ``with`` 使用）

    部分 Python 发行版（如 python.org 的 macOS 安装包未运行
    "Install Certificates.command"）缺少系统 CA 证书，导致 TLS 验证失败
    这里依次尝试：默认上下文 -> certifi/常见 CA bundle -> ``--insecure``
    服务端返回的 HTTP 错误码（4xx/5xx）会原样抛出，不会被误判为 TLS 问题
    """
    req_headers = {'User-Agent': USER_AGENT}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)

    if insecure:
        return urllib.request.urlopen(
            req, timeout=timeout, context=ssl._create_unverified_context()
        )

    try:
        return urllib.request.urlopen(
            req, timeout=timeout, context=ssl.create_default_context()
        )
    except (urllib.error.URLError, ssl.SSLError) as e:
        if not _is_cert_verification_error(e):
            raise

    for cafile in _candidate_ca_files():
        try:
            ctx = ssl.create_default_context(cafile=cafile)
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except (urllib.error.URLError, ssl.SSLError) as e:
            if not _is_cert_verification_error(e):
                raise
        except Exception:
            # CA bundle 本身无法加载（如文件损坏）时继续尝试下一个
            continue

    raise TweetError(
        'TLS 证书验证失败。可尝试：pip install certifi；'
        '或使用 --insecure 跳过证书校验。'
    )

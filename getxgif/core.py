"""X 博文链接解析与媒体信息获取。"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

from .errors import TweetError
from .http import open_url
from .token import syndication_token

SYNDICATION_URL = 'https://cdn.syndication.twimg.com/tweet-result'
FXTWITTER_URL = 'https://api.fxtwitter.com/status/'

_TWEET_ID_RE = re.compile(r'(?:^|/)(?:status(?:es)?|i/web/status)/(\d{5,})')
_HOST_RE = re.compile(r'^(?:www|m|mobile)\.')
_X_HOSTS = (
    'twitter.com',
    'x.com',
    'twitter3e4tixl4xyajtrzo62zg5vztmjuricljdp2c5kshju4avyoid.onion',
)

KIND_GIF = 'gif'
KIND_VIDEO = 'video'


@dataclass
class Media:
    """博文中的一条 GIF 或视频（X 均以 MP4 形式提供）。"""

    tweet_id: str
    index: int  # 该博文中第几个可下载媒体（从 1 起）
    url: str  # 可直接下载的 MP4 地址
    kind: str = KIND_GIF  # 'gif' | 'video'
    width: Optional[int] = None
    height: Optional[int] = None
    thumbnail_url: Optional[str] = None
    source: str = 'syndication'  # syndication / fxtwitter

    @property
    def ext(self) -> str:
        return 'mp4'

    @property
    def label(self) -> str:
        return 'GIF' if self.kind == KIND_GIF else '视频'


@dataclass
class TweetInfo:
    tweet_id: str
    screen_name: Optional[str] = None
    text: Optional[str] = None
    media: list[Media] = field(default_factory=list)
    media_types: list[str] = field(default_factory=list)  # 原始媒体类型，如 photo/video

    @property
    def gifs(self) -> list[Media]:
        return [m for m in self.media if m.kind == KIND_GIF]

    @property
    def videos(self) -> list[Media]:
        return [m for m in self.media if m.kind == KIND_VIDEO]


# ---------------------------------------------------------------------------
# URL 解析
# ---------------------------------------------------------------------------

def _resolve_redirect(url: str, timeout: float = 15.0) -> Optional[str]:
    """跟随重定向并返回最终 URL（用于 t.co 短链）。"""
    try:
        with open_url(url, timeout=timeout) as resp:
            return resp.geturl()
    except Exception:
        return None


def extract_tweet_id(url: str) -> Optional[str]:
    """从博文链接中提取博文 ID。

    支持：x.com / twitter.com（含 www、m、mobile 前缀、i/web/status、
    /photo/1、/video/1 等后缀）、t.co 短链（自动跟随重定向）。
    """
    url = (url or '').strip()
    if not url:
        return None
    if '://' not in url:
        url = 'https://' + url

    parsed = urllib.parse.urlparse(url)
    host = (parsed.netloc or '').lower()

    if host in ('t.co', 'www.t.co'):
        resolved = _resolve_redirect(url)
        return extract_tweet_id(resolved) if resolved else None

    host = _HOST_RE.sub('', host)
    if host not in _X_HOSTS:
        return None

    m = _TWEET_ID_RE.search(parsed.path or '')
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# 获取博文 JSON
# ---------------------------------------------------------------------------

def fetch_tweet_via_syndication(
    tweet_id: str, timeout: float = 20.0, insecure: bool = False
) -> dict:
    """通过 X 官方嵌入（syndication）接口获取博文 JSON，无需登录。"""
    query = urllib.parse.urlencode(
        {'id': tweet_id, 'lang': 'en', 'token': syndication_token(tweet_id)}
    )
    url = f'{SYNDICATION_URL}?{query}'
    try:
        with open_url(url, timeout=timeout, insecure=insecure) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise TweetError(f'syndication 接口返回 HTTP {e.code}') from e
    except urllib.error.URLError as e:
        raise TweetError(f'网络错误：{e.reason}') from e


def fetch_tweet_via_fxtwitter(
    tweet_id: str, timeout: float = 20.0, insecure: bool = False
) -> dict:
    """兜底方案：通过 fxtwitter 社区接口获取博文 JSON。"""
    url = f'{FXTWITTER_URL}{tweet_id}'
    try:
        with open_url(url, timeout=timeout, insecure=insecure) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        raise TweetError(f'fxtwitter 接口返回 HTTP {e.code}') from e
    except urllib.error.URLError as e:
        raise TweetError(f'网络错误：{e.reason}') from e

    tweet = data.get('tweet') or {}
    if data.get('code') != 200 or not tweet:
        raise TweetError(f"fxtwitter 返回错误：{data.get('message') or data.get('code')}")
    return tweet


# ---------------------------------------------------------------------------
# 提取媒体
# ---------------------------------------------------------------------------

def _pick_mp4_variant(variants: list[dict], prefer_original: bool) -> Optional[dict]:
    """从变体列表中挑选 MP4 下载地址。

    - ``prefer_original=True``（GIF）：优先 ``bitrate == 0`` 的原始文件；
    - 否则（普通视频）：取码率最高者，画质最好。
    """
    mp4s = [
        v for v in variants
        if v.get('content_type') == 'video/mp4' and v.get('url')
    ]
    if not mp4s:
        return None
    if prefer_original:
        return next((v for v in mp4s if v.get('bitrate') == 0), mp4s[0])
    return max(mp4s, key=lambda v: v.get('bitrate') or 0)


def _extract_media_syndication(data: dict, tweet_id: str) -> list[Media]:
    """从 syndication JSON 中提取 ``animated_gif`` 与 ``video`` 媒体。"""
    media: list[Media] = []
    for entry in data.get('mediaDetails') or []:
        mtype = entry.get('type')
        if mtype == 'animated_gif':
            kind = KIND_GIF
        elif mtype == 'video':
            kind = KIND_VIDEO
        else:
            continue
        variants = (entry.get('video_info') or {}).get('variants') or []
        variant = _pick_mp4_variant(variants, prefer_original=(kind == KIND_GIF))
        if not variant:
            continue
        ratio = (entry.get('video_info') or {}).get('aspect_ratio') or []
        w, h = (ratio[0], ratio[1]) if len(ratio) == 2 else (None, None)
        media.append(
            Media(
                tweet_id=tweet_id,
                index=0,  # 索引随后统一分配
                url=variant['url'],
                kind=kind,
                width=w,
                height=h,
                thumbnail_url=entry.get('media_url_https'),
                source='syndication',
            )
        )
    return media


def _extract_media_fxtwitter(tweet: dict, tweet_id: str) -> list[Media]:
    """从 fxtwitter JSON 中提取 ``gif`` 与 ``video`` 媒体。"""
    media: list[Media] = []
    for m in (tweet.get('media') or {}).get('all') or []:
        mtype = m.get('type')
        if mtype == 'gif':
            kind = KIND_GIF
        elif mtype == 'video':
            kind = KIND_VIDEO
        else:
            continue
        if not m.get('url'):
            continue
        media.append(
            Media(
                tweet_id=tweet_id,
                index=0,
                url=m['url'],
                kind=kind,
                width=m.get('width'),
                height=m.get('height'),
                thumbnail_url=m.get('thumbnail_url'),
                source='fxtwitter',
            )
        )
    return media


def _assign_indexes(media: list[Media]) -> list[Media]:
    for i, m in enumerate(media, start=1):
        m.index = i
    return media


# ---------------------------------------------------------------------------
# 对外主入口
# ---------------------------------------------------------------------------

def get_tweet_media(
    tweet_id: str,
    timeout: float = 20.0,
    insecure: bool = False,
) -> TweetInfo:
    """获取博文中的可下载媒体（GIF 与普通视频）。

    优先使用 syndication 接口；失败时回退 fxtwitter。接口成功但没有匹配
    媒体时返回空的 ``TweetInfo``（不含硬错误），由调用方给出提示。
    """
    info: Optional[TweetInfo] = None
    notes: list[str] = []

    try:
        data = fetch_tweet_via_syndication(tweet_id, timeout, insecure)
        if data.get('__typename') in ('TweetTombstone', 'TweetUnavailable'):
            reason = (data.get('tombstone') or {}).get('text')
            if isinstance(reason, dict):
                reason = reason.get('text')
            if isinstance(reason, str):
                reason = reason.removesuffix('. Learn more')
            else:
                reason = None
            raise TweetError(
                f'博文不可用（可能已删除或受保护）{": " + reason if reason else ""}'
            )
        raw = _extract_media_syndication(data, tweet_id)
        media_types = [m.get('type') for m in data.get('mediaDetails') or []]
        info = TweetInfo(
            tweet_id=tweet_id,
            screen_name=(data.get('user') or {}).get('screen_name'),
            text=data.get('text'),
            media=_assign_indexes(raw),
            media_types=media_types,
        )
        if raw:
            return info
        notes.append('syndication 未返回可下载媒体')
    except TweetError as e:
        notes.append(f'syndication：{e}')

    # 兜底：fxtwitter
    try:
        tweet = fetch_tweet_via_fxtwitter(tweet_id, timeout, insecure)
        raw = _extract_media_fxtwitter(tweet, tweet_id)
        if raw:
            return TweetInfo(
                tweet_id=tweet_id,
                screen_name=(tweet.get('author') or {}).get('screen_name'),
                text=tweet.get('text'),
                media=_assign_indexes(raw),
                media_types=[
                    m.get('type')
                    for m in (tweet.get('media') or {}).get('all') or []
                ],
            )
        if info is None:
            info = TweetInfo(
                tweet_id=tweet_id,
                screen_name=(tweet.get('author') or {}).get('screen_name'),
                text=tweet.get('text'),
                media_types=[
                    m.get('type')
                    for m in (tweet.get('media') or {}).get('all') or []
                ],
            )
    except TweetError as e:
        notes.append(f'fxtwitter：{e}')

    if info is not None:
        return info
    raise TweetError('；'.join(notes) or '未知错误')

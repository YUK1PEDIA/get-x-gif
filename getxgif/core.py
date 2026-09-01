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


@dataclass
class GifMedia:
    """博文中的一条 GIF（X 将 GIF 存储为 MP4 视频）"""

    tweet_id: str
    index: int  # 该博文中第几个 GIF（从 1 起）
    url: str  # 可直接下载的 MP4 地址
    width: Optional[int] = None
    height: Optional[int] = None
    thumbnail_url: Optional[str] = None
    source: str = 'syndication'  # syndication / fxtwitter

    @property
    def ext(self) -> str:
        return 'mp4'


@dataclass
class TweetInfo:
    tweet_id: str
    screen_name: Optional[str] = None
    text: Optional[str] = None
    gifs: list[GifMedia] = field(default_factory=list)


def _resolve_redirect(url: str, timeout: float = 15.0) -> Optional[str]:
    """跟随重定向并返回最终 URL（用于 t.co 短链）"""
    try:
        with open_url(url, timeout=timeout) as resp:
            return resp.geturl()
    except Exception:
        return None


def extract_tweet_id(url: str) -> Optional[str]:
    """从博文链接中提取博文 ID

    支持：x.com / twitter.com（含 www、m、mobile 前缀、i/web/status、/photo/1、/video/1 等后缀）、t.co 短链（自动跟随重定向）
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


def fetch_tweet_via_syndication(
    tweet_id: str, timeout: float = 20.0, insecure: bool = False
) -> dict:
    """通过 X 官方嵌入（syndication）接口获取博文 JSON，无需登录"""
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
    """通过 fxtwitter 社区接口获取博文 JSON"""
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


def extract_gifs_syndication(data: dict, tweet_id: str) -> list[GifMedia]:
    """从 syndication JSON 中提取 ``animated_gif`` 媒体"""
    gifs: list[GifMedia] = []
    for i, media in enumerate(data.get('mediaDetails') or [], start=1):
        if media.get('type') != 'animated_gif':
            continue
        variants = (media.get('video_info') or {}).get('variants') or []
        # 优先 bitrate=0（原始文件），其次第一个 video/mp4 变体
        best = next((v for v in variants if v.get('bitrate') == 0), None)
        if best is None:
            best = next(
                (v for v in variants if v.get('content_type') == 'video/mp4'), None
            )
        if not best or not best.get('url'):
            continue
        ratio = (media.get('video_info') or {}).get('aspect_ratio') or []
        w, h = (ratio[0], ratio[1]) if len(ratio) == 2 else (None, None)
        gifs.append(
            GifMedia(
                tweet_id=tweet_id,
                index=i,
                url=best['url'],
                width=w,
                height=h,
                thumbnail_url=media.get('media_url_https'),
                source='syndication',
            )
        )
    return gifs


def extract_gifs_fxtwitter(tweet: dict, tweet_id: str) -> list[GifMedia]:
    """从 fxtwitter JSON 中提取 ``type == gif`` 的媒体"""
    gifs: list[GifMedia] = []
    all_media = (tweet.get('media') or {}).get('all') or []
    for i, m in enumerate(all_media, start=1):
        if m.get('type') != 'gif' or not m.get('url'):
            continue
        gifs.append(
            GifMedia(
                tweet_id=tweet_id,
                index=i,
                url=m['url'],
                width=m.get('width'),
                height=m.get('height'),
                thumbnail_url=m.get('thumbnail_url'),
                source='fxtwitter',
            )
        )
    return gifs


def get_tweet_gifs(
    tweet_id: str, timeout: float = 20.0, insecure: bool = False
) -> TweetInfo:
    """获取博文中的 GIF 列表

    优先使用 syndication 接口；若失败或其中没有 GIF，则回退到 fxtwitter
    """
    syndication_note: Optional[str] = None
    try:
        data = fetch_tweet_via_syndication(tweet_id, timeout, insecure)
        gifs = extract_gifs_syndication(data, tweet_id)
        info = TweetInfo(
            tweet_id=tweet_id,
            screen_name=(data.get('user') or {}).get('screen_name'),
            text=data.get('text'),
            gifs=gifs,
        )
        if gifs:
            return info
        media_types = [m.get('type') for m in data.get('mediaDetails') or []]
        syndication_note = f'syndication 中未找到 GIF（媒体类型：{media_types or "无"}）'
    except TweetError as e:
        syndication_note = str(e)

    try:
        tweet = fetch_tweet_via_fxtwitter(tweet_id, timeout, insecure)
        gifs = extract_gifs_fxtwitter(tweet, tweet_id)
        if gifs:
            return TweetInfo(
                tweet_id=tweet_id,
                screen_name=(tweet.get('author') or {}).get('screen_name'),
                text=tweet.get('text'),
                gifs=gifs,
            )
    except TweetError as e:
        raise TweetError(f'{syndication_note}；fxtwitter：{e}') from e

    raise TweetError(syndication_note or '未找到 GIF')

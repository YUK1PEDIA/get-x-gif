"""get-x-gif：下载 X（Twitter）博文中的 GIF 图（含普通视频转 GIF）。"""

from .core import Media, TweetError, TweetInfo, extract_tweet_id, get_tweet_media
from .download import (
    convert_mp4_to_gif,
    convert_mp4_to_gif_within,
    download_file,
    ffmpeg_available,
)

__version__ = '0.5.0'

__all__ = [
    'Media',
    'TweetError',
    'TweetInfo',
    'convert_mp4_to_gif',
    'convert_mp4_to_gif_within',
    'download_file',
    'extract_tweet_id',
    'ffmpeg_available',
    'get_tweet_media',
    '__version__',
]

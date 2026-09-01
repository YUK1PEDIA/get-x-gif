from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from . import __version__
from .core import GifMedia, TweetError, extract_tweet_id, get_tweet_gifs
from .download import (
    DownloadError,
    convert_mp4_to_gif,
    download_file,
    ffmpeg_available,
)


def _default_basename(
    tweet_id: str, screen_name: Optional[str], index: int, total: int, ext: str
) -> str:
    parts = []
    if screen_name:
        parts.append(screen_name)
    parts.append(tweet_id)
    if total > 1:
        parts.append(str(index))
    return '_'.join(parts) + f'.{ext}'


def _default_output_dir() -> str:
    """默认输出目录：项目根目录下的 output/"""
    package_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(package_dir)
    return os.path.join(project_root, 'output')


def _plan_outputs(
    gif: GifMedia,
    out: Optional[str],
    screen_name: Optional[str],
    total: int,
    to_gif: bool,
) -> tuple[str, str]:
    """返回 (最终文件路径, 临时 MP4 路径)。最终文件为 .gif 时临时 MP4 需转换后删除"""
    ext = 'gif' if to_gif else 'mp4'
    single = total == 1
    base = _default_basename(gif.tweet_id, screen_name, gif.index, total, ext)

    if out:
        if single and not os.path.isdir(out) and not out.endswith(os.sep):
            # 单个 GIF 且 -o 指向一个不存在的路径：视为文件路径
            final = out if os.path.splitext(out)[1] else out + '.' + ext
        else:
            os.makedirs(out, exist_ok=True)
            final = os.path.join(out, base)
    else:
        final = base

    final = os.path.abspath(final)
    os.makedirs(os.path.dirname(final), exist_ok=True)
    tmp_mp4 = final + '.mp4' if to_gif else final
    return final, tmp_mp4


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog='get-x-gif',
        description='下载 X 博文中的 GIF 图。',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例：\n'
            '  get-x-gif "https://x.com/user/status/1234567890123456789"\n'
            '  get-x-gif "https://twitter.com/user/status/1234567890123456789" '
            '-o ~/Downloads\n'
            '  get-x-gif "https://x.com/user/status/1234567890123456789" --gif\n'
        ),
    )
    parser.add_argument('url', help='X 博文链接（x.com / twitter.com / t.co）')
    parser.add_argument(
        '-o',
        '--output',
        metavar='PATH',
        help='输出文件或目录（默认项目根目录下的 output/）',
    )
    parser.add_argument(
        '-n', '--index', type=int, metavar='N', help='只下载第 N 个 GIF（从 1 起）'
    )
    parser.add_argument(
        '--gif',
        action='store_true',
        help='用 ffmpeg 转成真正的 .gif（默认保存 MP4，X 的 GIF 本身就是 MP4）',
    )
    parser.add_argument(
        '--insecure', action='store_true', help='跳过 TLS 证书校验'
    )
    parser.add_argument(
        '-v', '--version', action='version', version=f'%(prog)s {__version__}'
    )
    args = parser.parse_args(argv)

    # 默认输出到项目根目录下的 output/
    out = args.output
    if out is None:
        out = _default_output_dir()
        os.makedirs(out, exist_ok=True)

    try:
        tweet_id = extract_tweet_id(args.url)
        if not tweet_id:
            print(f'错误：无法从链接中解析出博文 ID：{args.url}', file=sys.stderr)
            return 2

        print(f'解析到博文 ID：{tweet_id}')
        info = get_tweet_gifs(tweet_id, insecure=args.insecure)

        if not info.gifs:
            print('该博文没有 GIF 图。', file=sys.stderr)
            return 1

        if args.index is not None:
            if args.index < 1 or args.index > len(info.gifs):
                print(
                    f'错误：--index {args.index} 超出范围（该博文共 {len(info.gifs)} 个 GIF）',
                    file=sys.stderr,
                )
                return 2
            selected = [info.gifs[args.index - 1]]
        else:
            selected = info.gifs

        if args.gif and not ffmpeg_available():
            print(
                '错误：未找到 ffmpeg，无法转换为 .gif。'
                '请先安装 ffmpeg（macOS: brew install ffmpeg），'
                '或去掉 --gif 直接保存 MP4。',
                file=sys.stderr,
            )
            return 2

        results = []
        for g in selected:
            final, tmp_mp4 = _plan_outputs(
                g, out, info.screen_name, len(info.gifs), args.gif
            )
            size = f'{g.width}x{g.height} ' if g.width and g.height else ''
            print(f'[{g.index}/{len(info.gifs)}] 下载 GIF {size}({g.source}) {g.url}')
            download_file(g.url, tmp_mp4, insecure=args.insecure)
            if args.gif:
                print('    转换为 .gif ...')
                convert_mp4_to_gif(tmp_mp4, final)
                os.remove(tmp_mp4)
            else:
                final = tmp_mp4
            size_mb = os.path.getsize(final) / 1048576
            print(f'    -> 已保存 {final} ({size_mb:.1f} MB)')
            results.append(final)

        if len(results) > 1:
            print(f'共下载 {len(results)} 个 GIF。')
        return 0

    except TweetError as e:
        print(f'错误：{e}', file=sys.stderr)
        return 1
    except DownloadError as e:
        print(f'错误：{e}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\n已取消', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())

"""命令行入口：get-x-gif <博文链接>"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from . import __version__
from .core import Media, TweetError, extract_tweet_id, get_tweet_media
from .download import (
    DownloadError,
    convert_mp4_to_gif,
    convert_mp4_to_gif_within,
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
    """默认输出目录：项目根目录下的 output/。"""
    package_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(package_dir)
    return os.path.join(project_root, 'output')


def _plan_outputs(
    media: Media,
    out: Optional[str],
    screen_name: Optional[str],
    total: int,
    to_gif: bool,
) -> tuple[str, str]:
    """返回 (最终文件路径, 临时 MP4 路径)。最终文件为 .gif 时临时 MP4 需转换后删除。"""
    ext = 'gif' if to_gif else 'mp4'
    single = total == 1
    base = _default_basename(media.tweet_id, screen_name, media.index, total, ext)

    if out:
        if single and not os.path.isdir(out) and not out.endswith(os.sep):
            # 单个媒体且 -o 指向一个不存在的路径：视为文件路径
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
        description='下载 X（Twitter）博文中的 GIF 图（普通视频自动转成 GIF）。',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例：\n'
            '  get-x-gif "https://x.com/user/status/1234567890123456789"\n'
            '  get-x-gif "https://twitter.com/user/status/1234567890123456789" '
            '-o ~/Downloads\n'
            '  get-x-gif "https://x.com/user/status/1234567890123456789" --mp4\n'
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
        '-n',
        '--index',
        type=int,
        metavar='N',
        help='只下载第 N 个 GIF/视频（从 1 起）',
    )
    parser.add_argument(
        '--mp4',
        action='store_true',
        help='保存原始 MP4（默认转成 .gif，需要 ffmpeg）',
    )
    parser.add_argument(
        '--max-size',
        type=float,
        metavar='MB',
        default=5.0,
        help='GIF 目标体积上限（MB，默认 5；0 表示不限制，超限自动降低宽度/帧率）',
    )
    parser.add_argument(
        '--insecure', action='store_true', help='跳过 TLS 证书校验'
    )
    parser.add_argument(
        '-v', '--version', action='version', version=f'%(prog)s {__version__}'
    )
    args = parser.parse_args(argv)

    # 默认输出到项目根目录下的 output/（自动创建）
    out = args.output
    if out is None:
        out = _default_output_dir()
        os.makedirs(out, exist_ok=True)

    to_gif = not args.mp4

    try:
        tweet_id = extract_tweet_id(args.url)
        if not tweet_id:
            print(f'错误：无法从链接中解析出博文 ID：{args.url}', file=sys.stderr)
            return 2

        print(f'解析到博文 ID：{tweet_id}')
        info = get_tweet_media(tweet_id, insecure=args.insecure)

        if not info.media:
            print('该博文没有可下载的 GIF/视频。', file=sys.stderr)
            return 1

        if args.index is not None:
            if args.index < 1 or args.index > len(info.media):
                print(
                    f'错误：--index {args.index} 超出范围'
                    f'（该博文共 {len(info.media)} 个可下载媒体）',
                    file=sys.stderr,
                )
                return 2
            selected = [info.media[args.index - 1]]
        else:
            selected = info.media

        if to_gif and not ffmpeg_available():
            print(
                '错误：未找到 ffmpeg，默认输出 .gif 需要 ffmpeg。'
                '请先安装（macOS: brew install ffmpeg，'
                'Windows: winget install Gyan.FFmpeg），'
                '或加 --mp4 直接保存 MP4。',
                file=sys.stderr,
            )
            return 2

        results = []
        for m in selected:
            final, tmp_mp4 = _plan_outputs(
                m, out, info.screen_name, len(info.media), to_gif
            )
            size = f'{m.width}x{m.height} ' if m.width and m.height else ''
            print(f'[{m.index}/{len(info.media)}] 下载 {m.label} {size}({m.source}) {m.url}')
            download_file(m.url, tmp_mp4, insecure=args.insecure)
            if to_gif:
                if args.max_size > 0:
                    print(
                        f'    转换为 .gif（目标 ≤{args.max_size} MB，'
                        '自动调整尺寸/帧率）...'
                    )
                else:
                    print('    转换为 .gif（不限制体积）...')
                _, used_w, used_f, ok = convert_mp4_to_gif_within(
                    tmp_mp4,
                    final,
                    max_size_mb=args.max_size,
                )
                print(f'    -> 采用 {used_w}px / {used_f}fps')
                if not ok:
                    print(
                        f'    警告：最小参数下仍超过 {args.max_size} MB',
                        file=sys.stderr,
                    )
                os.remove(tmp_mp4)
            size_mb = os.path.getsize(final) / 1048576
            print(f'    -> 已保存 {final} ({size_mb:.1f} MB)')
            results.append(final)

        if len(results) > 1:
            print(f'共下载 {len(results)} 个媒体。')
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

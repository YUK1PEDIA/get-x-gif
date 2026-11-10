from __future__ import annotations

import os
import shutil
import subprocess
import urllib.error

from .errors import DownloadError
from .http import open_url

_CHUNK = 1 << 16


def ffmpeg_available() -> bool:
    return shutil.which('ffmpeg') is not None


def download_file(
    url: str, dest: str, timeout: float = 60.0, insecure: bool = False
) -> str:
    tmp = dest + '.part'
    try:
        with open_url(url, timeout=timeout, insecure=insecure) as resp, open(
            tmp, 'wb'
        ) as f:
            total = int(resp.headers.get('Content-Length') or 0)
            done = 0
            last_report = 0
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total and done - last_report >= (1 << 18):
                    pct = done * 100 // total
                    print(
                        f'\r    {pct:3d}% ({done / 1048576:.1f} MB)',
                        end='',
                        flush=True,
                    )
                    last_report = done
                elif not total and done - last_report >= (1 << 20):
                    print(
                        f'\r    {done / 1048576:.1f} MB', end='', flush=True
                    )
                    last_report = done
        print('\r' + ' ' * 40 + '\r', end='')
        os.replace(tmp, dest)
        return dest
    except urllib.error.HTTPError as e:
        raise DownloadError(f'下载失败：HTTP {e.code}') from e
    except urllib.error.URLError as e:
        raise DownloadError(f'下载失败：{e.reason}') from e
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def convert_mp4_to_gif(
    mp4_path: str,
    gif_path: str,
    max_width: int = 480,
    fps: int = 30,
    timeout: float = 300.0,
) -> str:
    """用 ffmpeg 两遍调色板（palettegen/paletteuse）把 MP4 转成真正的 .gif。

    - ``max_width``：宽度上限（像素），0 表示不缩放；小于该值的图不会被放大
    - ``fps``：帧率上限，0 表示保持原始帧率
    """
    if not ffmpeg_available():
        raise DownloadError(
            '未找到 ffmpeg，无法转换为 .gif。请先安装（macOS: brew install ffmpeg），'
            '或加 --mp4 直接保存 MP4。'
        )
    filters = []
    if max_width and max_width > 0:
        filters.append(f"scale=w='min({max_width},iw)':h=-1:flags=lanczos")
    if fps and fps > 0:
        filters.append(f'fps={fps}')
    vf = ','.join(filters) + ',' if filters else ''
    vf += 'split[a][b];[a]palettegen[p];[b][p]paletteuse'
    cmd = [
        'ffmpeg',
        '-hide_banner',
        '-loglevel',
        'error',
        '-y',
        '-i',
        mp4_path,
        '-filter_complex',
        f'[0:v]{vf}',
        gif_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        raise DownloadError(
            f'ffmpeg 转换失败：{e.stderr.strip() or e}'
        ) from e
    except subprocess.TimeoutExpired as e:
        raise DownloadError('ffmpeg 转换超时') from e
    return gif_path

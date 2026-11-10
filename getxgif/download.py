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


# 目标体积模式下依次尝试的 (宽度上限, 帧率上限) 阶梯
_SIZE_LADDER = [
    (480, 30),
    (400, 24),
    (360, 15),
    (320, 15),
    (320, 12),
    (240, 12),
    (240, 10),
    (200, 10),
]


def convert_mp4_to_gif_within(
    mp4_path: str,
    gif_path: str,
    max_size_mb: float,
    timeout: float = 300.0,
) -> tuple[str, int, int, bool]:
    """按目标体积（MB）自动选择宽度/帧率，尽量不超过目标。

    ``max_size_mb <= 0`` 表示不限制体积（按最佳画质 480px/30fps 转换）。
    先按最佳画质尝试，超限时沿阶梯逐步降低分辨率与帧率，直到体积达标；
    全部档位都超标时保留最小档位的产物。

    返回 ``(gif_path, 实际宽度, 实际fps, 是否达标)``。
    """
    if max_size_mb <= 0:
        convert_mp4_to_gif(mp4_path, gif_path, max_width=480, fps=30, timeout=timeout)
        return gif_path, 480, 30, True

    target = max_size_mb * 1024 * 1024
    # 临时文件名必须以 .gif 结尾，否则 ffmpeg 无法推断输出格式
    work = gif_path + '.tmp.gif'
    try:
        used_w, used_f = _SIZE_LADDER[-1]
        for w, f in _SIZE_LADDER:
            if os.path.exists(work):
                os.remove(work)
            convert_mp4_to_gif(
                mp4_path, work, max_width=w, fps=f, timeout=timeout
            )
            if os.path.getsize(work) <= target:
                os.replace(work, gif_path)
                return gif_path, w, f, True
            used_w, used_f = w, f
        # 全部档位仍超标：保留最小档位的产物
        os.replace(work, gif_path)
        return gif_path, used_w, used_f, False
    finally:
        if os.path.exists(work):
            os.remove(work)

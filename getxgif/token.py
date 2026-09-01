r"""X 博文 syndication 端点所需的 token 生成。

原理：X 的嵌入页面通过
  https://cdn.syndication.twimg.com/tweet-result?id=<博文ID>&token=<token>
返回博文的 JSON（无需登录、无 API key）。token 的计算方式为：

    ((Number(tweet_id) / 1e15) * Math.PI).toString(36).replace(/(0+|\.)/g, '')

实现参考了 yt-dlp 的 Twitter 提取器：
  https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/twitter.py
  https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/jsinterp.py
"""

from __future__ import annotations

import math

_ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyz.-'


def js_number_to_string(val: float, radix: int = 10) -> str:
    """复刻 JavaScript 的 ``Number.prototype.toString(radix)``

    参考 yt-dlp 的 ``jsinterp.js_number_to_string``（ECMA-262 #x9.8.1）
    本项目只使用 radix=36，该路径与浏览器行为一致
    """
    if math.isnan(val):
        return 'NaN'
    if val == 0:
        return '0'
    if math.isinf(val):
        return '-Infinity' if val < 0 else 'Infinity'

    # result 中元素含义：0-35 为进制数字/字母；-2 为 '.'；-1 为 '-'
    result: list[int] = []
    sign = val < 0
    val = abs(val)
    fraction, integer = math.modf(val)
    delta = max(math.nextafter(0.0, math.inf), math.ulp(val) / 2)

    if fraction >= delta:
        result.append(-2)  # '.'
    while fraction >= delta:
        delta *= radix
        fraction, digit = math.modf(fraction * radix)
        result.append(int(digit))
        # 需要进位时，向小数部分传播进位
        needs_rounding = fraction > 0.5 or (fraction == 0.5 and int(digit) & 1)
        if needs_rounding and fraction + delta > 1:
            for index in reversed(range(1, len(result))):
                if result[index] + 1 < radix:
                    result[index] += 1
                    break
                result.pop()
            else:
                integer += 1
            break

    integer, digit = divmod(int(integer), radix)
    result.insert(0, int(digit))
    while integer > 0:
        integer, digit = divmod(integer, radix)
        result.insert(0, int(digit))

    if sign:
        result.insert(0, -1)  # '-'

    return ''.join(_ALPHABET[d] for d in result)


def syndication_token(tweet_id: str) -> str:
    """生成 ``cdn.syndication.twimg.com/tweet-result`` 所需的 token"""
    # 与 JS 保持一致的 float64 运算：Number(tweet_id) / 1e15 * Math.PI
    value = (int(tweet_id) / 1e15) * math.pi
    return js_number_to_string(value, 36).replace('0', '').replace('.', '')

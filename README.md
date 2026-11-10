# get-X-gif

下载 **X（Twitter）博文中的 GIF 图**：传入博文链接，自动解析并下载其中的 GIF（普通视频也会自动转成 GIF）

X 网页端无法直接右键保存 GIF，官方 API 又要申请 key。本项目通过 X 官方的
**嵌入（syndication）接口**，无需登录、无需 API key，即可拿到博文 JSON，
从中提取 `animated_gif` / `video` 媒体并下载

## 特点

- 支持 `x.com` / `twitter.com`（含 `www`/`m`/`mobile` 前缀、`i/web/status`、
  `/photo/1`、`/video/1` 后缀、`?s=20` 参数）以及 `t.co` 短链（自动跟随重定向）
- syndication 接口失败时自动回退到 fxtwitter 社区接口
- 支持 GIF 和普通视频，默认统一转成 `.gif` 输出（需本机 ffmpeg）

## 说明：默认输出 .gif

X 的 GIF 本质是 MP4 视频，普通视频同样是 MP4，因此：

- 默认会用本机 **ffmpeg** 把下载的 MP4 转成真正的 `.gif` 文件（需先安装 ffmpeg）
- 想保留原始 MP4（体积小、画质无损），加 `--mp4`

安装 ffmpeg：

| 系统 | 命令 |
|------|------|
| macOS | `brew install ffmpeg` |
| Windows | `winget install Gyan.FFmpeg`，或到 [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) 下载 |

## 安装

前置要求：Python 3.9+

### macOS

```bash
cd get_x_gif
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

### Windows

在 PowerShell，依次执行：

```powershell
cd get_x_gif
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e .
```

安装完成后即可使用：

```powershell
get-x-gif "https://x.com/<用户名>/status/<博文ID>"
```

> 没有 `py` 命令时，把上面的 `py` 换成 `python`。

### 不安装，直接运行

在项目根目录运行：

```bash
# macOS / Linux
python3 -m getxgif <博文链接>

# Windows
py -m getxgif <博文链接>
```

### 卸载

```bash
python3 -m pip uninstall get-x-gif   # Windows: py -m pip uninstall get-x-gif
```

> 若运行时报证书相关错误，先执行 `python3 -m pip install certifi`
> （Windows：`py -m pip install certifi`）再重试；也可以给命令加 `--insecure`

## 使用示例

```bash
# 下载 GIF 并转成 .gif（默认保存到根目录的 output 下，需要 ffmpeg）
get-x-gif "https://x.com/<用户名>/status/<博文ID>"

# 保留原始 MP4（不转 GIF）
get-x-gif "https://x.com/<用户名>/status/<博文ID>" --mp4

# 指定输出目录
get-x-gif "https://twitter.com/<用户名>/status/<博文ID>" -o ~/Downloads

# 有多个 GIF/视频时，只下载第 2 个
get-x-gif "https://x.com/<用户名>/status/<博文ID>" -n 2

# example
get-x-gif "https://x.com/xcowboygeniusx/status/1771987199124214200"
```

### 参数

| 参数 | 说明 |
|------|------|
| `url` | X 博文链接（`x.com` / `twitter.com` / `t.co`） |
| `-o, --output PATH` | 输出文件或目录（默认项目根目录下的 `output/`，自动创建） |
| `-n, --index N` | 只下载第 N 个 GIF/视频（从 1 起） |
| `--mp4` | 保存原始 MP4（默认转成 .gif，需要 ffmpeg） |
| `--insecure` | 跳过 TLS 证书校验 |

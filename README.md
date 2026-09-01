# get-X-gif

下载 **X（Twitter）博文中的 GIF 图**：传入博文链接，自动解析并下载其中的 GIF

X 网页端无法直接右键保存 GIF，官方 API 又要申请 key。本项目通过 X 官方的
**嵌入（syndication）接口**，无需登录、无需 API key，即可拿到博文 JSON，
从中提取 `animated_gif` 媒体并下载

## 特点

- 支持 `x.com` / `twitter.com`（含 `www`/`m`/`mobile` 前缀、`i/web/status`、
  `/photo/1`、`/video/1` 后缀、`?s=20` 参数）以及 `t.co` 短链（自动跟随重定向）
- syndication 接口失败时自动回退到 fxtwitter 社区接口

## 说明：GIF 其实是 MP4

X 把 GIF 存储为 **MP4 视频**（H.264 编码），因此：

- 默认下载得到的是 `.mp4` 文件——体积小、画质无损，任何播放器都能播放
- 想要真正的 `.gif` 文件时加 `--gif`，会用本机 **ffmpeg** 转换（本地需安装 ffmpeg）

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
# 下载 GIF 保存为 MP4（默认保存到根目录的 output 下）
get-x-gif "https://x.com/<用户名>/status/<博文ID>"

# 指定输出目录
get-x-gif "https://twitter.com/<用户名>/status/<博文ID>" -o ~/Downloads

# 下载 GIF 保存为 GIF（需要本地安装 ffmpeg）
get-x-gif "https://x.com/<用户名>/status/<博文ID>" --gif

# 有多个 GIF 时，只下载第 2 个
get-x-gif "https://x.com/<用户名>/status/<博文ID>" -n 2

# example
get-x-gif "https://x.com/xcowboygeniusx/status/1771987199124214200" --gif
```

### 参数

| 参数 | 说明 |
|------|------|
| `url` | X 博文链接（`x.com` / `twitter.com` / `t.co`） |
| `-o, --output PATH` | 输出文件或目录（默认项目根目录下的 `output/`，自动创建） |
| `-n, --index N` | 只下载第 N 个 GIF（从 1 起） |
| `--gif` | 用 ffmpeg 转成的 GIF（默认保存 MP4） |
| `--insecure` | 跳过 TLS 证书校验 |

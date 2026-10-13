# wechat-article-parser

微信公众号文章解析器。传入一个公众号文章链接，自动抓取页面并提取公众号信息、文章元数据及正文的 Markdown 内容。

支持的文章类型：

- 标准富文本文章
- 转载式文章
- 纯文本文章
- 视频分享类文章
- 音频分享类文章
- 小红书风格图片轮播文章
- 全屏布局短文本文章

解析时优先读取页面全局的 `item_show_type`：`0` 对应图文、`5` 对应视频分享、`7` 对应音频分享、
`8` 对应图片轮播、`10` 对应文字消息，再通过 HTML 或脚本数据区分具体模板。
类型字段缺失、值未知或对应分支未提取到正文时，会按原有 HTML 特征匹配顺序兜底。

图文正文仅包含视频号视频卡片或微信视频 iframe 时，Markdown 返回“这是一篇纯视频内容。”。
正文只有付费预览占位标签时，Markdown 返回“这是一篇付费内容，正文需付费后查看。”，
并保留公开元数据；已有的可见预览正文仍正常提取。
图文中的公众号推荐卡片按原文顺序转换为 `**公众号名称**：简介`，每张卡片一段；
名称或简介缺失时，仅输出已有字段。
图文正文仅包含商品广告卡片（`mp-common-cpsad`）时，Markdown 返回“这是一篇商品推荐内容。”；
已有的文字和图片仍正常提取。关键元数据完整时占位结果也有效，不表示已获取商品详情。

## 安装

```bash
pip install wechat-article-parser
```

**本地开发安装：**

```bash
git clone https://github.com/huanjuedadehen/wechat-article-parser.git
cd wechat-article-parser
pip install -e ".[dev]"
```

依赖项（会自动安装）：

- Python >= 3.10
- httpx
- beautifulsoup4
- markdownify

## 使用方式

### 同步调用

```python
from wechat_article_parser import parse

result = parse("https://mp.weixin.qq.com/s/xxxxx")
print(result.article_title)
print(result.article_markdown)
```

### 异步调用

```python
from wechat_article_parser import parse_async

result = await parse_async("https://mp.weixin.qq.com/s/xxxxx")
print(result.article_title)
print(result.article_markdown)
```

### 可选参数

两个方法都支持以下可选参数：

- `timeout`：请求超时时间，单位秒，默认 15
- `user_agent`：自定义 User-Agent，不传则使用内置默认值
- `proxy`：HTTP/HTTPS 代理地址，不传则直连
- `include_raw_html`：是否在返回结果中带上原始 HTML 网页源代码，默认 `False`

```python
result = parse(
    "https://mp.weixin.qq.com/s/xxxxx",
    timeout=30,
    user_agent="MyBot/1.0",
    proxy="http://user:pass@127.0.0.1:7890",
    include_raw_html=True,
)
```

## 返回结构

`parse` 和 `parse_async` 均返回 `ArticleResult` 数据类，包含以下字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `mp_id_b64` | `str` | 公众号 ID（Base64 编码原始值） |
| `mp_id` | `int` | 公众号 ID（解码后的整数） |
| `mp_name` | `str` | 公众号名称 |
| `mp_alias` | `str` | 公众号别名 |
| `mp_user_name` | `str` | 公众号用户名（如 `aifaner383402` 或 `gh_9a1919baf888`），未获取到时为空字符串 |
| `mp_image` | `str` | 公众号头像链接 |
| `mp_description` | `str` | 公众号简介 |
| `mp_account_type` | `AccountType` | 账号类型：`AccountType.SUBSCRIPTION`（订阅号）/ `AccountType.SERVICE`（服务号）/ `AccountType.UNKNOWN`（未识别） |
| `article_id` | `str` | 文章 ID |
| `article_msg_id` | `int` | 文章所在的群发消息 ID |
| `article_idx` | `int` | 群发图文中的位置（从 1 开始） |
| `article_sn` | `str` | 文章签名（防伪校验） |
| `article_title` | `str` | 文章标题 |
| `article_cover_image` | `str` | 文章封面图链接 |
| `article_description` | `str` | 文章摘要 |
| `article_markdown` | `str` | 文章正文的 Markdown 内容；视频或音频分享没有文字附言时可为空 |
| `article_publish_time` | `int` | 发布时间（Unix 时间戳） |
| `article_display_type` | `ArticleDisplayType` | 文章展示类型：`article`、`video`、`audio`、`image`、`text` 或 `unknown` |
| `article_item_show_type` | `int \| None` | 微信页面中的原始展示类型：`0` 图文、`5` 视频、`7` 音频、`8` 图片轮播、`10` 文字；其他已提取的数值原样保留，缺失或无法解析时为 `None` |
| `raw_html` | `str` | 原始 HTML 网页源代码（仅在 `include_raw_html=True` 时填充，否则为空字符串） |
| `images` | `list[str]` | 文章中提取的所有图片链接 |
| `is_valid` | `bool` | 关键字段是否全部解析成功（属性） |

`is_valid` 为 `True` 的条件：`mp_id`、`mp_name`、`article_id`、`article_msg_id`、`article_idx`、`article_sn`、`article_title`、`article_publish_time` 均不为空/零，且 `article_markdown` 非空或 `article_display_type in ("video", "audio")`。视频和音频分享允许没有文字正文，仍须满足其他关键字段要求；有效性不表示已获取视频或音频文件。

付费受限页面返回提示且关键元数据完整时，`is_valid` 也为 `True`，这不表示已获取付费正文。

### 判断文章展示类型

`ArticleDisplayType` 是字符串枚举，既支持枚举比较，也支持语义字符串比较：

| 枚举 | 字符串值 | 含义 |
|---|---|---|
| `ArticleDisplayType.ARTICLE` | `article` | 图文，包括转载式 |
| `ArticleDisplayType.VIDEO` | `video` | 视频分享 |
| `ArticleDisplayType.AUDIO` | `audio` | 音频分享 |
| `ArticleDisplayType.IMAGE` | `image` | 图片轮播 |
| `ArticleDisplayType.TEXT` | `text` | 文字消息 |
| `ArticleDisplayType.UNKNOWN` | `unknown` | 页面类型缺失或未支持 |

```python
from wechat_article_parser import parse, ArticleDisplayType

result = parse("https://mp.weixin.qq.com/s/xxxxx")
if result.article_display_type == ArticleDisplayType.VIDEO:
    print("这是视频分享")

if result.article_display_type == "video":
    print("视频分享可以没有文字正文")

print(result.article_display_type)  # 例如 video
print(result.article_item_show_type)  # 例如 5
```

`article_display_type` 是返回结果中的数据字段，包含在 `dataclasses.asdict(result)` 中，JSON 序列化时输出语义字符串。
`article_item_show_type` 返回微信页面中 `item_show_type` 的原始数值，也包含在 `dataclasses.asdict(result)` 中；JSON 序列化时输出数字或 `null`。

### 判断账号类型

`AccountType` 继承自 `str` 枚举，既支持枚举比较，也支持与中文字符串直接比较：

```python
from wechat_article_parser import parse, AccountType

result = parse("https://mp.weixin.qq.com/s/xxxxx")

# 推荐：枚举比较（有类型提示与 IDE 补全）
if result.mp_account_type == AccountType.SERVICE:
    print("这是服务号")

# 也支持：字符串字面量比较
if result.mp_account_type == "服务号":
    print("这是服务号")

# 打印直接输出中文值
print(f"账号类型: {result.mp_account_type}")  # 账号类型: 订阅号
```

## 异常处理

### WeChatVerifyError

当请求频率过高或 IP 被限流时，微信会返回验证码页面而非文章内容。此时会抛出 `WeChatVerifyError`：

```python
from wechat_article_parser import parse, WeChatVerifyError

try:
    result = parse("https://mp.weixin.qq.com/s/xxxxx")
except WeChatVerifyError:
    print("触发了微信人机验证，请稍后重试或更换 IP")
```

### httpx.HTTPStatusError

当 HTTP 请求返回非 2xx 状态码时，会抛出 `httpx.HTTPStatusError`：

```python
import httpx
from wechat_article_parser import parse

try:
    result = parse("https://mp.weixin.qq.com/s/xxxxx")
except httpx.HTTPStatusError as e:
    print(f"请求失败: {e.response.status_code}")
```

### 解析不完整

缺少标题、发布时间等关键字段，或非视频/音频分享缺少正文时，解析结果的 `is_valid` 会返回 `False`。封面图、摘要等非必填字段为空不影响有效性。建议在业务逻辑中检查：

```python
result = parse("https://mp.weixin.qq.com/s/xxxxx")
if not result.is_valid:
    print("部分关键字段未能解析")
```

## 测试

安装开发依赖：

```bash
pip install -e ".[dev]"
```

### 运行全部测试

```bash
pytest tests/test_parser.py -v -s
```

### 只运行同步 / 异步测试

```bash
pytest tests/test_parser.py -v -s -k "sync"
pytest tests/test_parser.py -v -s -k "async"
```

### 测试单个链接 - 查看所有字段

```bash
pytest tests/test_parser.py::test_fetch_all -s --url "https://mp.weixin.qq.com/s/xxxxx"
```

### 测试单个链接 - 只看 Markdown 内容

```bash
pytest tests/test_parser.py::test_fetch_markdown -s --url "https://mp.weixin.qq.com/s/xxxxx"
```

### 测试单个链接 - 打印原始 HTML 网页源代码

```bash
pytest tests/test_parser.py::test_fetch_raw_html -s --url "https://mp.weixin.qq.com/s/xxxxx"
```

### 通过 HTTP 代理运行测试

所有测试命令都支持 `--proxy` 参数，传入后所有请求都会经由该代理；不传则直连。常用于 IP 被微信限流时换出口：

```bash
# 全量测试走代理
pytest tests/test_parser.py -v -s --proxy "http://127.0.0.1:7890"

# 测试单个链接走代理
pytest tests/test_parser.py::test_fetch_all -s \
  --url "https://mp.weixin.qq.com/s/xxxxx" \
  --proxy "http://user:pass@127.0.0.1:7890"
```

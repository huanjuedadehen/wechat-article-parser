# wechat-article-parser

微信公众号文章解析器。传入一个公众号文章链接，自动抓取页面并提取公众号信息、文章元数据及正文的 Markdown 内容。

支持的文章类型：

- 标准富文本文章
- 转载式文章
- 纯文本文章
- 视频分享类文章
- 小红书风格图片轮播文章
- 全屏布局短文本文章

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

```python
result = parse(
    "https://mp.weixin.qq.com/s/xxxxx",
    timeout=30,
    user_agent="MyBot/1.0",
    proxy="http://user:pass@127.0.0.1:7890",
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
| `article_markdown` | `str` | 文章正文的 Markdown 内容 |
| `article_publish_time` | `int` | 发布时间（Unix 时间戳） |
| `images` | `list[str]` | 文章中提取的所有图片链接 |
| `is_valid` | `bool` | 关键字段是否全部解析成功（属性） |

`is_valid` 为 `True` 的条件：`mp_id`、`mp_name`、`article_id`、`article_msg_id`、`article_idx`、`article_sn`、`article_title`、`article_markdown`、`article_publish_time` 均不为空/零。

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

部分文章类型可能无法提取所有字段（如某些文章没有封面图或摘要）。这种情况不会抛出异常，但 `result.is_valid` 会返回 `False`。建议在业务逻辑中检查：

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

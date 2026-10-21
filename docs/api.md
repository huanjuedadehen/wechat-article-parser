# API 参考

[返回 README](../README.md) · [正文转换规则](content-rules.md)

## 解析接口

以下接口和类型均可从 `wechat_article_parser` 顶层导入。

```python
from wechat_article_parser import ArticleResult


def parse(
    url: str,
    *,
    timeout: int = 15,
    user_agent: str | None = None,
    proxy: str | None = None,
    include_raw_html: bool = False,
) -> ArticleResult: ...

async def parse_async(
    url: str,
    *,
    timeout: int = 15,
    user_agent: str | None = None,
    proxy: str | None = None,
    include_raw_html: bool = False,
) -> ArticleResult: ...
```

两个接口使用相同的解析逻辑，均返回 `ArticleResult`；异步接口需要 `await`。
每次调用创建一个 HTTP 客户端，请求时跟随重定向，结束后关闭客户端。

| 参数 | 说明 |
|---|---|
| `url` | 微信公众号文章链接，支持短链接和长链接 |
| `timeout` | 传给 HTTP 客户端的超时时间，单位秒，默认 `15` |
| `user_agent` | 自定义 User-Agent，默认使用内置浏览器标识 |
| `proxy` | 显式指定代理地址，例如 `http://127.0.0.1:7890`；默认 `None` |
| `include_raw_html` | 默认 `False`；为 `True` 时填充 `result.raw_html` |

`url` 之后的参数必须以关键字传入。`proxy=None` 时不显式设置代理；HTTP 客户端仍使用默认环境配置。

```python
from wechat_article_parser import parse

result = parse(
    "https://mp.weixin.qq.com/s/xxxxx",  # 替换为实际文章链接
    timeout=30,
    user_agent="MyBot/1.0",
    proxy="http://127.0.0.1:7890",
    include_raw_html=True,
)
```

## 链接识别

同步和异步接口均支持短链接 `/s/<22位文章ID>`（ID 由英文字母、数字、`_` 或 `-` 组成）和长链接 `/s?__biz=...&mid=...&idx=...&sn=...&chksm=...`。
根据原始输入 URL 识别链接类型：协议须为 HTTP/HTTPS，域名须为 `mp.weixin.qq.com`，且不能包含 URL 用户名或密码。
长链接路径须为 `/s`，且 `__biz`、`mid`、`idx`、`sn`、`chksm` 五个查询参数必须都存在且有值，
空字符串或纯空白不算有效值；重复参数中的每个值也须非空白。额外查询参数和片段不影响识别。
未满足识别条件时，`article_url_type` 为 `unknown`，仍尝试解析页面，不额外抛出链接校验异常。

长链接返回的 `article_id` 为空，其他字段继续从页面提取。
只有识别为 `long` 时，`is_valid` 才允许缺少 `article_id`。

`ArticleURLType` 的成员为 `SHORT = "short"`、`LONG = "long"`、`UNKNOWN = "unknown"`。
支持枚举比较、字符串比较和 JSON 序列化。链接类型按原始输入判断，不按重定向后的地址判断。

## 返回结果

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
| `article_id` | `str` | 短链接中的文章 ID；长链接为空字符串 |
| `article_url_type` | `ArticleURLType` | 输入链接类型：`short`、`long` 或 `unknown`（默认）；可从包顶层导入枚举，支持字符串比较和 JSON 序列化 |
| `article_msg_id` | `int` | 文章所在的群发消息 ID |
| `article_idx` | `int` | 群发图文中的位置（从 1 开始） |
| `article_sn` | `str` | 文章签名（防伪校验） |
| `article_title` | `str` | 文章标题 |
| `article_cover_image` | `str` | 文章封面图链接 |
| `article_description` | `str` | 文章摘要 |
| `article_markdown` | `str` | 文章正文的 Markdown 内容；视频或音频分享没有文字附言时可为空 |
| `article_publish_time` | `int` | 发布时间（Unix 时间戳） |
| `article_is_paid` | `bool` | 是否检测到当前文章的付费标记，默认 `False`；不表示是否已获取付费全文 |
| `article_display_type` | `ArticleDisplayType` | 文章展示类型：`article`、`video`、`audio`、`image`、`text` 或 `unknown` |
| `article_item_show_type` | `int \| None` | 微信页面中的原始展示类型：`0` 图文、`5` 视频、`7` 音频、`8` 图片轮播、`10` 文字；其他已提取的数值原样保留，缺失或无法解析时为 `None` |
| `raw_html` | `str` | 原始 HTML 网页源代码（仅在 `include_raw_html=True` 时填充，否则为空字符串） |
| `images` | `list[str]` | 最终保留的正文图片链接，按顺序去重；不包含被省略的动画帧、小程序封面和头像、红包封面预览图 |
| `is_valid` | `bool` | 关键字段是否全部解析成功（属性） |

`is_valid` 为 `True` 的条件：`mp_id`、`mp_name`、`article_msg_id`、`article_idx`、`article_sn`、`article_title`、`article_publish_time` 均不为空/零，且 `article_markdown` 非空或 `article_display_type in ("video", "audio")`。
此外，`article_url_type == "long"` 时允许 `article_id` 为空；短链接和未识别链接仍要求 `article_id` 非空。
视频和音频分享允许没有文字正文，仍须满足其他关键字段要求；有效性不表示已获取视频或音频文件。

付费受限页面返回提示且关键元数据完整时，`is_valid` 也为 `True`，这不表示已获取付费正文。

未提取到的字符串默认为 `""`，整数默认为 `0`，图片列表默认为空列表；
展示类型、链接类型和账号类型默认为各自的 `UNKNOWN`。
`article_is_paid` 默认为 `False`，`article_item_show_type` 默认为 `None`。

## JSON 序列化

```python
import json
from dataclasses import asdict

from wechat_article_parser import parse

result = parse("https://mp.weixin.qq.com/s/xxxxx")
data = asdict(result)
data["is_valid"] = result.is_valid
print(json.dumps(data, ensure_ascii=False, indent=2))
```

`is_valid` 是计算属性，**不包含在 `asdict(result)` 中**，需要时自行加入。
三个枚举均继承自 `str`，JSON 中直接输出字符串值。

## 判断是否为付费文章

```python
from wechat_article_parser import parse

result = parse("https://mp.weixin.qq.com/s/xxxxx")
print(result.article_is_paid)  # True：识别为付费文章
```

未检测到付费标记时返回 `False`；有可见预览或可访问正文的付费文章仍返回 `True`。
该字段包含在 `dataclasses.asdict(result)` 中，JSON 序列化为布尔值。
标记来源及预览处理方式见[正文转换规则](content-rules.md#微信组件与占位提示)。

## 判断文章展示类型

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

## 判断账号类型

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

`AccountType.UNKNOWN` 的字符串值为空字符串 `""`。

## 异常与不完整结果

| 情况 | 行为 |
|---|---|
| 检测到微信验证码或人机验证页面 | 抛出 `WeChatVerifyError` |
| HTTP 状态异常 | `response.raise_for_status()` 抛出的 `httpx.HTTPStatusError` 直接向外传播 |
| 请求超时、连接失败等网络问题 | `httpx.RequestError` 及其子类直接向外传播，例如 `httpx.TimeoutException` |
| 页面可获取，但关键内容未提取完整 | 返回 `ArticleResult`，由调用方检查 `is_valid` |

```python
import httpx

from wechat_article_parser import WeChatVerifyError, parse

try:
    result = parse("https://mp.weixin.qq.com/s/xxxxx")
except WeChatVerifyError:
    print("微信要求人机验证，请稍后重试")
except httpx.HTTPStatusError as exc:
    print(f"HTTP 请求失败：{exc.response.status_code}")
except httpx.RequestError as exc:
    print(f"网络请求失败：{exc}")
else:
    if result.is_valid:
        print(result.article_markdown)
    else:
        print("部分关键字段未能解析，请检查返回结果")
```

接口不自动重试。封面、摘要等非必填字段为空不影响有效性；
`is_valid` 不用于判断付费全文、视频文件或组件内部内容是否已获取。

# wechat-article-parser

微信公众号文章解析器。传入文章链接，提取公众号信息、文章元数据和 Markdown 正文，支持同步与异步调用。

## 功能

- 支持微信文章短链接和长链接。
- 支持标准图文、转载式文章、纯文本、视频与音频分享、图片轮播及全屏布局短文本。
- 提取标题、作者公众号、摘要、封面、发布时间、付费标记等信息，返回结构化数据。
- 将正文转换为 Markdown，提取正文图片链接，支持 SVG 内嵌图片和文字。
- 将投票、公众号推荐、小程序、红包封面等组件转换为可读文字或查看提示。
- 支持请求超时、自定义 User-Agent、代理和按需返回原始 HTML。

## 安装

需要 **Python 3.10+**。

```bash
python -m pip install wechat-article-parser
```

`httpx`、`beautifulsoup4` 和 `markdownify` 会随包自动安装。

## 快速开始

将以下示例中的 URL 替换为实际文章链接。

### 同步调用

```python
from wechat_article_parser import parse

result = parse("https://mp.weixin.qq.com/s/xxxxx")

if result.is_valid:
    print(result.article_title)
    print(result.mp_name)
    print(result.article_markdown)
    print(result.images)
else:
    print("部分关键字段未能解析，请检查返回结果")
```

### 异步调用

```python
import asyncio

from wechat_article_parser import parse_async


async def main():
    result = await parse_async("https://mp.weixin.qq.com/s/xxxxx")
    if result.is_valid:
        print(result.article_title)
        print(result.article_markdown)
    else:
        print("部分关键字段未能解析，请检查返回结果")


asyncio.run(main())
```

### 请求选项

两个接口均支持以下关键字参数：

```python
from wechat_article_parser import parse

result = parse(
    "https://mp.weixin.qq.com/s/xxxxx",
    timeout=30,                    # 默认 15 秒
    user_agent="MyBot/1.0",         # 默认使用内置 User-Agent
    proxy="http://127.0.0.1:7890",  # 可选，显式指定代理
    include_raw_html=True,          # 默认 False
)
print(result.raw_html)
```

## 返回结果

两个接口均返回 `ArticleResult` 数据类，常用字段如下：

| 字段 | 说明 |
|---|---|
| `article_title` / `article_description` | 文章标题 / 摘要 |
| `article_markdown` | Markdown 正文 |
| `article_publish_time` | 发布时间，Unix 时间戳 |
| `article_cover_image` / `images` | 封面链接 / 最终保留的正文图片链接列表 |
| `mp_name` / `mp_user_name` | 公众号名称 / 用户名 |
| `article_display_type` | `article`、`video`、`audio`、`image`、`text` 或 `unknown` |
| `article_url_type` | 输入链接类型：`short`、`long` 或 `unknown` |
| `article_is_paid` | 是否检测到付费标记 |
| `is_valid` | 关键字段是否完整的计算属性 |

完整字段、枚举、长链接识别条件及 JSON 序列化示例见 [API 参考](docs/api.md)。

## 使用边界与错误处理

- 基于页面 HTML 和已知脚本数据提取，不执行 JavaScript，不还原交互与视觉布局。图片返回链接，不下载媒体文件。
- 明确识别的 SVG 快速逐帧动画仅保留首帧；轮播及无法确认的帧序列保留可提取图片。具体规则见[正文转换规则](docs/content-rules.md)。
- 视频、音频分享可以没有文字附言。付费预览及部分卡片可能只返回文字提示；`is_valid=True` 不代表已获取付费全文、媒体文件或小程序内部内容。
- 页面结构变化或内容不可访问时，可能返回不完整结果。调用方应检查 `is_valid`；长链接的 `article_id` 为空属于正常情况。
- 检测到微信人机验证时抛出 `WeChatVerifyError`；HTTP 状态异常和网络错误通过 `httpx` 异常向外传播。接口不自动重试，处理示例见 [API 参考](docs/api.md#异常与不完整结果)。

## 文档

- [API 参考](docs/api.md)：参数、全部返回字段、枚举、有效性判断和异常处理。
- [正文转换规则](docs/content-rules.md)：图片与动画、微信组件、页面模板与回退规则。
- [开发指南](docs/development.md)：本地安装、项目结构、离线测试和真实链接调试。
- [版本记录](https://github.com/huanjuedadehen/wechat-article-parser/releases)：各版本的发布说明。

## 参与贡献

欢迎通过 [Issues](https://github.com/huanjuedadehen/wechat-article-parser/issues) 报告问题，或提交 Pull Request。
请附上可复现的文章链接、版本信息和预期结果；修改解析行为时补充离线回归用例。
开发环境和测试方法见[开发指南](docs/development.md)。

## 许可证

本项目使用 [MIT License](LICENSE)。

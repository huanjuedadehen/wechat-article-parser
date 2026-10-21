# 开发指南

[返回 README](../README.md) · [正文转换规则](content-rules.md)

## 本地安装

需要 Python 3.10 或更高版本。建议使用虚拟环境：

```bash
git clone https://github.com/huanjuedadehen/wechat-article-parser.git
cd wechat-article-parser
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Windows PowerShell 下使用 `.venv\Scripts\Activate.ps1` 激活虚拟环境。
构建系统为 hatchling，版本号、依赖及 pytest 配置集中在 `pyproject.toml`。

## 项目结构

```text
src/wechat_article_parser/
├── __init__.py  # 公开接口和类型导出
├── models.py    # ArticleResult、枚举和异常
└── parser.py    # HTTP 抓取、页面提取与 Markdown 转换
tests/          # 离线回归用例与真实链接集成测试
docs/           # API、转换规则和开发说明
```

`parse()` 和 `parse_async()` 共用 `_parse_html()`。
修改模板或组件行为前，可先阅读[正文转换规则](content-rules.md)；公开字段约定见 [API 参考](api.md)。

## 离线回归测试

日常修改优先运行离线测试，不请求微信：

```bash
python -m pytest tests --ignore=tests/test_parser.py -q
```

功能用例分布在 `tests/test_*_content.py`、`test_markdown.py`、`test_type_routing.py`、
`test_models.py`、`test_user_name.py` 等文件中。异步测试使用 `@pytest.mark.asyncio`，
项目已配置 `asyncio_mode = "auto"`。

## 真实链接集成测试

以下命令会访问微信，请按需要运行：

```bash
# 全部测试：包含离线回归与真实链接请求
python -m pytest tests -v

# 仅运行真实链接测试
python -m pytest tests/test_parser.py -v -s

# 仅运行同步测试
python -m pytest tests/test_parser.py -v -s -k "test_parse_sync"

# 仅运行异步测试
python -m pytest tests/test_parser.py -v -s -k "test_parse_async"
```

频繁请求可能触发验证码或 IP 限流。参数化同步/异步测试遇到 `WeChatVerifyError` 时会跳过，
**跳过不代表解析通过**。其他网络错误仍会导致测试失败。

## 调试单个链接

将示例 URL 替换为实际文章链接：

```bash
# 打印所有字段
python -m pytest tests/test_parser.py::test_fetch_all -s --url "https://mp.weixin.qq.com/s/xxxxx"

# 打印 Markdown
python -m pytest tests/test_parser.py::test_fetch_markdown -s --url "https://mp.weixin.qq.com/s/xxxxx"

# 打印原始 HTML
python -m pytest tests/test_parser.py::test_fetch_raw_html -s --url "https://mp.weixin.qq.com/s/xxxxx"

# 通过代理请求
python -m pytest tests/test_parser.py::test_fetch_all -s \
  --url "https://mp.weixin.qq.com/s/xxxxx" \
  --proxy "http://127.0.0.1:7890"
```

`--url` 只供三个 `test_fetch_*` 调试入口使用，不替换参数化集成测试中的链接列表。
未传 `--url` 时，这三个入口会跳过；遇到验证码时则直接抛出异常。
`--proxy` 供真实链接测试使用。

`test_fetch_all` 和 `test_fetch_markdown` 只打印结果，不断言解析有效；
`test_fetch_raw_html` 只检查原始 HTML 非空。验证修复时应同时检查关键字段、`is_valid` 和实际正文内容。

## 提交问题与贡献代码

- 通过 [Issues](https://github.com/huanjuedadehen/wechat-article-parser/issues) 报告问题，提供包版本、Python 版本、可复现的文章链接、预期结果和实际结果或异常。
- 分享 HTML、日志或代理配置前，移除凭据及不适合公开的信息。
- 修改解析行为时添加对应的离线 HTML 或脚本样例，断言正文、图片或元数据的预期结果，再按需要验证真实链接。
- 保持同步和异步接口行为一致；修改公开接口或转换规则时同步更新文档。
- 注释与文档使用中文。提交 PR 前运行离线回归测试，并在 PR 中说明改动目的与验证方式。

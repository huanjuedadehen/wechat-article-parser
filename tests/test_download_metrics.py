"""通过内存传输验证四个公开接口的下载大小和分段计时。"""

from dataclasses import asdict
import gzip
import inspect

import httpx
import pytest

from wechat_article_parser import parse, parse_account, parse_account_async, parse_async, parser


_URL = "https://mp.weixin.qq.com/s/ncPoZnxKdvDRLM_s4DBgmA"
_HTML = """
<meta property="og:title" content="标题">
<div class="rich_media_content">正文</div>
<script type="text/javascript">
var biz = "MTIz";
var mid = "10";
var idx = "1";
window.__allowLoadResFromMp = true;
var hd_head_img = "https://example.com/avatar";
var nickname = htmlDecode("测试公众号");
var oriCreateTime = '1700000000';
</script>
"""


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", [parse, parse_async, parse_account, parse_account_async])
@pytest.mark.parametrize("encoding", ["identity", "gzip", "empty"])
async def test_public_metrics(entry, encoding, monkeypatch) -> None:
    html = "" if encoding == "empty" else _HTML
    body = html.encode("utf-8")
    if encoding == "gzip":
        body = gzip.compress(body)

    # 用可控时钟区分重定向、下载、文本解码和解析，避免依赖实际机器速度。
    now = 0.0
    monkeypatch.setattr(parser, "perf_counter", lambda: now)

    class Response(httpx.Response):
        @property
        def text(self):
            nonlocal now
            now += 0.25
            return super().text

    def respond(request):
        nonlocal now
        if str(request.url) == _URL:
            now += 1.0
            return httpx.Response(302, headers={"location": "/final"}, stream=httpx.ByteStream(b"redirect"))
        now += 2.0
        headers = {"content-encoding": "gzip"} if encoding == "gzip" else {}
        return Response(200, headers=headers, stream=httpx.ByteStream(body))

    client_name = "AsyncClient" if inspect.iscoroutinefunction(entry) else "Client"
    client = getattr(httpx, client_name)
    monkeypatch.setattr(parser.httpx, client_name, lambda **kw: client(
        transport=httpx.MockTransport(respond), **kw,
    ))

    full_article = entry in (parse, parse_async)
    parser_name = "_parse_html" if full_article else "_parse_account_html"
    original = getattr(parser, parser_name)

    def timed_parse(url, text):
        nonlocal now
        assert text == html
        now += 0.5
        return original(url, text)

    monkeypatch.setattr(parser, parser_name, timed_parse)
    keep_raw_html = full_article and encoding == "identity"
    options = {"include_raw_html": True} if keep_raw_html else {}
    result = entry(_URL, **options)
    if inspect.isawaitable(result):
        result = await result

    assert result.is_valid is bool(html)  # 有效页面和空页面都应返回本次实测值。
    data = asdict(result)
    assert data["html_download_bytes"] == len(body)
    assert data["html_download_seconds"] == 3.25
    assert data["parse_seconds"] == 0.5
    if full_article:
        assert result.raw_html == (html if keep_raw_html else "")

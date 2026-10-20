"""长短链接识别及有效性判断的离线回归测试。"""

from dataclasses import replace
from urllib.parse import urlencode

import httpx
import pytest

from wechat_article_parser import ArticleURLType, parser


_SHORT_URL = "https://mp.weixin.qq.com/s/ncPoZnxKdvDRLM_s4DBgmA"
_PARAMS = {
    "__biz": "MjY2NzgwMjU0MA==",
    "mid": "2650331950",
    "idx": "3",
    "sn": "59630a9449c484f555c71978ee521cd8",
    "chksm": "ae4b5d1c0343c5bf3af413da074abb54a3d56268937ba1825fa518c6ba4b1c96c34675d15d9e",
}
_LONG_URL = "https://mp.weixin.qq.com/s?" + urlencode(_PARAMS)
_HTML = """
<meta property="og:title" content="长链接测试文章">
<div class="rich_media_content"><p>正文</p></div>
<script type="text/javascript">
var item_show_type = "0";
var hd_head_img = "https://example.com/avatar";
var nickname = htmlDecode("测试公众号");
var oriCreateTime = '1791884914';
window.__allowLoadResFromMp = true;
var biz = "MjY2NzgwMjU0MA==";
var mid = "2650331950";
var idx = "3";
var sn = "59630a9449c484f555c71978ee521cd8";
</script>
"""


@pytest.mark.parametrize("scheme", ["http", "https"])
@pytest.mark.parametrize("suffix", ["", "&scene=21#wechat_redirect"])
def test_long_url_parses_without_article_id(scheme: str, suffix: str) -> None:
    result = parser._parse_html(_LONG_URL.replace("https:", scheme + ":") + suffix, _HTML)

    assert result.article_url_type is ArticleURLType.LONG
    assert result.article_id == ""
    assert result.mp_id == 2667802540
    assert result.article_msg_id == 2650331950
    assert result.article_idx == 3
    assert result.article_sn == _PARAMS["sn"]
    assert result.article_markdown == "正文"
    assert result.is_valid


@pytest.mark.parametrize("key", _PARAMS)
@pytest.mark.parametrize("value", [None, "", " \t\n"])
def test_long_url_requires_each_parameter_with_value(key: str, value: str | None) -> None:
    params = _PARAMS.copy()
    if value is None:
        del params[key]
    else:
        params[key] = value
    result = parser._parse_html("https://mp.weixin.qq.com/s?" + urlencode(params), _HTML)

    assert result.article_url_type is ArticleURLType.UNKNOWN
    assert result.article_id == ""
    assert not result.is_valid


@pytest.mark.parametrize("key", _PARAMS)
def test_duplicate_blank_parameter_does_not_pass_validation(key: str) -> None:
    result = parser._parse_html(_LONG_URL + "&" + key + "=", _HTML)
    assert result.article_url_type is ArticleURLType.UNKNOWN
    assert not result.is_valid


@pytest.mark.parametrize(
    "base",
    [
        "https://example.com/s",
        "https://mp.weixin.qq.com.example.com/s",
        "https://mp.weixin.qq.com@evil.example/s",
        "https://user@mp.weixin.qq.com/s",
        "ftp://mp.weixin.qq.com/s",
        "//mp.weixin.qq.com/s",
        "https://mp.weixin.qq.com/s/",
        "https://mp.weixin.qq.com/other",
        "https://[invalid/s",
    ],
)
def test_unrecognized_url_cannot_skip_article_id(base: str) -> None:
    result = parser._parse_html(base + "?" + urlencode(_PARAMS), _HTML)
    assert result.article_url_type is ArticleURLType.UNKNOWN
    assert not result.is_valid


def test_required_parameters_in_fragment_do_not_count() -> None:
    result = parser._parse_html("https://mp.weixin.qq.com/s#" + urlencode(_PARAMS), _HTML)
    assert result.article_url_type is ArticleURLType.UNKNOWN
    assert not result.is_valid


@pytest.mark.parametrize("suffix", ["", "?scene=21#wechat_redirect", "?" + urlencode(_PARAMS)])
def test_short_url_still_requires_article_id(suffix: str) -> None:
    result = parser._parse_html(_SHORT_URL + suffix, _HTML)
    assert result.article_url_type is ArticleURLType.SHORT
    assert result.article_id == "ncPoZnxKdvDRLM_s4DBgmA"
    assert result.is_valid
    assert not replace(result, article_id="").is_valid


def test_query_parameters_do_not_replace_missing_page_metadata() -> None:
    result = parser._parse_html(_LONG_URL, '<div class="rich_media_content">正文</div>')
    assert result.article_url_type is ArticleURLType.LONG
    assert not result.is_valid


@pytest.fixture
def mock_article_http(monkeypatch):
    # 重定向到短链接后仍根据原始输入链接识别类型。
    def respond(request):
        if request.url.path == "/s":
            return httpx.Response(302, headers={"Location": _SHORT_URL})
        return httpx.Response(200, text=_HTML)

    transport = httpx.MockTransport(respond)
    client, async_client = httpx.Client, httpx.AsyncClient
    monkeypatch.setattr(
        parser.httpx, "Client", lambda **kwargs: client(transport=transport, **kwargs),
    )
    monkeypatch.setattr(
        parser.httpx, "AsyncClient", lambda **kwargs: async_client(transport=transport, **kwargs),
    )


def test_sync_public_entry_accepts_long_url(mock_article_http) -> None:
    result = parser.parse(_LONG_URL, include_raw_html=True)
    assert result.article_url_type is ArticleURLType.LONG
    assert result.article_id == ""
    assert result.is_valid
    assert result.raw_html == _HTML


@pytest.mark.asyncio
async def test_async_public_entry_accepts_long_url(mock_article_http) -> None:
    result = await parser.parse_async(_LONG_URL, include_raw_html=True)
    assert result.article_url_type is ArticleURLType.LONG
    assert result.article_id == ""
    assert result.is_valid
    assert result.raw_html == _HTML

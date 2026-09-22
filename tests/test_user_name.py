"""当前公众号 user_name 的位置规则及公开返回接口回归测试。"""

from dataclasses import asdict
import json

import httpx
import pytest

from wechat_article_parser import ArticleResult, parser


_URL = "https://mp.weixin.qq.com/s/tBqB3134QzILypNVUW1fdw"
# 精简自参考页面的文章元数据脚本，保留字段上下文。
_METADATA = """
var nickname = htmlDecode("爱范儿");
var appmsg_type = "9";
var ct = "1784779200";
var user_name = "aifaner383402";
var fakeid = "";
"""
_DECOYS = """
var ad = {biz_info: {user_name: 'gh_1e80bb81a1d2'}};
window.cgiDataNew = {ad: {user_name: 'nested-ad-account'}};
(function () { var user_name = 'local-account'; })();
function report() { var user_name = 'another-local-account'; }
var example = "var user_name = 'string-account';";
var template = `var user_name = 'template-account';`;
// var user_name = 'comment-account';
/* var user_name = 'block-comment-account'; */
var original_user_name = 'reference-account';
var info = {userName: window.user_name};
"""


def _html(*scripts: str, body: str = "") -> str:
    return body + "".join(
        f'<script type="text/javascript">{script}</script>' for script in scripts
    )


@pytest.mark.parametrize("body", ["", '<div class="rich_media_content">正文</div>'])
def test_user_name_comes_from_global_metadata(body: str) -> None:
    result = parser._parse_html(_URL, _html(_DECOYS, _METADATA, _DECOYS, body=body))

    assert result.mp_user_name == "aifaner383402"
    assert json.loads(json.dumps(asdict(result)))["mp_user_name"] == "aifaner383402"


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        ("var user_name = 'gh_another-account';", "gh_another-account"),
        ('var\nuser_name /* comment */ = "other_account";', "other_account"),
        (r'var user_name = "gh_\x61bc";', "gh_abc"),
        ("", ""),
        ("var user_name = '';", ""),
        ("var user_name = null;", ""),
        ("var user_name = another_variable;", ""),
        ("var user_name = 'prefix' + suffix;", ""),
    ],
)
def test_user_name_is_dynamic_and_missing_values_are_empty(
    declaration: str, expected: str,
) -> None:
    result = parser._parse_html(_URL, _html(_DECOYS, declaration))
    assert result.mp_user_name == expected


def test_script_without_type_attribute() -> None:
    result = parser._parse_html(_URL, f"<script>{_METADATA}</script>")
    assert result.mp_user_name == "aifaner383402"


def test_default_user_name() -> None:
    assert ArticleResult().mp_user_name == ""


@pytest.mark.parametrize("key", ["user_name", "'user_name'", '"user_name"'])
@pytest.mark.parametrize("body", ["", '<div class="rich_media_content">正文</div>'])
def test_cgi_direct_user_name_fallback(key: str, body: str) -> None:
    data = (
        "(function () { window.cgiDataNew = {"
        "base_resp: {ret: '0' * 1},"
        "ad: {user_name: 'wrong-ad'},"
        "references: [{user_name: 'wrong-reference'}],"
        f"{key}: 'gh_9a1919baf888'"
        "}; })();"
    )
    result = parser._parse_html(_URL, _html(_DECOYS, data, body=body))
    assert result.mp_user_name == "gh_9a1919baf888"


def test_global_metadata_has_priority_over_cgi_fallback() -> None:
    data = "window.cgiDataNew = {user_name: 'cgi-account'};"
    result = parser._parse_html(_URL, _html(data, _METADATA))
    assert result.mp_user_name == "aifaner383402"


@pytest.mark.parametrize(
    "data",
    [
        "window.cgiDataNew = {user_name: ''};",
        "window.cgiDataNew = {user_name: 'prefix' + suffix};",
        "other.window.cgiDataNew = {user_name: 'wrong'};",
        "var text = \"window.cgiDataNew = {user_name: 'wrong'};\";",
        "// window.cgiDataNew = {user_name: 'wrong'};",
        "/* window.cgiDataNew = {user_name: 'wrong'}; */",
    ],
)
def test_cgi_fallback_ignores_decoys_and_nonliteral_values(data: str) -> None:
    result = parser._parse_html(_URL, _html(_DECOYS, data))
    assert result.mp_user_name == ""


@pytest.fixture
def mock_article_http(monkeypatch):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text=_html(_DECOYS, _METADATA))
    )
    client = httpx.Client
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        parser.httpx, "Client", lambda **kwargs: client(transport=transport, **kwargs),
    )
    monkeypatch.setattr(
        parser.httpx, "AsyncClient", lambda **kwargs: async_client(transport=transport, **kwargs),
    )


def test_sync_parse_returns_user_name(mock_article_http) -> None:
    assert parser.parse(_URL).mp_user_name == "aifaner383402"


@pytest.mark.asyncio
async def test_async_parse_returns_user_name(mock_article_http) -> None:
    result = await parser.parse_async(_URL)
    assert result.mp_user_name == "aifaner383402"

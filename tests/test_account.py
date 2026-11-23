"""仅提取发布公众号资料的离线回归测试。"""

import asyncio
from dataclasses import asdict

import httpx
import pytest

from wechat_article_parser import (
    AccountResult, AccountType, WeChatVerifyError, parse_account, parse_account_async, parser,
)


_URL = "https://mp.weixin.qq.com/s/ncPoZnxKdvDRLM_s4DBgmA"
_RICH = """
<script type="text/javascript">
var biz = "" || "MTIz";
var mid = "无效的文章字段";
window.__allowLoadResFromMp = true;
</script>
<script>
var hd_head_img = "https://example.com/avatar";
var nickname = htmlDecode("图文账号");
var profile_signature = "简介";
var account = {alias: 'alias', new_service_type: '2'};
var user_name = "gh_publisher";
</script>
"""
_SHARE = """
<script type="application/javascript">
window.__initCgiDataConfig = function(d) {
    return {
        biz: d.biz ? d.biz : 'NDU2',
        nick_name: d.nick_name ? d.nick_name : '分享账号',
        hd_head_img: d.hd_head_img ? d.hd_head_img : 'https://example.com/share',
        mid: d.mid ? d.mid : '无效的文章字段'
    };
};
window.alias = "share_alias";
window.cgiDataNew = {
    card: {user_name: 'gh_card'}, user_name: 'gh_share', new_service_type: '0'
};
</script>
"""


def test_rich_account_skips_article_fields_and_body(monkeypatch) -> None:
    def unexpected(*args, **kwargs):
        pytest.fail("仅获取公众号资料时调用了文章提取逻辑")

    for name in ("_parse_html", "_extract_meta", "_extract_item_show_type", "_extract_is_paid",
                 "_extract_rich_text_meta", "_extract_swiper_meta", "_try_content_branch"):
        monkeypatch.setattr(parser, name, unexpected)
    body = '<div class="rich_media_content"><mp-common-profile data-nickname="推荐账号"/></div>'
    result = parser._parse_account_html(_URL, body + _RICH)
    assert result.is_valid
    assert asdict(result) == {
        "mp_id_b64": "MTIz", "mp_id": 123, "mp_name": "图文账号", "mp_alias": "alias",
        "mp_image": "https://example.com/avatar", "mp_description": "简介",
        "mp_account_type": AccountType.SERVICE, "mp_user_name": "gh_publisher",
        "html_download_bytes": 0, "html_download_seconds": 0.0, "parse_seconds": 0.0,
    }


def test_share_account_without_article_or_layout() -> None:
    result = parser._parse_account_html(_URL, _SHARE)
    assert result.is_valid
    assert result == AccountResult(
        mp_id_b64="NDU2", mp_id=456, mp_name="分享账号", mp_alias="share_alias",
        mp_image="https://example.com/share", mp_account_type=AccountType.SUBSCRIPTION,
        mp_user_name="gh_share",
    )


@pytest.mark.parametrize("html", [_SHARE + _RICH, _RICH + _SHARE])
def test_rich_account_metadata_has_priority(html: str) -> None:
    result = parser._parse_account_html(_URL, html)
    assert result.mp_id == 123 and result.mp_name == "图文账号"
    assert result.mp_user_name == "gh_publisher"


def test_missing_or_incomplete_account() -> None:
    page = '<meta property="og:title" content="文章标题"><mp-common-profile data-nickname="推荐"/>'
    assert parser._parse_account_html(_URL, page) == AccountResult()
    partial = parser._parse_account_html(_URL, _RICH.replace("MTIz", "无效"))
    assert partial.mp_id_b64 == "无效" and partial.mp_id == 0
    assert partial.mp_name == "图文账号"
    assert not partial.is_valid


@pytest.fixture(params=["sync", "async"])
def fetch_account(request, monkeypatch):
    # 用真实 HTTP 客户端和内存传输测试选项、响应解码、重定向及异常。
    asynchronous = request.param == "async"
    client_name = "AsyncClient" if asynchronous else "Client"
    client = getattr(httpx, client_name)

    def fetch(respond):
        def make_client(**kwargs):
            assert kwargs.pop("proxy") == "http://proxy.test"
            return client(transport=httpx.MockTransport(respond), **kwargs)

        monkeypatch.setattr(parser.httpx, client_name, make_client)
        options = dict(timeout=7, user_agent="account-test", proxy="http://proxy.test")
        if asynchronous:
            return asyncio.run(parse_account_async(_URL, **options))
        return parse_account(_URL, **options)

    return fetch


def test_public_account_entry(fetch_account) -> None:
    def respond(request):
        assert request.headers["user-agent"] == "account-test"
        assert request.extensions["timeout"]["read"] == 7
        if str(request.url) == _URL:
            return httpx.Response(302, headers={"Location": "/redirected"})
        assert request.url.path == "/redirected"
        return httpx.Response(200, text=_RICH)

    result = fetch_account(respond)
    assert isinstance(result, AccountResult)
    assert result.is_valid and result.mp_name == "图文账号"


@pytest.mark.parametrize(("status", "body", "error"), [
    (200, '<script src="secitptpage/template/verify.js"></script>', WeChatVerifyError),
    (200, "register_code", WeChatVerifyError),
    (403, "", httpx.HTTPStatusError),
])
def test_public_account_errors(fetch_account, status, body, error) -> None:
    with pytest.raises(error):
        fetch_account(lambda request: httpx.Response(status, text=body))

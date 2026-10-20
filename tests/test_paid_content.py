"""付费受限正文的提示、元数据和预览内容回归测试。"""

import pytest

from wechat_article_parser import ArticleDisplayType
from wechat_article_parser.parser import _parse_html


_URL = "https://mp.weixin.qq.com/s/n2q09-I95zwggfbXKAmbuQ"
_NOTICE = "这是一篇付费内容，正文需付费后查看。"
_FILTER = (
    '<p class="js_pay_preview_filter" style="height: 0; overflow: hidden;">'
    '<mp-pay-preview-filter></mp-pay-preview-filter></p>'
)
_METADATA = """
var biz = "MzkwMTYxMzYwNg==";
var mid = "2247533326";
var idx = "5";
var sn = "5ae1c1d004a9ccbf774610a8be1de3d7";
window.__allowLoadResFromMp = true;
var hd_head_img = "https://example.com/avatar";
var nickname = htmlDecode("真锂研究");
var oriCreateTime = '1791450000';
var user_name = "gh_61cfd6274c18";
"""


def _html(body: str, metadata: str = _METADATA, data: str = "") -> str:
    return (
        '<meta property="og:title" content="付费文章标题">'
        f'<div class="rich_media_content" id="js_content">{body}</div>'
        '<div id="js_fullscreen_layout_padding"></div>'
        '<script type="text/javascript">var item_show_type = "0";</script>'
        f'<script type="text/javascript">{metadata}</script>'
        f'<script type="text/javascript">{data}</script>'
    )


@pytest.mark.parametrize("metadata", [_METADATA, ""])
def test_paid_placeholder_keeps_metadata_and_does_not_use_unrelated_images(
    metadata: str,
) -> None:
    # 对应真实页面：正文只有付费占位符，脚本另有图片数组。
    data = """
    window.cgiDataNew = {
      is_pay_subscribe: '1' * 1,
      pay_subscribe_info: {preview_percent: '0' * 1},
      picture_page_info_list: [{cdn_url: 'https://example.com/unrelated.jpg'}]
    };
    """
    result = _parse_html(_URL, _html(_FILTER, metadata, data))

    assert result.article_markdown == _NOTICE
    assert result.article_is_paid is True
    assert result.images == []
    assert result.article_display_type is ArticleDisplayType.ARTICLE
    assert result.article_item_show_type == 0
    assert result.is_valid is bool(metadata)
    if metadata:
        assert result.mp_id == 3901613606
        assert result.mp_name == "真锂研究"
        assert result.mp_user_name == "gh_61cfd6274c18"
        assert result.article_msg_id == 2247533326
        assert result.article_idx == 5
        assert result.article_sn == "5ae1c1d004a9ccbf774610a8be1de3d7"
        assert result.article_publish_time == 1791450000


@pytest.mark.parametrize("body", [
    '<p>可见的免费预览正文。</p>',
    '<img data-src="https://example.com/preview.jpg">',
])
def test_paid_filter_does_not_replace_visible_preview(body: str) -> None:
    result = _parse_html(_URL, _html(body + _FILTER))

    assert result.is_valid
    assert result.article_is_paid is True
    assert _NOTICE not in result.article_markdown
    if "免费预览" in body:
        assert result.article_markdown == "可见的免费预览正文。"
    else:
        assert result.article_markdown == "![](https://example.com/preview.jpg)"
        assert result.images == ["https://example.com/preview.jpg"]


def test_paid_filter_takes_priority_over_empty_video_embed() -> None:
    body = '<iframe class="wx_video_iframe"></iframe>' + _FILTER
    result = _parse_html(_URL, _html(body))

    assert result.is_valid
    assert result.article_is_paid is True
    assert result.article_markdown == _NOTICE


def test_paid_marker_outside_article_does_not_fill_empty_body() -> None:
    result = _parse_html(_URL, _html("") + _FILTER)

    assert result.article_markdown == ""
    assert result.article_is_paid is False
    assert not result.is_valid


def test_paid_flag_without_filter_keeps_accessible_body() -> None:
    result = _parse_html(
        _URL,
        _html('<p>已提供的完整正文。</p>', data="window.cgiDataNew = {is_pay_subscribe: '1' * 1};"),
    )

    assert result.is_valid
    assert result.article_is_paid is True
    assert result.article_markdown == "已提供的完整正文。"


@pytest.mark.parametrize("value", ["1", "'1'", '"1"', "'1' * 1", '"1" * 1', "true"])
@pytest.mark.parametrize("template", [
    "var is_pay_subscribe = VALUE;",
    "window.is_pay_subscribe = VALUE;",
    "window.cgiDataNew = {is_pay_subscribe: VALUE};",
    'window.cgiDataNew = {"is_pay_subscribe": VALUE, other: 0};',
])
def test_paid_flag_forms(value: str, template: str) -> None:
    result = _parse_html(
        _URL, _html("<p>可见正文</p>", data=template.replace("VALUE", value)),
    )

    assert result.article_is_paid is True
    assert result.article_markdown == "可见正文"
    assert result.is_valid


@pytest.mark.parametrize("data", [
    "",
    "var is_pay_subscribe = 0;",
    "window.cgiDataNew = {is_pay_subscribe: '0' * 1};",
    "window.cgiDataNew = {is_pay_subscribe: false};",
    "window.cgiDataNew = {is_pay_subscribe: '10'};",
    "var is_pay_subscribe = '1' * 0;",
    "var is_pay_subscribe = 1 === 0;",
    "// var is_pay_subscribe = 1;",
    "/* window.cgiDataNew = {is_pay_subscribe: 1}; */",
    'var text = "var is_pay_subscribe = 1;";',
    "var recommendation = {is_pay_subscribe: 1};",
    "window.cgiDataNew = {card: {is_pay_subscribe: 1}, is_pay_subscribe: 0};",
    "window.cgiDataNew = {cards: [{is_pay_subscribe: 1}]};",
    "function unrelated() { var is_pay_subscribe = 1; }",
    "other.window.cgiDataNew = {is_pay_subscribe: 1};",
    "other.window.is_pay_subscribe = 1;",
])
def test_missing_free_or_unrelated_paid_flags(data: str) -> None:
    result = _parse_html(_URL, _html("<p>正文提到付费，并不代表本文收费。</p>", data=data))

    assert result.article_is_paid is False
    assert result.is_valid


def test_paid_flag_survives_content_fallback() -> None:
    html = _html("", data="window.cgiDataNew = {is_pay_subscribe: 1};")
    html += '<div class="original_page"><p id="js_share_notice">转载正文</p></div>'
    result = _parse_html(_URL, html)

    assert result.article_is_paid is True
    assert result.article_markdown == "转载正文"


def test_paid_flag_without_content_or_script_type() -> None:
    result = _parse_html(_URL, "<script>var is_pay_subscribe = 1;</script>")

    assert result.article_is_paid is True
    assert not result.is_valid


def test_paid_preview_marker_in_repost() -> None:
    result = _parse_html(
        _URL, f'<div class="original_page"><p>转载预览</p>{_FILTER}</div>',
    )

    assert result.article_is_paid is True


def test_paid_preview_marker_in_script_repost_content() -> None:
    html = (
        '<div class="original_page"></div>'
        '<script type="text/javascript">window.cgiDataNew = {'
        """content: '<p>预览</p><mp-pay-preview-filter></mp-pay-preview-filter>'"""
        '};</script>'
    )
    result = _parse_html(_URL, html)

    assert result.article_is_paid is True
    assert result.article_markdown == "预览"

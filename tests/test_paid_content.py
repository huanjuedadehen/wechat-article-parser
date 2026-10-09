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
    assert result.article_markdown == _NOTICE


def test_paid_marker_outside_article_does_not_fill_empty_body() -> None:
    result = _parse_html(_URL, _html("") + _FILTER)

    assert result.article_markdown == ""
    assert not result.is_valid


def test_paid_flag_without_filter_keeps_accessible_body() -> None:
    result = _parse_html(
        _URL,
        _html('<p>已提供的完整正文。</p>', data="window.cgiDataNew = {is_pay_subscribe: '1' * 1};"),
    )

    assert result.is_valid
    assert result.article_markdown == "已提供的完整正文。"

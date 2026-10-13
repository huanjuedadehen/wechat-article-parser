"""商品卡片占位提示及混合正文的回归测试。"""

import pytest

from wechat_article_parser import ArticleDisplayType
from wechat_article_parser.parser import _parse_html


_URL = "https://mp.weixin.qq.com/s/CBmoIFPJwV4BkidYGp-l1Q"
_NOTICE = "这是一篇商品推荐内容。"
_CARD = '<section><mp-common-cpsad data-pid="104_630468802"></mp-common-cpsad></section>'
_METADATA = """
var biz = "MzkwNDQyNzY2NQ==";
var mid = "2247501127";
var idx = "2";
var sn = "bc04bcc079a380252791ace32e8a91ba";
window.__allowLoadResFromMp = true;
var hd_head_img = "https://example.com/avatar";
var nickname = htmlDecode("老鱼讲古");
var oriCreateTime = '1791711648';
"""


def _html(body: str, metadata: str = _METADATA) -> str:
    return (
        '<meta property="og:title" content="推荐几本好书">'
        f'<div class="rich_media_content" id="js_content">{body}</div>'
        '<script type="text/javascript">var item_show_type = "0";</script>'
        f'<script type="text/javascript">{metadata}</script>'
    )


@pytest.mark.parametrize("metadata", [_METADATA, ""])
def test_product_only_body_returns_one_notice_and_requires_metadata(metadata: str) -> None:
    result = _parse_html(_URL, _html(
        _CARD * 4 + '<section><span><br/></span></section>'
        '<p style="display: none;"><mp-style-type data-value="3"></mp-style-type></p>',
        metadata,
    ))

    assert result.article_markdown == _NOTICE
    assert result.article_display_type is ArticleDisplayType.ARTICLE
    assert result.article_item_show_type == 0
    assert result.article_title == "推荐几本好书"
    assert result.images == []
    assert result.is_valid is bool(metadata)
    if metadata:
        assert result.mp_name == "老鱼讲古"
        assert result.article_msg_id == 2247501127


@pytest.mark.parametrize(("body", "expected", "images"), [
    ('<p>推荐书单。</p>' + _CARD + '<p>阅读愉快。</p>',
     '推荐书单。\n\n阅读愉快。', []),
    (_CARD + '<img data-src="https://example.com/book.jpg">',
     '![](https://example.com/book.jpg)', ['https://example.com/book.jpg']),
])
def test_product_cards_do_not_replace_visible_content(
    body: str, expected: str, images: list[str],
) -> None:
    result = _parse_html(_URL, _html(body))

    assert result.article_markdown == expected
    assert result.images == images
    assert result.is_valid


def test_product_card_outside_body_does_not_fill_empty_body() -> None:
    result = _parse_html(_URL, _html("") + _CARD)

    assert result.article_markdown == ""
    assert not result.is_valid


@pytest.mark.parametrize(("embed", "expected"), [
    ('<mp-pay-preview-filter></mp-pay-preview-filter>', '这是一篇付费内容，正文需付费后查看。'),
    ('<iframe class="wx_video_iframe"></iframe>', '这是一篇纯视频内容。'),
])
def test_existing_notices_keep_priority(embed: str, expected: str) -> None:
    result = _parse_html(_URL, _html(_CARD + embed))

    assert result.article_markdown == expected
    assert result.is_valid

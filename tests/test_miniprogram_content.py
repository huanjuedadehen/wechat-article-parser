"""小程序卡片文字提取、图片排除及混合正文顺序的回归测试。"""

import pytest

from wechat_article_parser import ArticleDisplayType
from wechat_article_parser.parser import _parse_html


_URL = "https://mp.weixin.qq.com/s/qs2YxgdwWDplsmb6H8OS-w"
_NOTICE = "请在微信中打开小程序查看内容。"
_METADATA = """
var item_show_type = "0";
var biz = "MzIxMjg3NDA0Nw==";
var mid = "2247487342";
var idx = "1";
var sn = "6cda9d4c31fd025a8a9a319f96173d4a";
window.__allowLoadResFromMp = true;
var hd_head_img = "https://example.com/publisher-avatar";
var nickname = htmlDecode("苏瑞膜");
var oriCreateTime = '1775961027';
"""
_CARD = (
    '<mp-common-miniprogram data-miniprogram-title="苏瑞膜反渗透与纳滤产品手册（2026版）" '
    'data-miniprogram-nickname="快文档" '
    'data-miniprogram-imageurl="https://example.com/cover.jpg" '
    'data-miniprogram-avatar="https://example.com/avatar.jpg" '
    'data-miniprogram-path="/pages/download/download?fid=13695" '
    'data-miniprogram-appid="wxc24ac90045c531a4">'
    '</mp-common-miniprogram>'
)
_EXPECTED = f"**苏瑞膜反渗透与纳滤产品手册（2026版）**\n\n小程序：快文档\n\n{_NOTICE}"


def _html(body: str, metadata: str = _METADATA) -> str:
    return (
        '<meta property="og:title" content="苏瑞膜SURO®反渗透与纳滤膜产品手册(2026)">'
        f'<div class="rich_media_content">{body}</div>'
        f'<script type="text/javascript">{metadata}</script>'
    )


@pytest.mark.parametrize("metadata", [_METADATA, ""])
def test_miniprogram_only_article_extracts_text_and_requires_metadata(metadata: str) -> None:
    result = _parse_html(_URL, _html(f'<section>{_CARD}</section><p><br></p>', metadata))

    assert result.article_markdown == _EXPECTED
    assert result.images == []
    assert result.is_valid is bool(metadata)
    if metadata:
        assert result.article_display_type is ArticleDisplayType.ARTICLE
        assert result.article_item_show_type == 0
        assert result.mp_name == "苏瑞膜"
        assert result.article_msg_id == 2247487342


def test_mixed_cards_preserve_order_and_exclude_nested_card_images() -> None:
    rendered_card = _CARD.replace(
        '</mp-common-miniprogram>',
        '<img src="https://example.com/cover.jpg"><p>重复卡片文字</p>'
        '</mp-common-miniprogram>',
    )
    result = _parse_html(_URL, _html(
        '<p>正文开头。</p>' + rendered_card
        + '<p><img data-src="https://example.com/body.jpg"></p>'
        + '<mp-common-miniprogram data-miniprogram-title="第二份文档" '
        'data-miniprogram-nickname="文档助手"></mp-common-miniprogram>'
        '<p>正文结尾。</p>'
    ))

    assert result.article_markdown == (
        f'正文开头。\n\n{_EXPECTED}\n\n![](https://example.com/body.jpg)\n\n'
        f'**第二份文档**\n\n小程序：文档助手\n\n{_NOTICE}\n\n正文结尾。'
    )
    assert result.images == ["https://example.com/body.jpg"]


@pytest.mark.parametrize(("attributes", "expected"), [
    ('data-miniprogram-title="  手册  "', f'**手册**\n\n{_NOTICE}'),
    ('data-miniprogram-nickname="  快文档  "', f'小程序：快文档\n\n{_NOTICE}'),
    ('data-miniprogram-title=" " data-miniprogram-nickname=" "', _NOTICE),
    ('', _NOTICE),
])
def test_missing_card_fields_omit_empty_paragraphs(attributes: str, expected: str) -> None:
    result = _parse_html(_URL, _html(
        f'<mp-common-miniprogram {attributes}></mp-common-miniprogram>'
    ))

    assert result.article_markdown == expected
    assert result.images == []


def test_card_attributes_preserve_entities_and_escape_markdown() -> None:
    result = _parse_html(_URL, _html(
        '<mp-common-miniprogram data-miniprogram-title="A &amp; B *手册* &lt;tag&gt;" '
        'data-miniprogram-nickname="文档&amp;助手"></mp-common-miniprogram>'
    ))

    assert result.article_markdown == (
        r'**A & B \*手册\* <tag>**' f'\n\n小程序：文档&助手\n\n{_NOTICE}'
    )


def test_card_outside_article_body_is_not_extracted() -> None:
    result = _parse_html(_URL, _html("") + _CARD)

    assert result.article_markdown == ""
    assert result.images == []
    assert not result.is_valid

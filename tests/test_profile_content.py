"""公众号推荐卡片转换及正文顺序的离线回归测试。"""

import json

import pytest

from wechat_article_parser import ArticleDisplayType
from wechat_article_parser.parser import _parse_html


_URL = "https://mp.weixin.qq.com/s/PXZuh3fFEi3VXUUI1uBnlw"
_METADATA = """
var item_show_type = "0";
var biz = "MzUyNTgyNjUzMw==";
var mid = "2247923648";
var idx = "2";
var sn = "d744c25ecdf2ac7f361d880dffb0a2ca";
window.__allowLoadResFromMp = true;
var hd_head_img = "https://example.com/publisher-avatar";
var nickname = htmlDecode("药融圈");
var oriCreateTime = '1791441362';
"""


def _html(body: str) -> str:
    return (
        '<meta property="og:title" content="公众号推荐文章">'
        f'<div class="rich_media_content">{body}</div>'
        '<div id="js_fullscreen_layout_padding"></div>'
        f'<script type="text/javascript">{_METADATA}</script>'
    )


def test_profile_only_article_preserves_names_signatures_and_metadata() -> None:
    body = (
        '<section><span><mp-common-profile data-nickname="药融圈" '
        'data-signature="中国医药信息和人脉的链接平台" '
        'data-headimg="https://example.com/card-avatar"></mp-common-profile></span></section>'
        '<section><mp-common-profile data-nickname="药通社" '
        'data-signature="政策、资讯、产业、技术"></mp-common-profile></section>'
    )
    result = _parse_html(
        _URL,
        _html(body)
        + '<mp-common-profile data-nickname="页外推荐" data-signature="不属于正文"></mp-common-profile>',
    )

    assert result.article_markdown == (
        '**药融圈**：中国医药信息和人脉的链接平台\n\n'
        '**药通社**：政策、资讯、产业、技术'
    )
    assert result.images == []
    assert result.is_valid
    assert result.mp_id == 3525826533
    assert result.mp_name == "药融圈"
    assert result.article_msg_id == 2247923648
    assert result.article_idx == 2
    assert result.article_sn == "d744c25ecdf2ac7f361d880dffb0a2ca"
    assert result.article_publish_time == 1791441362
    assert result.article_display_type is ArticleDisplayType.ARTICLE
    assert result.article_item_show_type == 0


def test_profile_mixed_with_text_and_images_preserves_order_without_duplicate_card() -> None:
    result = _parse_html(_URL, _html(
        '<p>推荐以下公众号。</p><mp-common-profile data-nickname="药融圈" '
        'data-signature="医药信息平台">'
        '<img src="https://example.com/card-avatar"><p>药融圈</p><p>医药信息平台</p>'
        '</mp-common-profile>'
        '<p><img data-src="https://mmbiz.qpic.cn/mmbiz_jpg/body/0?wx_fmt=jpeg"></p>'
        '<p>正文结尾。</p>'
    ))

    assert result.article_markdown == (
        '推荐以下公众号。\n\n**药融圈**：医药信息平台\n\n'
        '![](https://mmbiz.qpic.cn/mmbiz_jpg/body/640)\n\n正文结尾。'
    )
    assert result.images == ["https://mmbiz.qpic.cn/mmbiz_jpg/body/640"]


@pytest.mark.parametrize(("attributes", "expected"), [
    ('data-nickname="  药融圈  "', '**药融圈**'),
    ('data-signature="  医药信息平台  "', '医药信息平台'),
    ('data-nickname=" " data-signature=" "', ''),
    ('', ''),
])
def test_profile_missing_fields_keeps_available_text_without_empty_placeholders(
    attributes: str, expected: str,
) -> None:
    result = _parse_html(_URL, _html(f'<mp-common-profile {attributes}></mp-common-profile>'))

    assert result.article_markdown == expected
    assert result.is_valid is bool(expected)
    assert result.images == []


def test_profile_attributes_keep_entities_and_escape_markdown_characters() -> None:
    result = _parse_html(_URL, _html(
        '<mp-common-profile data-nickname="药品&amp;研发*圈*" '
        'data-signature="A &amp; B，进度 100%，保留 %20 和 &lt;tag&gt;。">'
        '</mp-common-profile>'
    ))

    assert result.article_markdown == r'**药品&研发\*圈\***：A & B，进度 100%，保留 %20 和 <tag>。'


def test_repost_script_body_uses_same_profile_conversion() -> None:
    body = (
        '<mp-common-profile data-nickname="药通社" '
        'data-signature="政策、资讯、产业、技术"></mp-common-profile>'
    )
    html = (
        '<meta property="og:title" content="转载推荐文章">'
        '<div class="original_page"><span id="js_share_source" '
        'data-url="https://example.com/original"></span></div>'
        f'<script type="text/javascript">{_METADATA}</script>'
        '<script type="text/javascript">window.cgiDataNew = '
        f'{{content_noencode: {json.dumps(body, ensure_ascii=False)}}};</script>'
    )
    result = _parse_html(_URL, html)

    assert result.is_valid
    assert result.article_markdown == (
        '**药通社**：政策、资讯、产业、技术\n\n'
        '[查看原文](https://example.com/original)'
    )
    assert result.images == []

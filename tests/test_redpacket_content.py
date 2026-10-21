"""红包封面文字提示及预览图片排除的离线回归测试。"""

import json

import pytest

from wechat_article_parser import ArticleDisplayType
from wechat_article_parser.parser import _parse_html


_URL = "https://mp.weixin.qq.com/s/CgWnsf3lyBijzy3L5Y7Xtg"
_NOTICE = "红包封面，请在微信中查看。"
_METADATA = """
var item_show_type = "0";
var biz = "MzIyMjkzMzY4Ng==";
var mid = "2247511420";
var idx = "1";
var sn = "b8cdf9976e0544dbc6acebdcc978264a";
window.__allowLoadResFromMp = true;
var hd_head_img = "https://example.com/avatar";
var nickname = htmlDecode("WgpSec狼组安全团队");
var oriCreateTime = '1771218474';
"""
_CARD = (
    '<mp-common-redpacket data-name="%E7%BA%A2%E5%8C%85" '
    'data-openimg="https%3A%2F%2Fexample.com%2Fopen.jpg" '
    'data-receiveimg="https%3A%2F%2Fexample.com%2Freceive.jpg" '
    'data-coveruri="cover-id"></mp-common-redpacket>'
)


def _html(body: str, metadata: str = _METADATA) -> str:
    return (
        '<meta property="og:title" content="新年快乐 · 红包封面">'
        f'<div class="rich_media_content">{body}</div>'
        f'<script type="text/javascript">{metadata}</script>'
    )


@pytest.mark.parametrize("metadata", [_METADATA, ""])
@pytest.mark.parametrize("card", [_CARD, '<mp-common-redpacket></mp-common-redpacket>'])
def test_redpacket_only_body_returns_notice_and_requires_metadata(metadata: str, card: str) -> None:
    result = _parse_html(_URL, _html(card, metadata))
    assert result.article_markdown == _NOTICE
    assert result.images == []
    assert result.is_valid is bool(metadata)
    if metadata:
        assert result.article_display_type is ArticleDisplayType.ARTICLE
        assert result.mp_name == 'WgpSec狼组安全团队'
        assert result.article_msg_id == 2247511420


def test_redpacket_removes_rendered_contents_and_keeps_surrounding_body_order() -> None:
    rendered = _CARD.replace('</mp-common-redpacket>',
        '<p>预览文字</p><a href="https://example.com/receive">领取链接</a>'
        '<img src="https://example.com/preview.jpg">'
        '<svg><image href="https://example.com/svg-preview.jpg"/></svg>'
        '</mp-common-redpacket>',
    )
    result = _parse_html(_URL, _html(
        '<p>新年快乐</p>' + rendered + '<img data-src="https://example.com/body.jpg">'
        + _CARD + '<p>正文结尾</p>',
    ))
    assert result.article_markdown == (
        f'新年快乐\n\n{_NOTICE}\n\n![](https://example.com/body.jpg)\n\n{_NOTICE}\n\n正文结尾'
    )
    assert result.images == ['https://example.com/body.jpg']


def test_redpacket_outside_body_does_not_create_valid_content() -> None:
    result = _parse_html(_URL, _html('') + _CARD)
    assert result.article_markdown == ''
    assert result.images == []
    assert not result.is_valid


def test_repost_script_body_uses_redpacket_notice() -> None:
    page = (
        '<meta property="og:title" content="转载红包封面">'
        '<div class="original_page"></div>'
        f'<script type="text/javascript">{_METADATA}'
        f'window.cgiDataNew = {{content_noencode: {json.dumps(_CARD)}}};</script>'
    )
    result = _parse_html(_URL, page)
    assert result.article_markdown == _NOTICE
    assert result.images == []
    assert result.is_valid

"""纯视频号卡片正文的离线回归测试。"""

import pytest

from wechat_article_parser import ArticleDisplayType
from wechat_article_parser.parser import _parse_html


_URL = "https://mp.weixin.qq.com/s/wAyM7yYKDfTH21-XpS9agQ"
_CARD = (
    '<mp-common-videosnap data-type="video" data-id="video-id" '
    'data-desc="视频描述" data-url="https://example.com/cover.jpg">'
    '</mp-common-videosnap>'
)
_IFRAME = (
    '<iframe class="video_iframe rich_pages wx_video_iframe" data-mpvid="wxv_123" '
    'data-src="https://mp.weixin.qq.com/mp/readtemplate?t=pages/video_player_tmpl'
    '&amp;action=mpvideo&amp;vid=wxv_123"></iframe>'
)
_METADATA = """
var biz = "MjM5NTAwMzE0MA==";
var mid = "2908209265";
var idx = "4";
var sn = "signature";
window.__allowLoadResFromMp = true;
var hd_head_img = "https://example.com/avatar";
var nickname = htmlDecode("卡车之家");
var oriCreateTime = '1791462000';
"""


def _html(body: str, metadata: str = _METADATA) -> str:
    return (
        '<meta property="og:title" content="后双胎大轻客，江淮星锐EV6">'
        f'<div class="rich_media_content">{body}</div>'
        '<script type="text/javascript">var item_show_type = "0";</script>'
        f'<script type="text/javascript">{metadata}</script>'
    )


@pytest.mark.parametrize("metadata", [_METADATA, ""])
@pytest.mark.parametrize("video", [_CARD, _IFRAME])
def test_video_only_body_gets_one_sentence_and_still_requires_metadata(
    metadata: str, video: str,
) -> None:
    result = _parse_html(
        _URL,
        _html(f'<section>{video}</section><p><br></p><mp-style-type></mp-style-type>', metadata),
    )

    assert result.article_markdown == "这是一篇纯视频内容。"
    assert result.article_display_type is ArticleDisplayType.ARTICLE
    assert result.article_item_show_type == 0
    assert result.images == []
    assert result.is_valid is bool(metadata)


@pytest.mark.parametrize("body", [
    '<p>实际文字正文</p>',
    '<img data-src="https://example.com/body.jpg">',
])
@pytest.mark.parametrize("video", [_CARD, _IFRAME])
def test_video_with_other_content_keeps_existing_markdown(body: str, video: str) -> None:
    result = _parse_html(_URL, _html(body + video))

    assert result.is_valid
    assert "这是一篇纯视频内容。" not in result.article_markdown
    assert "cover.jpg" not in result.article_markdown
    if "实际文字正文" in body:
        assert result.article_markdown == "实际文字正文"
    else:
        assert result.images == ["https://example.com/body.jpg"]
        assert result.article_markdown == "![](https://example.com/body.jpg)"


@pytest.mark.parametrize("body", [
    "",
    _CARD.replace('data-type="video"', 'data-type="image"'),
    '<iframe src="https://example.com/unrelated"></iframe>',
])
def test_empty_or_non_video_body_does_not_get_video_notice(body: str) -> None:
    result = _parse_html(_URL, _html(body))

    assert result.article_markdown == ""
    assert not result.is_valid

"""SVG 容器承载正文图片的离线回归测试。"""

import html

import pytest

from wechat_article_parser import ArticleDisplayType, ArticleResult
from wechat_article_parser.parser import _parse_html


_URL = "https://mp.weixin.qq.com/s/3ixeC9whuEgpup2G1yvDZg"
_METADATA = """
var item_show_type = "0";
var biz = "MjM5MjY2MTc5NQ==";
var mid = "2652403355";
var idx = "1";
var sn = "9c582b2554db23b592ed758e95680f0a";
window.__allowLoadResFromMp = true;
var hd_head_img = "https://example.com/avatar";
var nickname = htmlDecode("CFMOTO春风动力");
var oriCreateTime = '1791454818';
"""


def _parse(body: str) -> ArticleResult:
    return _parse_html(
        _URL,
        '<meta property="og:title" content="SVG 图片正文">'
        f'<div class="rich_media_content">{body}</div>'
        '<div id="js_fullscreen_layout_padding"></div>'
        f'<script type="text/javascript">{_METADATA}</script>',
    )


def test_foreignobject_images_keep_body_order_and_rich_text_metadata() -> None:
    # 对应真实页面：整个正文由三个 SVG 中的长图组成，没有背景图。
    body = "".join(
        '<svg viewBox="0 0 1080 2362"><foreignObject>'
        f'<span><img data-src="https://mmbiz.qpic.cn/mmbiz_jpg/body-{i}/0?wx_fmt=jpeg"></span>'
        '</foreignObject></svg>'
        for i in range(3)
    )
    result = _parse(body)
    urls = [f"https://mmbiz.qpic.cn/mmbiz_jpg/body-{i}/640" for i in range(3)]

    assert result.article_markdown == "".join(f"![]({url})" for url in urls)
    assert result.images == urls
    assert result.is_valid
    assert result.mp_id == 2392661795
    assert result.mp_name == "CFMOTO春风动力"
    assert result.article_msg_id == 2652403355
    assert result.article_idx == 1
    assert result.article_sn == "9c582b2554db23b592ed758e95680f0a"
    assert result.article_publish_time == 1791454818
    assert result.article_display_type is ArticleDisplayType.ARTICLE


def test_nested_svg_images_and_backgrounds_keep_source_order() -> None:
    result = _parse(
        '<svg style=\'background-image: url("https://example.com/first.jpg")\'>'
        '<foreignObject><img data-src="https://example.com/second.jpg" alt="第二张">'
        '<svg style=\'background-image: url("https://example.com/third.jpg")\'>'
        '<foreignObject><img src="https://example.com/fourth.jpg"></foreignObject>'
        '</svg></foreignObject></svg>'
    )

    assert result.article_markdown == "".join([
        "![](https://example.com/first.jpg)",
        "![第二张](https://example.com/second.jpg)",
        "![](https://example.com/third.jpg)",
        "![](https://example.com/fourth.jpg)",
    ])
    assert result.images == [
        "https://example.com/first.jpg",
        "https://example.com/second.jpg",
        "https://example.com/third.jpg",
        "https://example.com/fourth.jpg",
    ]


def test_repeated_svg_images_remain_in_body_but_image_list_is_unique() -> None:
    result = _parse(
        '<img src="https://mmbiz.qpic.cn/mmbiz_jpg/body/0">'
        '<svg><foreignObject><svg><foreignObject>'
        '<img data-src="https://mmbiz.qpic.cn/mmbiz_jpg/body/640?wx_fmt=jpeg">'
        '</foreignObject></svg></foreignObject></svg>'
    )

    url = "https://mmbiz.qpic.cn/mmbiz_jpg/body/640"
    assert result.images == [url]
    assert result.article_markdown.count(f"![]({url})") == 2


def test_decorative_svg_and_invalid_images_do_not_pollute_body() -> None:
    result = _parse(
        '<p>正文</p><svg><title>装饰分隔线</title><path d="M0 0 L100 0"></path></svg>'
        '<svg><foreignObject><img><img src="data:image/png;base64,AA==">'
        '</foreignObject></svg>'
    )

    assert result.article_markdown == "正文"
    assert result.images == []


@pytest.mark.parametrize("property_name", ["background", "background-image", "BACKGROUND"])
@pytest.mark.parametrize("quote", ["", "'", '"'])
def test_svg_background_variants_keep_rich_text_metadata(property_name: str, quote: str) -> None:
    url = "https://mmecoa.qpic.cn/sz_mmecoa_jpg/body/0?wx_fmt=jpeg"
    style = f'display: block; {property_name}: URL( {quote}{url}{quote} ) center / cover no-repeat;'
    result = _parse(f'<svg style="{html.escape(style, quote=True)}"></svg>')

    normalized = "https://mmecoa.qpic.cn/sz_mmecoa_jpg/body/640"
    assert result.images == [normalized]
    assert result.article_markdown == f'![]({normalized})'
    assert result.mp_name == "CFMOTO春风动力"
    assert result.article_publish_time == 1791454818
    assert result.is_valid


def test_background_shorthand_preserves_nested_order_and_repeated_images() -> None:
    result = _parse(
        '<p>开头</p><svg style="background: #fff url(https://example.com/first.jpg) no-repeat;">'
        '<foreignObject><img src="https://example.com/second.jpg"></foreignObject>'
        '<svg style="background: url(https://example.com/first.jpg)"></svg>'
        '</svg><p>结尾</p>'
    )
    assert result.article_markdown == (
        '开头\n\n![](https://example.com/first.jpg)![](https://example.com/second.jpg)'
        '![](https://example.com/first.jpg)\n\n结尾'
    )
    assert result.images == ["https://example.com/first.jpg", "https://example.com/second.jpg"]


@pytest.mark.parametrize("style", [
    'background: none; mask-image: url(https://example.com/mask.svg)',
    'background-color: url(https://example.com/not-background.jpg)',
    '--background: url(https://example.com/custom.jpg)',
    'background: url(data:image/png;base64,AA==)',
    'background: url(/relative.jpg)',
    'background: url("")',
    'background: url("https://example.com/unclosed.jpg)',
])
def test_invalid_or_unrelated_background_urls_do_not_fill_body(style: str) -> None:
    result = _parse(f'<svg style="{html.escape(style, quote=True)}"></svg>')
    assert result.article_markdown == ""
    assert result.images == []
    assert not result.is_valid

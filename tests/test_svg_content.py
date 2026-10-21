"""SVG 容器承载正文图片的离线回归测试。"""

import html
import json

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


@pytest.mark.parametrize("attribute", ["href", "xlink:href"])
def test_svg_image_elements_keep_nested_order_and_drop_interaction(attribute: str) -> None:
    result = _parse(
        '<a href="https://example.com/jump"><svg opacity="0" style="display:none">'
        '<animate attributeName="opacity" begin="click" values="0;1" dur="1s"/>'
        f'<image {attribute}="https://example.com/first.jpg"/>'
        '<g><animateTransform attributeName="transform" type="scale" '
        'values="1;1.3;1" dur="2s" repeatCount="indefinite"/>'
        f'<image {attribute}="https://example.com/second.jpg"/></g>'
        '<foreignObject><a href="https://example.com/inner">'
        '<img data-src="https://example.com/third.jpg" alt="第三张"></a></foreignObject>'
        '<rect opacity="0" width="1000" height="1000"/>'
        '<a href="https://example.com/hotspot"><rect width="100" height="100"/></a>'
        '</svg></a>'
    )
    assert result.images == [f'https://example.com/{name}.jpg' for name in ('first', 'second', 'third')]
    assert result.article_markdown == (
        '![](https://example.com/first.jpg)![](https://example.com/second.jpg)'
        '![第三张](https://example.com/third.jpg)'
    )
    assert result.is_valid


def test_svg_href_takes_precedence_and_repeated_images_are_only_deduplicated_in_list() -> None:
    result = _parse(
        '<svg><image href="https://example.com/first.jpg" xlink:href="https://example.com/old.jpg"/>'
        '<g><image href="https://example.com/first.jpg"/></g>'
        '<image href="" xlink:href="https://example.com/unused.jpg"/></svg>'
    )
    assert result.images == ['https://example.com/first.jpg']
    assert result.article_markdown == '![](https://example.com/first.jpg)' * 2


def _frame_sequence(kind: str = "image", *, vertical: bool = False,
                    animation: str = "", coordinates: tuple[int, ...] = (0, 100, 200)) -> str:
    frames = []
    for i, position in enumerate(coordinates):
        x, y = (0, position) if vertical else (position, 0)
        attrs = f'x="{x}" y="{y}" width="100" height="100"'
        url = f'https://example.com/frame-{i}.jpg'
        if kind == "image":
            frame = f'<image href="{url}" {attrs}/>'
        elif kind == "background":
            frame = f'<svg {attrs} style="background:url({url})"></svg>'
        else:
            frame = f'<foreignObject {attrs}><img data-src="{url}"></foreignObject>'
        frames.append(f'<g>{frame}</g>')
    values = '0 0;0 -100;0 -200' if vertical else '0 0;-100 0;-200 0'
    animation = animation or (
        f'<animateTransform attributeName="transform" type="translate" calcMode="discrete" '
        f'values="{values}" dur="0.3s" repeatCount="indefinite"/>'
    )
    return '<g>' + animation + ''.join(frames) + '</g>'


@pytest.mark.parametrize("kind", ["image", "background", "foreignobject"])
@pytest.mark.parametrize("vertical", [False, True])
def test_frame_sequence_keeps_first_frame_for_all_svg_image_sources(kind: str, vertical: bool) -> None:
    result = _parse(
        '<svg><image href="https://example.com/static-before.jpg"/>'
        + _frame_sequence(kind, vertical=vertical)
        + '<image href="https://example.com/static-after.jpg"/></svg>'
    )
    assert result.images == [
        'https://example.com/static-before.jpg', 'https://example.com/frame-0.jpg',
        'https://example.com/static-after.jpg',
    ]
    assert result.article_markdown == ''.join(f'![]({url})' for url in result.images)
    assert result.is_valid


@pytest.mark.parametrize("attributes", [
    'calcMode="spline" dur="0.3s"',
    'calcMode="discrete" dur="12s"',
    'calcMode="discrete" dur="invalid"',
    'calcMode="discrete" dur="0s"',
    'calcMode="discrete" dur="0.3s" keyTimes="0;0.9;1"',
    'calcMode="discrete" dur="0.3s" href="#another-group"',
    'calcMode="discrete" dur="0.3s" additive="sum"',
])
def test_carousel_and_uncertain_animations_preserve_every_image(attributes: str) -> None:
    animation = (
        '<animateTransform attributeName="transform" type="translate" '
        f'values="0 0;-100 0;-200 0" repeatCount="indefinite" {attributes}/>'
    )
    result = _parse('<svg>' + _frame_sequence(animation=animation) + '</svg>')
    assert result.images == [f'https://example.com/frame-{i}.jpg' for i in range(3)]


@pytest.mark.parametrize("coordinates", [(0, 0, 0), (0, 150, 300), (200, 100, 0)])
def test_discrete_animation_with_unmatched_geometry_keeps_all_images(coordinates: tuple[int, ...]) -> None:
    result = _parse('<svg>' + _frame_sequence(coordinates=coordinates) + '</svg>')
    assert result.images == [f'https://example.com/frame-{i}.jpg' for i in range(3)]


def test_multiple_frame_sequences_do_not_remove_each_others_first_frame() -> None:
    result = _parse('<svg>' + _frame_sequence() + _frame_sequence('background') + '</svg>')
    assert result.images == ['https://example.com/frame-0.jpg']
    assert result.article_markdown == '![](https://example.com/frame-0.jpg)' * 2


@pytest.mark.parametrize("extra", ['transform="translate(10 0)"', 'style="transform: translateX(10px)"'])
def test_extra_frame_transforms_preserve_all_images(extra: str) -> None:
    sequence = _frame_sequence().replace('<image ', f'<image {extra} ')
    result = _parse('<svg>' + sequence + '</svg>')
    assert result.images == [f'https://example.com/frame-{i}.jpg' for i in range(3)]


def test_empty_svg_and_placeholder_images_do_not_make_fallback_valid() -> None:
    result = _parse_html(
        _URL,
        '<meta property="og:title" content="无图片内容">'
        '<div class="rich_media_content"><svg><image/><image href="data:image/png;base64,AA"/>'
        '<image href="/relative.jpg"/><rect opacity="0"/></svg><img></div>'
        '<div id="js_fullscreen_layout_padding"></div>'
        f'<script type="text/javascript">{_METADATA}'
        "window.cgiDataNew = {picture_page_info_list: [], text_page_info: {content: '<img>'}};"
        '</script>',
    )
    assert result.article_markdown == ''
    assert result.images == []
    assert not result.is_valid


@pytest.mark.parametrize("values", [
    '0 0;-100 0;-200 0;',
    '0 0;-100 0;-200 0;-200 0;-200 0;',
    '0 0;0 0;-100 0;-100 0;-200 0;',
])
def test_frame_sequences_allow_trailing_semicolon_and_repeated_holds(values: str) -> None:
    animation = (
        '<animateTransform attributeName="transform" type="translate" calcMode="discrete" '
        f'values="{values}" dur="0.3s" repeatCount="indefinite"/>'
    )
    result = _parse('<svg>' + _frame_sequence(animation=animation) + '</svg>')
    assert result.images == ['https://example.com/frame-0.jpg']


@pytest.mark.parametrize("values", [
    '0 0;;-100 0;-200 0;',
    '0 0;-200 0;-100 0;',
    '0 0;-100 0;-200 0;0 0;',
])
def test_invalid_or_reordered_frame_sequences_preserve_every_image(values: str) -> None:
    animation = (
        '<animateTransform attributeName="transform" type="translate" calcMode="discrete" '
        f'values="{values}" dur="0.3s" repeatCount="indefinite"/>'
    )
    result = _parse('<svg>' + _frame_sequence(animation=animation) + '</svg>')
    assert len(result.images) == 3


def test_long_holds_do_not_turn_slow_carousel_into_fast_animation() -> None:
    values = ';'.join(['0 0'] * 10 + ['-100 0'] * 10 + ['-200 0'] * 10)
    animation = (
        '<animateTransform attributeName="transform" type="translate" calcMode="discrete" '
        f'values="{values}" dur="3s" repeatCount="indefinite"/>'
    )
    result = _parse('<svg>' + _frame_sequence(animation=animation) + '</svg>')
    assert len(result.images) == 3


@pytest.mark.parametrize(("viewport", "count"), [
    ('viewBox="0 0 100 100"', 1),
    ('viewBox="0 0 200 100"', 4),
    ('viewBox="0 0 100 100" overflow="visible"', 4),
    ('viewBox="0 0 100 100" style="overflow:visible"', 4),
    ('', 4),
])
def test_unplayed_tail_frame_is_only_omitted_with_confirmed_single_frame_viewport(
    viewport: str, count: int,
) -> None:
    result = _parse(f'<svg {viewport}>' + _frame_sequence(coordinates=(0, 100, 200, 300)) + '</svg>')
    assert result.images == [f'https://example.com/frame-{i}.jpg' for i in range(count)]


@pytest.mark.parametrize("kind", ["image", "background", "foreignobject"])
@pytest.mark.parametrize("vertical", [False, True])
def test_percentage_frame_sizes_are_resolved_from_nearest_viewbox(kind: str, vertical: bool) -> None:
    sequence = _frame_sequence(kind, vertical=vertical).replace(
        'width="100" height="100"', 'width="100%" height="100%"',
    )
    result = _parse('<svg viewBox="0 0 999 999"><svg viewBox="0 0 100 100">' + sequence + '</svg></svg>')
    assert result.images == ['https://example.com/frame-0.jpg']


@pytest.mark.parametrize("viewport", [
    '', 'viewBox="bad"', 'viewBox="0 0 0 100"', 'width="100%" height="100%"',
])
def test_unresolved_percentage_sizes_keep_every_frame(viewport: str) -> None:
    sequence = _frame_sequence().replace('width="100" height="100"', 'width="100%" height="100%"')
    result = _parse(f'<svg {viewport}>' + sequence + '</svg>')
    assert len(result.images) == 3


def test_svg_text_and_foreignobject_content_keep_order_with_images_without_links() -> None:
    result = _parse(
        '<svg><text x="10" y="20"><tspan>活动介绍</tspan></text>'
        '<image href="https://example.com/poster.jpg"/>'
        '<a href="https://example.com/jump"><text>报名时间</text></a>'
        '<foreignObject><p>保留<strong>规则</strong>与'
        '<a href="https://example.com/rules">说明</a>。</p>'
        '<img src="https://example.com/detail.jpg" alt="详情"></foreignObject>'
        '<svg><text>结束</text></svg></svg>'
    )
    assert result.article_markdown == (
        '活动介绍\n\n![](https://example.com/poster.jpg)\n\n报名时间\n\n'
        '保留**规则**与说明。\n\n![详情](https://example.com/detail.jpg)\n\n结束'
    )
    assert result.images == ['https://example.com/poster.jpg', 'https://example.com/detail.jpg']
    assert result.is_valid


def test_svg_text_preserves_line_breaks_entities_and_hidden_content() -> None:
    result = _parse(
        '<svg opacity="0"><animate attributeName="opacity" begin="click" values="0;1"/>'
        '<text><tspan x="0" y="20">A &amp; B</tspan><tspan> *活动*</tspan>'
        '<tspan x="0" dy="20">第二行</tspan><tspan dy="0">末尾</tspan></text></svg>'
    )
    assert result.article_markdown == r'A & B \*活动\*' + '  \n第二行末尾'
    assert result.is_valid


def test_svg_definitions_masks_and_descriptions_are_not_body_content() -> None:
    result = _parse(
        '<svg><defs><g><text>未使用定义</text><image href="https://example.com/unused.jpg"/></g></defs>'
        '<mask><text>遮罩文字</text><image href="https://example.com/mask.jpg"/></mask>'
        '<title>辅助标题</title><desc>辅助说明</desc><rect opacity="0"/>'
        '<text>真正正文</text><image href="https://example.com/body.jpg"/></svg>'
    )
    assert result.article_markdown == '真正正文\n\n![](https://example.com/body.jpg)'
    assert result.images == ['https://example.com/body.jpg']


def test_svg_background_is_kept_before_text_and_frame_reduction_does_not_drop_text() -> None:
    result = _parse(
        '<svg style="background:url(https://example.com/background.jpg)">'
        '<text>前文</text>' + _frame_sequence().replace('</g>', '<text>提示</text></g>', 1)
        + '<text>后文</text></svg>'
    )
    assert result.article_markdown == (
        '![](https://example.com/background.jpg)\n\n前文\n\n'
        '![](https://example.com/frame-0.jpg)\n\n提示\n\n后文'
    )


def test_repost_script_svg_body_preserves_text() -> None:
    body = '<svg><text>转载正文</text><image href="https://example.com/body.jpg"/></svg>'
    result = _parse_html(_URL,
        '<meta property="og:title" content="转载文章">'
        '<div class="original_page"></div>'
        f'<script type="text/javascript">{_METADATA}'
        f'window.cgiDataNew = {{content_noencode: {json.dumps(body)}}};</script>',
    )
    assert result.article_markdown == '转载正文\n\n![](https://example.com/body.jpg)'
    assert result.is_valid

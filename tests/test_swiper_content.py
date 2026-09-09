"""使用精简页面离线回归轮播图片的提取和 Markdown 输出。"""

import pytest

from wechat_article_parser.parser import _parse_html


_URL = "https://mp.weixin.qq.com/s/0Wz3JeMbtWBL5iWJgYPS_Q"
_EXPECTED_IMAGES = [
    "https://mmbiz.qpic.cn/mmbiz_png/second/640",
    "https://mmbiz.qpic.cn/mmbiz_png/first/640",
]
_PICTURES = r"""[
  {
    note: '含括号 ] } 和转义引号 \' 的字符串',
    watermark_info: {
      position: {x: 1},
      cdn_url: 'https://mmbiz.qpic.cn/mmbiz_png/watermark/0'
    },
    cdn_url: 'https://mmbiz.qpic.cn/mmbiz_png/second/0?wx_fmt=png',
    share_cover: {
      crop_info: {x: 0},
      cdn_url: 'https://mmbiz.qpic.cn/mmbiz_png/share-cover/0'
    },
    live_photo: {format_info: [{cdn_url: 'https://example.com/live-photo'}]}
  },
  {"cdn_url": "https://mmbiz.qpic.cn/mmbiz_png/first/0?wx_fmt=png"},
  {cdn_url: 'https://mmbiz.qpic.cn/mmbiz_png/second/640'},
  {cdn_url: ''}
]"""
_DESCRIPTION = r'window.desc = "第一行\x0a第二行";'
_REFERENCE = """
window.picture_page_info_list =
  ((window.cgiDataNew && window.cgiDataNew.picture_page_info_list) || []).slice(0, 20);
"""


def _html(*scripts: str, fullscreen: bool = False) -> str:
    content = (
        '<div id="js_fullscreen_layout_padding"></div>'
        if fullscreen
        else '<div class="share_media_swiper_content"></div>'
    )
    return content + "".join(
        f'<script type="text/javascript">{script}</script>' for script in scripts
    )


@pytest.mark.parametrize("layout", ["inline", "data_first", "description_first"])
def test_swiper_collects_body_images_across_scripts(layout: str) -> None:
    data = (
        "window.cgiDataNew = {"
        "cdn_url: 'https://mmbiz.qpic.cn/mmbiz_png/outside-before/0',"
        f"picture_page_info_list: {_PICTURES},"
        "other: {cdn_url: 'https://mmbiz.qpic.cn/mmbiz_png/outside-after/0'}"
        "};"
    )
    reference = _REFERENCE + _DESCRIPTION
    if layout == "inline":
        scripts = [f"window.picture_page_info_list = {_PICTURES};" + _DESCRIPTION]
    elif layout == "data_first":
        scripts = [data, reference]
    else:
        scripts = [reference, data]

    result = _parse_html(_URL, _html(*scripts))

    assert result.images == _EXPECTED_IMAGES
    assert result.article_markdown.count("![") == 2
    assert result.article_markdown.index(_EXPECTED_IMAGES[0]) < result.article_markdown.index(_EXPECTED_IMAGES[1])
    assert "第一行  \n第二行" in result.article_markdown
    assert "outside" not in result.article_markdown
    assert "watermark" not in result.article_markdown
    assert "share-cover" not in result.article_markdown
    assert "live-photo" not in result.article_markdown


def test_swiper_later_empty_lists_do_not_erase_images() -> None:
    result = _parse_html(
        _URL,
        _html(
            f"window.picture_page_info_list = {_PICTURES};" + _DESCRIPTION,
            "window.picture_page_info_list = [];",
            _REFERENCE,
        ),
    )

    assert result.images == _EXPECTED_IMAGES
    assert result.article_markdown.count("![") == 2
    assert "第一行  \n第二行" in result.article_markdown


def test_swiper_ignores_list_text_in_strings_and_comments() -> None:
    decoy = "picture_page_info_list: [{cdn_url: 'https://example.com/decoy'}]"
    result = _parse_html(
        _URL,
        _html(
            f'var example = "{decoy}";\n'
            f"// {decoy}\n"
            f"/* {decoy} */\n"
            f"var template = `{decoy}`;\n",
            f"window.cgiDataNew = {{'picture_page_info_list': {_PICTURES}}};",
            _REFERENCE + _DESCRIPTION,
        ),
    )

    assert result.images == _EXPECTED_IMAGES
    assert "decoy" not in result.article_markdown


def test_swiper_image_only_content() -> None:
    result = _parse_html(
        _URL,
        _html(f"window.cgiDataNew = {{picture_page_info_list: {_PICTURES}}};", _REFERENCE),
    )

    assert result.images == _EXPECTED_IMAGES
    assert result.article_markdown.count("![") == 2


def test_swiper_text_only_content() -> None:
    result = _parse_html(
        _URL,
        _html(
            "window.cgiDataNew = {picture_page_info_list: [], cdn_url: 'https://example.com/cover'};",
            _REFERENCE,
            _DESCRIPTION,
        ),
    )

    assert result.images == []
    assert result.article_markdown == "第一行  \n第二行"


def test_fullscreen_shared_image_extractor_keeps_body_images() -> None:
    result = _parse_html(
        _URL,
        _html(
            "window.cgiDataNew = {"
            "cdn_url: 'https://example.com/cover',"
            f"picture_page_info_list: {_PICTURES},"
            "text_page_info: {content: JsDecode('全屏正文')}"
            "};",
            fullscreen=True,
        ),
    )

    assert result.images == _EXPECTED_IMAGES
    assert result.article_markdown.count("![") == 2
    assert "全屏正文" in result.article_markdown

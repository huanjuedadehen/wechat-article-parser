"""类型字段优先分发、模板细分及 HTML 兜底的离线回归测试。"""

import pytest
from bs4 import BeautifulSoup

from wechat_article_parser import ArticleDisplayType, parser


_URL = "https://mp.weixin.qq.com/s/0Wz3JeMbtWBL5iWJgYPS_Q"
_RICH_TEXT = '<div class="rich_media_content"><p>富文本正文</p></div>'
_REPOST = """
<div class="original_page">
  <p id="js_share_notice"><script>notice.innerHTML = "转载附言";</script></p>
  <span id="js_share_source" data-url="https://example.com/original"></span>
</div>
"""
_PLAIN_DATA = """
var TextContentNoEncode = '';
var ContentNoEncode = window.a_value_which_never_exists || '文字正文';
"""
_SWIPER_DATA = """
window.cgiDataNew = {
  picture_page_info_list: [{cdn_url: 'https://mmbiz.qpic.cn/mmbiz_png/body/0'}]
};
window.desc = "轮播正文";
"""
_FULLSCREEN_DATA = """
window.cgiDataNew = {
  picture_page_info_list: [],
  text_page_info: {content: JsDecode('全屏正文')}
};
"""


def _html(body: str = "", script: str = "", title: str = "原标题") -> str:
    return (
        f'<meta property="og:title" content="{title}">'
        f"{body}<script type=\"text/javascript\">{script}</script>"
    )


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        ('var item_show_type = "0";', 0),
        ("window.item_show_type = '8' || '';", 8),
        ("window.item_show_type = 10;", 10),
        ("var /* 注释 */ item_show_type = 5;", 5),
        ("(function() { window.item_show_type = '10'; })();", 10),
        ("window.item_show_type = '999';", 999),
        ("window.item_show_type = '';", None),
        ("window.item_show_type = 'unknown';", None),
        ("window.item_show_type = null;", None),
        ("window.item_show_type = -1;", None),
        ("window.item_show_type = 8.5;", None),
        ("window.item_show_type = 8e2;", None),
        ("window.item_show_type == 8;", None),
        ("var real_item_show_type = '8';", None),
        ("", None),
    ],
)
def test_read_current_article_type(script: str, expected: int | None) -> None:
    soup = BeautifulSoup(_html(script=script), "html.parser")

    assert parser._extract_item_show_type(soup.find_all("script")) == expected


@pytest.mark.parametrize("current_assignment", ["", "window.item_show_type = '8';"])
def test_ignore_type_in_references_strings_comments_and_local_variables(
    current_assignment: str,
) -> None:
    decoys = """
    var reference = {item_show_type: 5};
    var example = "var item_show_type = '5';";
    var url = 'https://example.com/?item_show_type=5';
    var template = `
      window.item_show_type = '5';
    `;
    // window.item_show_type = '5';
    /* var item_show_type = '5'; */
    function report() { var item_show_type = '5'; }
    report.window.item_show_type = '5';
    window.real_item_show_type = '5';
    """
    soup = BeautifulSoup(_html(script=decoys + current_assignment), "html.parser")

    expected = 8 if current_assignment else None
    assert parser._extract_item_show_type(soup.find_all("script")) == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (_RICH_TEXT + _REPOST, "富文本正文"),
        (_REPOST, "转载附言"),
        ('<div class="rich_media_content"></div>' + _REPOST, "转载附言"),
    ],
)
def test_type_zero_uses_html_to_distinguish_rich_text_and_repost(
    body: str, expected: str,
) -> None:
    result = parser._parse_html(_URL, _html(body, 'var item_show_type = "0";'))

    assert result.article_display_type is ArticleDisplayType.ARTICLE
    assert expected in result.article_markdown
    if expected == "转载附言":
        assert "[查看原文](https://example.com/original)" in result.article_markdown
    else:
        assert "转载附言" not in result.article_markdown


@pytest.mark.parametrize(
    ("item_type", "data", "expected", "display_type"),
    [
        (5, _PLAIN_DATA, "文字正文", ArticleDisplayType.VIDEO),
        (8, _SWIPER_DATA, "轮播正文", ArticleDisplayType.IMAGE),
        (10, _PLAIN_DATA, "文字正文", ArticleDisplayType.TEXT),
        (10, _FULLSCREEN_DATA, "全屏正文", ArticleDisplayType.TEXT),
    ],
)
def test_known_type_takes_priority_over_other_html_templates(
    item_type: int, data: str, expected: str, display_type: ArticleDisplayType,
) -> None:
    # 即使存在富文本壳，已知类型仍先读取对应脚本数据；无需专用容器。
    result = parser._parse_html(
        _URL,
        _html(_RICH_TEXT, f"window.item_show_type = '{item_type}';" + data),
    )

    assert expected in result.article_markdown
    assert "富文本正文" not in result.article_markdown
    assert result.article_display_type is display_type
    assert not hasattr(result, "item_show_type")
    if item_type == 8:
        assert result.images == ["https://mmbiz.qpic.cn/mmbiz_png/body/640"]


@pytest.mark.parametrize(
    "declaration",
    ["", "window.item_show_type = '999';", "window.item_show_type = 'invalid';"],
)
def test_missing_unknown_or_invalid_type_falls_back_to_html(declaration: str) -> None:
    result = parser._parse_html(_URL, _html(_RICH_TEXT, declaration))

    assert result.article_markdown == "富文本正文"
    assert result.article_display_type is ArticleDisplayType.UNKNOWN


@pytest.mark.parametrize("item_type", [5, 8, 10])
def test_known_type_without_matching_data_falls_back_to_html(item_type: int) -> None:
    result = parser._parse_html(
        _URL,
        _html(_RICH_TEXT, f"window.item_show_type = '{item_type}';"),
    )

    assert result.article_markdown == "富文本正文"


def test_type_zero_without_matching_html_falls_back_to_other_templates() -> None:
    result = parser._parse_html(
        _URL,
        _html(
            '<div class="share_media_swiper_content"></div>',
            "window.item_show_type = '0';" + _SWIPER_DATA,
        ),
    )

    assert "轮播正文" in result.article_markdown
    assert len(result.images) == 1


def test_failed_branch_does_not_pollute_fallback_result(monkeypatch) -> None:
    def fail_swiper(soup, result):
        result.article_title = "错误标题"
        result.mp_name = "错误账号"
        result.images.append("https://example.com/wrong-image")
        result.article_markdown = "  \n"

    monkeypatch.setattr(parser, "_extract_swiper_content", fail_swiper)
    result = parser._parse_html(
        _URL,
        _html(_RICH_TEXT, "window.item_show_type = '8';"),
    )

    assert result.article_title == "原标题"
    assert result.mp_name == ""
    assert result.images == []
    assert result.article_markdown == "富文本正文"


def test_unrecognized_content_still_returns_metadata() -> None:
    result = parser._parse_html(
        _URL,
        _html(script='window.item_show_type = "999"; window.alias = "account";'),
    )

    assert result.article_title == "原标题"
    assert result.mp_alias == "account"
    assert result.article_display_type is ArticleDisplayType.UNKNOWN
    assert result.article_markdown == ""
    assert not result.is_valid


@pytest.mark.parametrize(
    ("declaration", "expected_type"),
    [
        ("", ArticleDisplayType.UNKNOWN),
        ("window.item_show_type = '5';", ArticleDisplayType.VIDEO),
    ],
)
def test_video_without_description_keeps_type_and_metadata(
    declaration: str, expected_type: ArticleDisplayType,
) -> None:
    metadata = """
    window.__initCgiDataConfig = function(d) {
      return {
        biz: d.biz ? d.biz : 'MQ==',
        nick_name: d.nick_name ? d.nick_name : '测试公众号',
        mid: d.mid ? d.mid : '123',
        idx: d.idx ? d.idx : '1',
        sn: d.sn ? d.sn : 'signature',
        create_time: d.create_time ? d.create_time : '1788860293'
      };
    };
    var TextContentNoEncode = window.a_value_which_never_exists || '';
    var ContentNoEncode = window.a_value_which_never_exists || '';
    """
    result = parser._parse_html(
        _URL,
        _html(
            '<div id="js_common_share_desc_wrap" style="display: none"></div>'
            '<div id="js_fullscreen_layout_padding"></div>',
            declaration + metadata,
        ),
    )

    assert result.article_display_type is expected_type
    assert result.mp_id == 1
    assert result.mp_name == "测试公众号"
    assert result.article_markdown == ""
    assert result.is_valid is (expected_type == ArticleDisplayType.VIDEO)

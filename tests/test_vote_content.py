"""投票题目、选项及异常组件降级的离线回归测试。"""

import html
import json

import pytest

from wechat_article_parser import ArticleDisplayType
from wechat_article_parser.parser import _parse_html


_URL = "https://mp.weixin.qq.com/s/mK2qOjQj2A876oFvCbrkMw"
_NOTICE = "投票内容，请在微信中查看。"
_METADATA = """
var item_show_type = "0";
var biz = "MzA4MTgxNDM5Mg==";
var mid = "2458742088";
var idx = "1";
var sn = "0effdc27c676092d50cefa1a573ff438";
window.__allowLoadResFromMp = true;
var hd_head_img = "https://example.com/publisher-avatar";
var nickname = htmlDecode("WorldNuclearNews");
var oriCreateTime = '1763260614';
"""
_TITLE = "影响中国核电“走出去”的因素"
_OPTIONS = [
    "地缘政治与国际关系", " 核电的经济性", "核电项目的融资", "技术成熟度与可靠性",
    "安全记录与事故应对", "燃料循环与乏燃料处理", "市场与竞争", "国内产业链整合", "人才储备",
]


def _html(body: str, metadata: str = _METADATA) -> str:
    return (
        f'<meta property="og:title" content="投票：{_TITLE}">'
        f'<div class="rich_media_content">{body}</div>'
        '<div id="js_fullscreen_layout_padding"></div>'
        f'<script type="text/javascript">{metadata}</script>'
    )


def _card(subjects: object, body: str = "") -> str:
    data = html.escape(json.dumps(subjects, ensure_ascii=False), quote=True)
    return f'<mp-common-vote data-votesubject="{data}">{body}</mp-common-vote>'


@pytest.mark.parametrize("metadata", [_METADATA, ""])
def test_vote_only_article_extracts_all_options_and_requires_metadata(metadata: str) -> None:
    card = _card([{
        "type": 2, "title": _TITLE,
        "options": [{"name": name, "url": "", "cnt": 287} for name in _OPTIONS],
        "total_cnt": 692,
    }])
    result = _parse_html(_URL, _html(f'<section>{card}</section><p><br></p>', metadata))

    assert result.article_markdown == (
        f'**投票：{_TITLE}**\n\n' + '\n'.join(f'* {name.strip()}' for name in _OPTIONS)
    )
    assert result.images == []
    assert result.is_valid is bool(metadata)
    if metadata:
        assert result.article_display_type is ArticleDisplayType.ARTICLE
        assert result.article_item_show_type == 0
        assert result.mp_name == "WorldNuclearNews"
        assert result.article_msg_id == 2458742088


def test_multiple_subjects_and_cards_preserve_body_order_without_duplicates() -> None:
    card = _card([
        {"title": "第一题", "options": [{"name": "甲"}, {"name": "乙"}]},
        {"title": "第二题", "options": [{"name": "丙"}]},
    ], '<p>重复投票内容</p>')
    result = _parse_html(_URL, _html(
        '<p>开头</p>' + card + '<img data-src="https://example.com/body.jpg">'
        + _card([{"title": "第三题", "options": [{"name": "丁"}]}]) + '<p>结尾</p>'
    ))

    assert result.article_markdown == (
        '开头\n\n**投票：第一题**\n\n* 甲\n* 乙\n\n'
        '**投票：第二题**\n\n* 丙\n\n![](https://example.com/body.jpg)\n\n'
        '**投票：第三题**\n\n* 丁\n\n结尾'
    )
    assert result.images == ["https://example.com/body.jpg"]
    assert result.is_valid


@pytest.mark.parametrize("data", ["", "{broken", "null", "123", '"text"', "{}", "[]",
    '[null, 1, "bad", {}, {"title": [], "options": {}}, {"options": [null, {"name": 1}]}]',
])
@pytest.mark.parametrize("body", ["", "<p>已有题目</p><ul><li>已有选项</li></ul>"])
def test_invalid_vote_data_preserves_existing_text_or_adds_notice(data: str, body: str) -> None:
    card = f'<mp-common-vote data-votesubject="{html.escape(data, quote=True)}">{body}</mp-common-vote>'
    result = _parse_html(_URL, _html('<p>前文</p>' + card + '<p>后文</p>'))
    expected = '已有题目\n\n* 已有选项' if body else _NOTICE

    assert result.article_markdown == f'前文\n\n{expected}\n\n后文'
    assert result.is_valid


def test_missing_attribute_and_empty_rendered_content_use_notice() -> None:
    result = _parse_html(_URL, _html('<mp-common-vote><p> </p><br></mp-common-vote>'))
    assert result.article_markdown == _NOTICE
    assert result.is_valid


def test_partial_subjects_keep_valid_fields_and_skip_invalid_entries() -> None:
    result = _parse_html(_URL, _html(_card([
        None,
        {"title": " 只有题目 ", "options": "bad"},
        {"title": 123, "options": [None, "bad", {"name": []}, {"name": " "}, {"name": " 选项 "}]},
        {"title": " ", "options": []},
    ])))
    assert result.article_markdown == '**投票：只有题目**\n\n**投票**\n\n* 选项'


def test_vote_text_preserves_entities_and_escapes_markdown() -> None:
    result = _parse_html(_URL, _html(_card([{
        "title": 'A & B *题目* <tag>',
        "options": [{"name": '选项_一_ &lt;原文&gt; 100% %20'}, {"name": '<img src="https://example.com/x">'}],
    }])))
    assert result.article_markdown == (
        r'**投票：A & B \*题目\* <tag>**' '\n\n'
        r'* 选项\_一\_ &lt;原文&gt; 100% %20' '\n'
        '* <img src="https://example.com/x">'
    )
    assert result.images == []


def test_vote_outside_body_does_not_fill_empty_article() -> None:
    result = _parse_html(_URL, _html("") + _card([{"title": "页外投票"}]))
    assert result.article_markdown == ""
    assert not result.is_valid


def test_repost_script_body_uses_vote_conversion() -> None:
    card = _card([{"title": "转载题目", "options": [{"name": "选项"}]}])
    page = (
        '<meta property="og:title" content="转载投票">'
        '<div class="original_page"><span id="js_share_source" '
        'data-url="https://example.com/original"></span></div>'
        f'<script type="text/javascript">{_METADATA}</script>'
        '<script type="text/javascript">window.cgiDataNew = '
        f'{{content_noencode: {json.dumps(card, ensure_ascii=False)}}};</script>'
    )
    result = _parse_html(_URL, page)
    assert result.article_markdown == (
        '**投票：转载题目**\n\n* 选项\n\n[查看原文](https://example.com/original)'
    )
    assert result.is_valid

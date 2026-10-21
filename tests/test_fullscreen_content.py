"""全屏文字正文的对象作用域、字段兜底和脚本拆分回归测试。"""

import json

import pytest

from wechat_article_parser import ArticleDisplayType
from wechat_article_parser.parser import _parse_html


_URL = "https://mp.weixin.qq.com/s/YaROYW-2DD-0jOFkE5JCyQ"
_METADATA = """
var item_show_type = "10";
window.__initCgiDataConfig = function(d) {
  return {
    biz: d.biz ? d.biz : 'MQ==',
    nick_name: d.nick_name ? d.nick_name : '测试公众号',
    mid: d.mid ? d.mid : '123',
    idx: d.idx ? d.idx : '1',
    sn: d.sn ? d.sn : 'signature',
    create_time: d.create_time ? d.create_time : '1766656832'
  };
};
"""


def _parse(*scripts: str):
    return _parse_html(_URL,
        '<meta property="og:title" content="文字文章">'
        '<div id="js_fullscreen_layout_padding"></div>'
        + ''.join(f'<script type="text/javascript">{script}</script>' for script in (_METADATA, *scripts)),
    )


@pytest.mark.parametrize("outer_value", ["", "外层错误正文"])
def test_text_page_content_is_not_shadowed_by_outer_field(outer_value: str) -> None:
    result = _parse(
        'window.cgiDataNew = {'
        f'content_noencode: {json.dumps(outer_value)}, picture_page_info_list: [],'
        "text_page_info: {content: '备用正文', content_noencode: '第一行\\x0a第二行'}"
        '};'
    )
    assert result.article_markdown == '第一行  \n第二行'
    assert result.images == []
    assert result.article_display_type is ArticleDisplayType.TEXT
    assert result.mp_name == '测试公众号'
    assert result.article_publish_time == 1766656832
    assert result.is_valid


@pytest.mark.parametrize("preferred", [
    "''", '"   "', "JsDecode('\\x0a')", "'&nbsp;'", "'<p><br></p>'", "'<img>'",
    "null", "{}", "'错误' + other", "JsDecode('错误', other)", "JsDecode('错误') + other",
])
def test_empty_or_unsupported_preferred_field_falls_back_to_content(preferred: str) -> None:
    result = _parse(
        f'window.cgiDataNew = {{text_page_info: {{content_noencode: {preferred}, '
        "content: JsDecode('备用正文')}};"
    )
    assert result.article_markdown == '备用正文'
    assert result.is_valid


def test_nested_fields_and_unrelated_objects_do_not_supply_body() -> None:
    result = _parse(
        "var other = {text_page_info: {content_noencode: '无关对象'}};"
        "window.cgiDataNew = {card: {text_page_info: {content_noencode: '卡片正文'}},"
        "text_page_info: {card: {content_noencode: '嵌套正文'}, content: '真正正文'}};"
    )
    assert result.article_markdown == '真正正文'


def test_strings_comments_and_templates_cannot_supply_fake_text_objects() -> None:
    decoy = "window.cgiDataNew = {text_page_info: {content: '错误正文'}};"
    result = _parse(
        f'var example = {json.dumps(decoy)};\n'
        f'// {decoy}\n/* {decoy} */\nvar template = `{decoy}`;\n'
        "window.cgiDataNew = {'text_page_info': {'content': '正确正文'}};"
    )
    assert result.article_markdown == '正确正文'


@pytest.mark.parametrize("wrapped", [False, True])
def test_escaped_quotes_braces_entities_and_newlines_are_preserved(wrapped: bool) -> None:
    literal = r"'Don\'t 截断 } ]\n第二行 &amp; 内容\u3002'"
    value = f'JsDecode({literal})' if wrapped else literal
    result = _parse(f'window.cgiDataNew = {{text_page_info: {{content_noencode: {value}}}}};')
    assert result.article_markdown == "Don't 截断 } ]  \n第二行 & 内容。"


def test_literal_backslash_hex_escape_is_not_decoded_twice() -> None:
    result = _parse(r"window.cgiDataNew = {text_page_info: {content: '保留 \\x41 原文'}};")
    assert result.article_markdown == r'保留 \x41 原文'


def test_images_and_preferred_body_can_be_split_across_scripts() -> None:
    result = _parse(
        'window.picture_page_info_list = ((window.cgiDataNew && window.cgiDataNew.picture_page_info_list) || []);',
        "window.cgiDataNew = {picture_page_info_list: [], text_page_info: {content_noencode: ''}};",
        "window.cgiDataNew = {picture_page_info_list: [{cdn_url: 'https://example.com/first.jpg'}],"
        "text_page_info: {content: '备用正文'}};",
        'window.cgiDataNew = {"text_page_info": {"content_noencode": "首选正文"}};',
        "window.picture_page_info_list = [{cdn_url: 'https://example.com/first.jpg'},"
        "{cdn_url: 'https://example.com/second.jpg'}];",
        "window.picture_page_info_list = [];",
    )
    assert result.images == ['https://example.com/first.jpg', 'https://example.com/second.jpg']
    assert result.article_markdown == (
        '![](https://example.com/first.jpg)  \n![](https://example.com/second.jpg)\n\n首选正文'
    )
    assert result.is_valid


@pytest.mark.parametrize("script", [
    "window.cgiDataNew = {content_noencode: '只有外层字段'};",
    "window.cgiDataNew = {card: {text_page_info: {content: '嵌套文章'}}};",
    "other.window.cgiDataNew = {text_page_info: {content: '其他对象'}};",
    "window.cgiDataNew = {text_page_info: {content: ''}};",
    "window.cgiDataNew = {text_page_info: {content: '未闭合',",
])
def test_missing_or_empty_text_page_does_not_fabricate_valid_body(script: str) -> None:
    result = _parse(script)
    assert result.article_markdown == ''
    assert not result.is_valid

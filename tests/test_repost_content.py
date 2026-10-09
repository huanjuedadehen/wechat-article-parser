"""转载页面的静态附言、脚本正文及元数据回归测试。"""

import pytest

from wechat_article_parser import ArticleDisplayType
from wechat_article_parser.parser import _parse_html


_URL = "https://mp.weixin.qq.com/s/Pq-JkEjhoIlLvTMzWKVtOw"
_SOURCE = "https://mp.weixin.qq.com/s?__biz=original&mid=456&idx=1&sn=source"
_BODY = """<section>
<p>转载正文第一段，保留 100% 和 %20。</p>
<img data-src="https://mmbiz.qpic.cn/mmbiz_png/first/0?wx_fmt=png&amp;from=appmsg">
<p>正文里的 &lt;tag&gt;、O'Reilly 和反斜杠 \\。</p>
<pre><code>if ready:
    print(&quot;&lt;tag&gt;&quot;)
</code></pre>
<img data-src="https://mmbiz.qpic.cn/mmbiz_png/second/0?wx_fmt=png">
<p>转载正文最后一段。</p>
</section>"""


def _html(data: str = "", notice: str = "分享一篇文章。") -> str:
    # 对应真实页面：正文容器尚未填充，正文和元数据分散在多个脚本。
    return f"""
    <meta property="og:title" content="转载文章标题">
    <div class="original_page">
      <p id="js_share_notice">{notice}</p>
      <div id="js_share_headimg"><img src="https://example.com/avatar"></div>
      <div id="js_content"></div>
      <span id="js_share_source" data-url="{_SOURCE}">阅读全文</span>
    </div>
    <div id="js_fullscreen_layout_padding"></div>
    <script type="text/javascript">
      var biz = "MzAxNjI5NzI4MA==" || "";
      var mid = "2247577355" || "";
      var idx = "4" || "";
      var sn = "signature" || "";
      window.__allowLoadResFromMp = true;
    </script>
    <script type="text/javascript">
      var hd_head_img = "https://example.com/publisher-avatar";
      var nickname = htmlDecode("新浪医药");
      var item_show_type = "0";
      var user_name = "gh_3675b3bc7097";
    </script>
    <script type="text/javascript">
      function setTime() {{ var oriCreateTime = '1791459000'; }}
    </script>
    <script type="text/javascript">{data}</script>
    """


def _js_body(body: str, quote: str = "'") -> str:
    escaped = body.translate(str.maketrans({
        "\\": "\\\\", "'": "\\'", '"': r"\x22", "<": r"\x3c",
        ">": r"\x3e", "&": r"\x26", "\n": r"\n",
    }))
    return quote + escaped + quote


@pytest.mark.parametrize("field", ["content_noencode", "content"])
@pytest.mark.parametrize("quote", ["'", '"'])
def test_static_repost_reads_script_body_and_preserves_metadata(
    field: str, quote: str,
) -> None:
    data = f"""
    window.cgiDataNew = {{
      reference: {{content_noencode: '嵌套的错误正文', content: '嵌套的错误正文'}},
      {quote}{field}{quote}: {_js_body(_BODY, quote)},
      picture_page_info_list: [{{cdn_url: 'https://example.com/wrong-image'}}]
    }};
    """
    result = _parse_html(_URL, _html(data))

    assert result.is_valid
    assert result.article_display_type is ArticleDisplayType.ARTICLE
    assert result.article_item_show_type == 0
    assert result.mp_id == 3016297280
    assert result.mp_name == "新浪医药"
    assert result.mp_user_name == "gh_3675b3bc7097"
    assert result.article_msg_id == 2247577355
    assert result.article_idx == 4
    assert result.article_sn == "signature"
    assert result.article_publish_time == 1791459000
    assert result.images == [
        "https://mmbiz.qpic.cn/mmbiz_png/first/640",
        "https://mmbiz.qpic.cn/mmbiz_png/second/640",
    ]
    markdown = result.article_markdown
    assert markdown.startswith("分享一篇文章。")
    assert "转载正文第一段，保留 100% 和 %20。" in markdown
    assert "正文里的 <tag>、O'Reilly 和反斜杠" in markdown
    assert '```\nif ready:\n    print("<tag>")\n```' in markdown
    assert "转载正文最后一段。" in markdown
    assert markdown.endswith(f"[查看原文]({_SOURCE})")
    assert markdown.count("![") == 2
    assert "![]()" not in markdown
    assert "嵌套的错误正文" not in markdown
    assert "avatar" not in markdown
    assert "wrong-image" not in markdown


def test_static_notice_without_script_body_still_parses() -> None:
    result = _parse_html(_URL, _html())

    assert result.is_valid
    assert result.article_markdown == f"分享一篇文章。\n\n[查看原文]({_SOURCE})"
    assert result.images == []


def test_legacy_script_notice_keeps_body_and_newlines() -> None:
    notice = r'<script>notice.innerHTML = "旧版附言\x0a第二行";</script>'
    result = _parse_html(_URL, _html(notice=notice))

    assert result.is_valid
    assert result.article_markdown == f"旧版附言  \n第二行\n\n[查看原文]({_SOURCE})"


def test_empty_unencoded_body_falls_back_to_content() -> None:
    data = "window.cgiDataNew = {content_noencode: '', content: '<p>备用正文</p>'};"
    result = _parse_html(_URL, _html(data, notice=""))

    assert result.is_valid
    assert result.article_markdown == f"备用正文\n\n[查看原文]({_SOURCE})"


def test_repost_ignores_body_in_comments_strings_and_other_objects() -> None:
    data = """
    // window.cgiDataNew = {content_noencode: '注释中的错误正文'};
    var example = "window.cgiDataNew = {content: '字符串中的错误正文'};";
    other.window.cgiDataNew = {content_noencode: '其他对象中的错误正文'};
    window.cgiDataNew = {
      reference: {content_noencode: '嵌套的错误正文'},
      content_noencode: loadUntrustedContent()
    };
    """
    result = _parse_html(_URL, _html(data))

    assert result.article_markdown == f"分享一篇文章。\n\n[查看原文]({_SOURCE})"

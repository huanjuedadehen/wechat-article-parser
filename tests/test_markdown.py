"""富文本 Markdown 转换的离线回归测试。"""

import pytest

from wechat_article_parser.parser import _parse_html


def _convert(body: str) -> str:
    html = f'<div class="rich_media_content">{body}</div>'
    return _parse_html("https://mp.weixin.qq.com/s/test", html).article_markdown


def test_highlighted_code_preserves_breaks_spaces_and_entities() -> None:
    # 微信 mdnice 代码块：语法高亮 span 切分 token，br 换行，nbsp 占位。
    body = (
        '<pre data-tool="mdnice编辑器"><code>'
        '<span><span># ======== 基础体验 ========</span></span><span><br></span>'
        '<span><span>set</span></span><span>&nbsp;-g default-terminal&nbsp;</span>'
        '<span><span>"tmux-256color"</span></span><span><br></span>'
        '<span>set</span><span>&nbsp;-as terminal-features&nbsp;</span>'
        '<span>",*:RGB"</span><span><br></span>'
        '<span>set</span><span>&nbsp;-g mouse on &nbsp; &nbsp;</span>'
        '<span># 支持鼠标操作</span><span><br></span><span><br></span>'
        '<span>&nbsp;&nbsp;echo &quot;&lt;tag&gt;&quot; &amp;&amp; echo &#160;ok</span>'
        '</code></pre>'
    )

    assert _convert(body) == (
        '```\n'
        '# ======== 基础体验 ========\n'
        'set -g default-terminal "tmux-256color"\n'
        'set -as terminal-features ",*:RGB"\n'
        'set -g mouse on    # 支持鼠标操作\n\n'
        '  echo "<tag>" && echo  ok\n'
        '```'
    )


def test_plain_pre_preserves_indentation_and_blank_lines() -> None:
    assert _convert('<pre><code>if ready:\n    run()\n\n    done()\n</code></pre>') == (
        '```\nif ready:\n    run()\n\n    done()\n```'
    )


@pytest.mark.parametrize("cell", ["td", "th"])
def test_table_pipes_in_text_and_inline_code_are_escaped(cell: str) -> None:
    output = _convert(
        f'<table><tr><{cell}>A | B</{cell}><{cell}><section>'
        '<span>验证 </span><code><span>tailscale status | grep peer-relay</span></code>'
        f'</section></{cell}></tr></table>'
    )

    assert r'A \| B' in output
    assert r'`tailscale status \| grep peer-relay`' in output
    # 每行仍然只有两个单元格（三个未转义的分隔符）。
    assert all(line.replace(r'\|', '').count('|') == 3 for line in output.splitlines())


def test_pipe_outside_table_is_unchanged() -> None:
    assert _convert('<p><code>left | right</code></p><pre>left | right</pre>') == (
        '`left | right`\n\n```\nleft | right\n```'
    )


def test_inline_spans_and_paragraph_breaks_preserve_spacing() -> None:
    assert _convert(
        '<p><span>hello </span><span>world</span><br><span>next line</span></p>'
    ) == 'hello world  \nnext line'


def test_bold_reference_stays_inline() -> None:
    assert _convert(
        '<ul><li><section><strong><span>Hermes</span><sup>'
        '<a href="https://example.com/hermes">[1]</a></sup></strong>'
        '<span>：Nous Research 的自主 AI Agent</span></section></li></ul>'
    ) == '* **Hermes[[1]](https://example.com/hermes)**：Nous Research 的自主 AI Agent'


def test_literal_asterisks_in_source_stay_literal_and_inline() -> None:
    # 这篇原文没有 strong 标签；不能把普通星号自动猜测为加粗语义。
    assert _convert(
        '<ul><li><section><span>**</span><span>Hermes</span>'
        '<sup><span>[1]</span></sup><span>**：Nous Research 的自主 AI Agent</span>'
        '</section></li></ul>'
    ) == r'* \*\*Hermes[1]\*\*：Nous Research 的自主 AI Agent'

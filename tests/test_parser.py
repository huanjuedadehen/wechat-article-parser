"""使用真实微信公众号文章链接测试 wechat_article_parser。"""

import pytest

from wechat_article_parser import ArticleResult, WeChatVerifyError, parse, parse_async

TEST_URLS = [
    "https://mp.weixin.qq.com/s/OkKlPnSbLOP9J3heC0CaPw",
    "https://mp.weixin.qq.com/s/z7zNi_DayzevcTe0EUTv5g",
    "https://mp.weixin.qq.com/s/9NjneDOJiteXBM9Cupb9Ig",
    "https://mp.weixin.qq.com/s/0Wz3JeMbtWBL5iWJgYPS_Q",
    "https://mp.weixin.qq.com/s/DmZXjgIzq5gBo3H-YtcjVw",
    "https://mp.weixin.qq.com/s/80bysSCadvy9VbaovXBv2g",
    "https://mp.weixin.qq.com/s/sfwGsafriO9sm6PfbQVXhw",
    "https://mp.weixin.qq.com/s/h8E6riExCaH2Znmnprj-WQ",
    "https://mp.weixin.qq.com/s/ySQdtsRlRmAl_skdc5HQ-A",
    "https://mp.weixin.qq.com/s/MnkArbYQNp3tF29gujMUnQ",
    "https://mp.weixin.qq.com/s/ncPoZnxKdvDRLM_s4DBgmA",
    # 转载页面的静态附言及脚本正文。
    "https://mp.weixin.qq.com/s/Pq-JkEjhoIlLvTMzWKVtOw",
    "https://mp.weixin.qq.com/s/X51M6PfionI6UpX4zsG78Q",
    # 视频号卡片和微信视频 iframe 的纯视频正文。
    "https://mp.weixin.qq.com/s/wAyM7yYKDfTH21-XpS9agQ",
    "https://mp.weixin.qq.com/s/a7P56VOipWNB0UyNaVOZYQ",
    # 付费受限正文。
    "https://mp.weixin.qq.com/s/n2q09-I95zwggfbXKAmbuQ",
    # SVG foreignObject 承载的正文图片。
    "https://mp.weixin.qq.com/s/3ixeC9whuEgpup2G1yvDZg",
    # 纯公众号推荐卡片正文。
    "https://mp.weixin.qq.com/s/PXZuh3fFEi3VXUUI1uBnlw",
    # 无文字正文的音频分享。
    "https://mp.weixin.qq.com/s/y4QxlYs7u0X9TdvZatCfIA",
    # 纯商品广告卡片正文。
    "https://mp.weixin.qq.com/s/CBmoIFPJwV4BkidYGp-l1Q",
    # 纯小程序卡片正文。
    "https://mp.weixin.qq.com/s/qs2YxgdwWDplsmb6H8OS-w",
]


@pytest.mark.parametrize("url", TEST_URLS)
def test_parse_sync(url: str, proxy: str | None) -> None:
    try:
        result = parse(url, proxy=proxy)
    except WeChatVerifyError:
        pytest.skip("WeChat returned verification page (IP rate-limited)")
        return
    _assert_result(result, url)


@pytest.mark.parametrize("url", TEST_URLS)
@pytest.mark.asyncio
async def test_parse_async(url: str, proxy: str | None) -> None:
    try:
        result = await parse_async(url, proxy=proxy)
    except WeChatVerifyError:
        pytest.skip("WeChat returned verification page (IP rate-limited)")
        return
    _assert_result(result, url)


def _assert_result(result: ArticleResult, url: str) -> None:
    print(f"\n{'='*60}")
    print(f"URL: {url}")
    print(f"公众号ID(B64):{result.mp_id_b64}")
    print(f"公众号ID:     {result.mp_id}")
    print(f"公众号名称:   {result.mp_name}")
    print(f"公众号别名:   {result.mp_alias}")
    print(f"公众号用户名: {result.mp_user_name}")
    print(f"账号类型:     {result.mp_account_type}")
    print(
        f"公众号图片:   {result.mp_image[:80]}..."
        if result.mp_image
        else "公众号图片:   (empty)"
    )
    print(
        f"公众号简介:   {result.mp_description[:80]}"
        if result.mp_description
        else "公众号简介:   (empty)"
    )
    print(f"文章ID:       {result.article_id}")
    print(f"群发消息ID:   {result.article_msg_id}")
    print(f"文章idx:      {result.article_idx}")
    print(f"文章签名:     {result.article_sn}")
    print(f"文章标题:     {result.article_title}")
    print(f"展示类型:     {result.article_display_type}")
    print(f"原始展示类型: {result.article_item_show_type}")
    print(
        f"封面图:       {result.article_cover_image[:80]}..."
        if result.article_cover_image
        else "封面图:       (empty)"
    )
    print(
        f"文章摘要:     {result.article_description[:80]}"
        if result.article_description
        else "文章摘要:     (empty)"
    )
    print(f"发布时间:     {result.article_publish_time}")
    print(f"Markdown长度: {len(result.article_markdown)}")
    print(f"Markdown预览: {result.article_markdown[:200]}")
    print(f"有效性:       {result.is_valid}")
    print(f"{'='*60}")

    assert result.mp_id > 0, "mp_id should be positive"
    assert result.mp_name, "mp_name should not be empty"
    assert result.mp_user_name, "mp_user_name should not be empty for these reference articles"
    assert result.article_id, "article_id should not be empty"
    assert result.article_msg_id > 0, "article_msg_id should be positive"
    assert result.article_idx > 0, "article_idx should be positive"
    assert result.article_sn, "article_sn should not be empty"
    assert result.article_title, "article_title should not be empty"
    if result.article_display_type not in ("video", "audio"):
        assert result.article_markdown, "article_markdown should not be empty for non-video/audio articles"
    assert result.article_publish_time > 0, "article_publish_time should be positive"
    assert result.is_valid


def test_fetch_all(url: str, proxy: str | None) -> None:
    """抓取指定 URL 并打印所有采集到的参数。

    用法: pytest tests/test_parser.py::test_fetch_all -s --url <URL> [--proxy <PROXY>]
    """
    result = parse(url, proxy=proxy)
    print(f"\n{'='*60}")
    print(f"URL:          {url}")
    print(f"公众号ID(B64):{result.mp_id_b64}")
    print(f"公众号ID:     {result.mp_id}")
    print(f"公众号名称:   {result.mp_name}")
    print(f"公众号别名:   {result.mp_alias}")
    print(f"公众号用户名: {result.mp_user_name}")
    print(f"账号类型:     {result.mp_account_type}")
    print(f"公众号图片:   {result.mp_image}")
    print(f"公众号简介:   {result.mp_description}")
    print(f"文章ID:       {result.article_id}")
    print(f"群发消息ID:   {result.article_msg_id}")
    print(f"文章idx:      {result.article_idx}")
    print(f"文章签名:     {result.article_sn}")
    print(f"文章标题:     {result.article_title}")
    print(f"展示类型:     {result.article_display_type}")
    print(f"原始展示类型: {result.article_item_show_type}")
    print(f"封面图:       {result.article_cover_image}")
    print(f"文章摘要:     {result.article_description}")
    print(f"发布时间:     {result.article_publish_time}")
    print(f"图片列表({len(result.images)}张):")
    for i, img in enumerate(result.images, 1):
        print(f"  {i}. {img}")
    print(f"Markdown内容:\n{result.article_markdown}")
    print(f"有效性:       {result.is_valid}")
    print(f"{'='*60}")


def test_fetch_markdown(url: str, proxy: str | None) -> None:
    """抓取指定 URL 并只打印 Markdown 内容。

    用法: pytest tests/test_parser.py::test_fetch_markdown -s --url <URL> [--proxy <PROXY>]
    """
    result = parse(url, proxy=proxy)
    print(f"\n{result.article_markdown}")


def test_fetch_raw_html(url: str, proxy: str | None) -> None:
    """抓取指定 URL 并打印原始 HTML 网页源代码。

    用法: pytest tests/test_parser.py::test_fetch_raw_html -s --url <URL> [--proxy <PROXY>]
    """
    result = parse(url, proxy=proxy, include_raw_html=True)
    assert result.raw_html, "raw_html should not be empty when include_raw_html=True"
    print(f"\n{'='*60}")
    print(f"URL:        {url}")
    print(f"raw_html长度: {len(result.raw_html)}")
    print(f"{'='*60}")
    print(result.raw_html)

"""使用真实微信公众号文章链接测试 wechat_article_parser。"""

import pytest

from wechat_article_parser import ArticleResult, WeChatVerifyError, parse, parse_async

TEST_URLS = [
    "https://mp.weixin.qq.com/s/OkKlPnSbLOP9J3heC0CaPw",
    "https://mp.weixin.qq.com/s/z7zNi_DayzevcTe0EUTv5g",
    "https://mp.weixin.qq.com/s/9NjneDOJiteXBM9Cupb9Ig",
    "https://mp.weixin.qq.com/s/0Wz3JeMbtWBL5iWJgYPS_Q",
    "https://mp.weixin.qq.com/s/DmZXjgIzq5gBo3H-YtcjVw",
]


@pytest.mark.parametrize("url", TEST_URLS)
def test_parse_sync(url: str) -> None:
    try:
        result = parse(url)
    except WeChatVerifyError:
        pytest.skip("WeChat returned verification page (IP rate-limited)")
        return
    _assert_result(result, url)


@pytest.mark.parametrize("url", TEST_URLS)
@pytest.mark.asyncio
async def test_parse_async(url: str) -> None:
    try:
        result = await parse_async(url)
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
    print(f"公众号图片:   {result.mp_image[:80]}..." if result.mp_image else "公众号图片:   (empty)")
    print(f"公众号简介:   {result.mp_description[:80]}" if result.mp_description else "公众号简介:   (empty)")
    print(f"文章ID:       {result.article_id}")
    print(f"群发消息ID:   {result.article_msg_id}")
    print(f"文章idx:      {result.article_idx}")
    print(f"文章签名:     {result.article_sn}")
    print(f"文章标题:     {result.article_title}")
    print(f"封面图:       {result.article_cover_image[:80]}..." if result.article_cover_image else "封面图:       (empty)")
    print(f"文章摘要:     {result.article_description[:80]}" if result.article_description else "文章摘要:     (empty)")
    print(f"发布时间:     {result.article_publish_time}")
    print(f"Markdown长度: {len(result.article_markdown)}")
    print(f"Markdown预览: {result.article_markdown[:200]}")
    print(f"有效性:       {result.is_valid}")
    print(f"{'='*60}")

    assert result.mp_id > 0, "mp_id should be positive"
    assert result.mp_name, "mp_name should not be empty"
    assert result.article_id, "article_id should not be empty"
    assert result.article_msg_id > 0, "article_msg_id should be positive"
    assert result.article_idx > 0, "article_idx should be positive"
    assert result.article_sn, "article_sn should not be empty"
    assert result.article_title, "article_title should not be empty"
    assert result.article_markdown, "article_markdown should not be empty"
    assert result.article_publish_time > 0, "article_publish_time should be positive"
    assert result.is_valid


def test_fetch_all(url: str) -> None:
    """抓取指定 URL 并打印所有采集到的参数。

    用法: pytest tests/test_parser.py::test_fetch_all -s --url <URL>
    """
    result = parse(url)
    print(f"\n{'='*60}")
    print(f"URL:          {url}")
    print(f"公众号ID(B64):{result.mp_id_b64}")
    print(f"公众号ID:     {result.mp_id}")
    print(f"公众号名称:   {result.mp_name}")
    print(f"公众号别名:   {result.mp_alias}")
    print(f"公众号图片:   {result.mp_image}")
    print(f"公众号简介:   {result.mp_description}")
    print(f"文章ID:       {result.article_id}")
    print(f"群发消息ID:   {result.article_msg_id}")
    print(f"文章idx:      {result.article_idx}")
    print(f"文章签名:     {result.article_sn}")
    print(f"文章标题:     {result.article_title}")
    print(f"封面图:       {result.article_cover_image}")
    print(f"文章摘要:     {result.article_description}")
    print(f"发布时间:     {result.article_publish_time}")
    print(f"图片列表({len(result.images)}张):")
    for i, img in enumerate(result.images, 1):
        print(f"  {i}. {img}")
    print(f"Markdown内容:\n{result.article_markdown}")
    print(f"有效性:       {result.is_valid}")
    print(f"{'='*60}")


def test_fetch_markdown(url: str) -> None:
    """抓取指定 URL 并只打印 Markdown 内容。

    用法: pytest tests/test_parser.py::test_fetch_markdown -s --url <URL>
    """
    result = parse(url)
    print(f"\n{result.article_markdown}")

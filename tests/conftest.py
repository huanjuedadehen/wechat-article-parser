import pytest


def pytest_addoption(parser):
    parser.addoption("--url", default=None, help="微信公众号文章链接")
    parser.addoption("--proxy", default=None, help="HTTP 代理地址，例如 http://127.0.0.1:7890")


@pytest.fixture
def url(request):
    value = request.config.getoption("--url")
    if not value:
        pytest.skip("需要通过 --url 参数传入链接")
    return value


@pytest.fixture
def proxy(request):
    return request.config.getoption("--proxy")

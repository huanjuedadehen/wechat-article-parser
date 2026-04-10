import pytest


def pytest_addoption(parser):
    parser.addoption("--url", default=None, help="微信公众号文章链接")


@pytest.fixture
def url(request):
    value = request.config.getoption("--url")
    if not value:
        pytest.skip("需要通过 --url 参数传入链接")
    return value

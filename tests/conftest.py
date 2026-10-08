import os

import pytest

# urllib3 probes AF_INET6 once, at import time, and catches failure.
# Import it before tests disable sockets so that probe is not a test warning.
import urllib3  # noqa: F401

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")


@pytest.fixture(autouse=True)
def _block_network(socket_disabled):
    """Fail any test that opens a socket. Analyzers must mock HTTP clients."""
    return socket_disabled


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()

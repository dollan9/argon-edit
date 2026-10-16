"""Pytest fixtures and configuration for Argon Video Engine tests.

Automatically spins up the Mock Adobe CEP server cluster on localhost:8088, 8089, 8090
so that tests run 100% offline in CI/CD without Adobe Creative Cloud installed.
"""

import pytest
from typing import Generator
from tests.mock_adobe_server import MockAdobeCluster


@pytest.fixture(scope="session", autouse=True)
def mock_adobe_cluster() -> Generator[MockAdobeCluster, None, None]:
    """Session-wide fixture running mock Adobe bridge servers on ports 8088, 8089, 8090."""
    cluster = MockAdobeCluster(ports=[8088, 8089, 8090])
    cluster.start()
    yield cluster
    cluster.stop()

"""FoxESS tests configuration."""

from collections.abc import Generator
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Make `custom_components` importable when pytest runs from the repo root.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from homeassistant.core import HomeAssistant

pytest_plugins = ["tests.conftest"]

DOMAIN = "foxess"

MOCK_CONFIG = {
    "name": "FoxESS",
    "apiKey": "test-api-key",
    "deviceSN": "ABC123456789",
    "deviceID": "ABC123456789",
}


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.foxess.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock

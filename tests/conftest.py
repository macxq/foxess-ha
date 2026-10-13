"""FoxESS tests configuration."""

from collections.abc import Generator
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant

sys.path.insert(0, str(Path(__file__).parent))

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

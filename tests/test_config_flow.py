"""Tests for the FoxESS config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientError
from conftest import DOMAIN, MOCK_CONFIG
from custom_components.foxess.config_flow import _fetch_device_list
import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from tests.common import MockConfigEntry

MOCK_DEVICES = [
    {
        "deviceSN": "FAKE_DEVICE_SN",
        "deviceType": "H3-Pro-3G",
        "productType": "H3",
        "status": 1,
    }
]

STEP1_INPUT = {"apiKey": "test-api-key"}

STEP2_INPUT = {
    "deviceSN": "FAKE_DEVICE_SN",
    CONF_NAME: "My Inverter",
}


def _patch_fetch_device_list(return_value: tuple) -> object:
    return patch(
        "custom_components.foxess.config_flow._fetch_device_list",
        return_value=return_value,
    )


# ---------------------------------------------------------------------------
# Step 1 — API key entry
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_show_form_step1(hass: HomeAssistant) -> None:
    """Step 1 form is shown on initial load."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_step1_invalid_auth(hass: HomeAssistant) -> None:
    """An invalid API key re-shows step 1 with invalid_auth error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with _patch_fetch_device_list(([], "invalid_auth")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], STEP1_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_step1_cannot_connect(hass: HomeAssistant) -> None:
    """A connection failure re-shows step 1 with cannot_connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with _patch_fetch_device_list(([], "cannot_connect")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], STEP1_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_step1_no_devices(hass: HomeAssistant) -> None:
    """An empty device list re-shows step 1 with no_devices error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with _patch_fetch_device_list(([], "no_devices")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], STEP1_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "no_devices"}


# ---------------------------------------------------------------------------
# Step 2 — device selection
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_step2_shown_after_valid_api_key(hass: HomeAssistant) -> None:
    """After a valid API key, step 2 (device selector) is shown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with _patch_fetch_device_list((MOCK_DEVICES, None)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], STEP1_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"
    assert not result["errors"]


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_create_entry(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Full happy path through both steps creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with _patch_fetch_device_list((MOCK_DEVICES, None)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], STEP1_INPUT
        )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], STEP2_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == STEP2_INPUT["deviceSN"]
    assert result["data"] == {
        "apiKey": STEP1_INPUT["apiKey"],
        "deviceSN": STEP2_INPUT["deviceSN"],
        "deviceID": STEP2_INPUT["deviceSN"],
        CONF_NAME: STEP2_INPUT[CONF_NAME],
    }
    assert result["result"].unique_id == STEP2_INPUT["deviceSN"]
    mock_setup_entry.assert_called_once()


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_create_entry_default_name(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Omitting the name field uses the default 'FoxESS'."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with _patch_fetch_device_list((MOCK_DEVICES, None)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], STEP1_INPUT
        )

    step2_no_name = {"deviceSN": STEP2_INPUT["deviceSN"]}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], step2_no_name
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_NAME] == "FoxESS"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_id_set_to_device_sn(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """The deviceID is automatically set equal to deviceSN in the config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with _patch_fetch_device_list((MOCK_DEVICES, None)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], STEP1_INPUT
        )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], STEP2_INPUT
    )
    await hass.async_block_till_done()

    assert result["data"]["deviceID"] == result["data"]["deviceSN"]


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_duplicate_device_aborts(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Configuring the same deviceSN a second time aborts with already_configured."""
    # First successful setup
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with _patch_fetch_device_list((MOCK_DEVICES, None)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], STEP1_INPUT
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], STEP2_INPUT
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY

    # Second attempt with same device
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with _patch_fetch_device_list((MOCK_DEVICES, None)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], STEP1_INPUT
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], STEP2_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# _fetch_device_list unit tests
# ---------------------------------------------------------------------------


def _make_mock_session(*, status: int = 200, json_return_value: object = None) -> MagicMock:
    """Return a mock aiohttp session whose response returns the given status and JSON."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_return_value)
    mock_session = MagicMock()
    mock_session.post = AsyncMock(return_value=mock_resp)
    return mock_session


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_fetch_device_list_success(hass: HomeAssistant) -> None:
    """Errno 0 with a non-empty device list returns (devices, None)."""
    response = {
        "errno": 0,
        "result": {"data": MOCK_DEVICES},
    }
    with patch(
        "custom_components.foxess.config_flow.async_get_clientsession",
        return_value=_make_mock_session(json_return_value=response),
    ):
        devices, error = await _fetch_device_list(hass, "valid-key")

    assert error is None
    assert devices == MOCK_DEVICES


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_fetch_device_list_invalid_auth_401(hass: HomeAssistant) -> None:
    """An HTTP 401 response maps to invalid_auth."""
    with patch(
        "custom_components.foxess.config_flow.async_get_clientsession",
        return_value=_make_mock_session(status=401),
    ):
        devices, error = await _fetch_device_list(hass, "bad-key")

    assert error == "invalid_auth"
    assert devices == []


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_fetch_device_list_unknown_errno(hass: HomeAssistant) -> None:
    """An unrecognised errno falls back to cannot_connect."""
    with patch(
        "custom_components.foxess.config_flow.async_get_clientsession",
        return_value=_make_mock_session(json_return_value={"errno": 99999}),
    ):
        devices, error = await _fetch_device_list(hass, "any-key")

    assert error == "cannot_connect"
    assert devices == []


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_fetch_device_list_empty_data(hass: HomeAssistant) -> None:
    """A successful response with an empty device list returns no_devices."""
    response = {"errno": 0, "result": {"data": []}}
    with patch(
        "custom_components.foxess.config_flow.async_get_clientsession",
        return_value=_make_mock_session(json_return_value=response),
    ):
        devices, error = await _fetch_device_list(hass, "any-key")

    assert error == "no_devices"
    assert devices == []


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_fetch_device_list_client_error(hass: HomeAssistant) -> None:
    """A ClientError maps to cannot_connect."""
    mock_session = MagicMock()
    mock_session.post = AsyncMock(side_effect=ClientError())
    with patch(
        "custom_components.foxess.config_flow.async_get_clientsession",
        return_value=mock_session,
    ):
        devices, error = await _fetch_device_list(hass, "any-key")

    assert error == "cannot_connect"
    assert devices == []


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_fetch_device_list_non_dict_response(hass: HomeAssistant) -> None:
    """A non-dict JSON body maps to cannot_connect."""
    with patch(
        "custom_components.foxess.config_flow.async_get_clientsession",
        return_value=_make_mock_session(json_return_value=None),
    ):
        devices, error = await _fetch_device_list(hass, "any-key")

    assert error == "cannot_connect"
    assert devices == []


# ---------------------------------------------------------------------------
# Reauth tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_reauth_form_shown(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """The reauth_confirm form is shown when reauth is initiated."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MOCK_CONFIG["deviceSN"], data=MOCK_CONFIG)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_reauth_success(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """A valid new API key updates the entry and reloads."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MOCK_CONFIG["deviceSN"], data=MOCK_CONFIG)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    with _patch_fetch_device_list((MOCK_DEVICES, None)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"apiKey": "new-valid-api-key"}
        )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["apiKey"] == "new-valid-api-key"


@pytest.mark.usefixtures("enable_custom_integrations", "mock_setup_entry")
async def test_reauth_success_no_devices(hass: HomeAssistant) -> None:
    """A valid key that returns no devices still succeeds reauth."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MOCK_CONFIG["deviceSN"], data=MOCK_CONFIG)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    with _patch_fetch_device_list(([], "no_devices")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"apiKey": "new-valid-api-key"}
        )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["apiKey"] == "new-valid-api-key"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_reauth_invalid_key(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """An invalid API key re-shows the reauth form with an error."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MOCK_CONFIG["deviceSN"], data=MOCK_CONFIG)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    with _patch_fetch_device_list(([], "invalid_auth")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"apiKey": "bad-api-key"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_reauth_cannot_connect(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """A connection error re-shows the reauth form so the user can retry."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=MOCK_CONFIG["deviceSN"], data=MOCK_CONFIG)
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    with _patch_fetch_device_list(([], "cannot_connect")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"apiKey": "any-api-key"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "cannot_connect"}

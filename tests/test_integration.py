"""End-to-end tests against the fake portal."""


from datetime import date
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bchydro.api import BCHydroApi, BCHydroData, BCHydroError
from custom_components.bchydro.const import DOMAIN


async def test_api_parses_everything(fake_bchydro):
    data = await BCHydroApi("me@example.com", "good").async_fetch()
    assert data.latest.day == date(2026, 10, 12)
    assert data.latest.kwh == 14.30 and data.latest.cost == 1.93
    assert len(data.daily) == 2  # estimated point skipped
    assert data.billing_start == date(2026, 9, 10)
    assert data.billing_end == date(2026, 11, 9)
    assert data.cost_to_date == 59.02 and data.projected_cost == 114.0
    assert data.days_since_billing == 33
    assert data.balance == 0.0
    assert data.last_bill_amount == 163.54 and data.last_bill_date == "Sep 11, 2026"


async def test_config_flow_bad_then_good(hass: HomeAssistant, fake_bchydro):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "me@example.com", CONF_PASSWORD: "bad"}
    )
    assert result["errors"] == {"base": "invalid_auth"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "me@example.com", CONF_PASSWORD: "good"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert hass.states.get("sensor.bc_hydro_yesterday_consumption").state == "14.3"
    yc = hass.states.get("sensor.bc_hydro_yesterday_consumption")
    assert yc.attributes["date"] == "2026-10-12"
    assert hass.states.get("sensor.bc_hydro_yesterday_cost").state == "1.93"
    assert hass.states.get("sensor.bc_hydro_projected_cost").state == "114.0"
    assert hass.states.get("sensor.bc_hydro_billing_period_end").state == "2026-11-09"
    assert hass.states.get("sensor.bc_hydro_last_bill_amount").state == "163.54"


async def test_refreshes_daily_at_1am(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    await hass.config.async_set_time_zone("America/Vancouver")
    freezer.move_to("2026-10-13 14:00:00-07:00")
    with patch.object(BCHydroApi, "async_fetch", return_value=BCHydroData()) as fetch:
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id="me@example.com",
            data={CONF_USERNAME: "me@example.com", CONF_PASSWORD: "good"},
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert fetch.call_count == 1

        # Nothing happens during the day...
        now = dt_util.parse_datetime("2026-10-13 23:59:00-07:00")
        freezer.move_to(now)
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        assert fetch.call_count == 1

        # ...one scrape at 1 am.
        now = dt_util.parse_datetime("2026-10-14 01:00:00-07:00")
        freezer.move_to(now)
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        assert fetch.call_count == 2


async def test_failed_1am_scrape_retries(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    await hass.config.async_set_time_zone("America/Vancouver")
    freezer.move_to("2026-10-13 14:00:00-07:00")
    with patch.object(BCHydroApi, "async_fetch", return_value=BCHydroData()) as fetch:
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id="me@example.com",
            data={CONF_USERNAME: "me@example.com", CONF_PASSWORD: "good"},
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        fetch.side_effect = BCHydroError("site down")
        now = dt_util.parse_datetime("2026-10-14 01:00:00-07:00")
        freezer.move_to(now)
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        assert fetch.call_count == 2

        fetch.side_effect = None
        now = dt_util.parse_datetime("2026-10-14 02:00:01-07:00")
        freezer.move_to(now)
        async_fire_time_changed(hass, now)
        await hass.async_block_till_done()
        assert fetch.call_count == 3
        assert hass.states.get("sensor.bc_hydro_yesterday_consumption").state == "unknown"

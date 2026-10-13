# BC Hydro for Home Assistant

A custom integration that logs in to your BC Hydro account (app.bchydro.com) once a day at 1 am and exposes yesterday's electricity use and cost, plus billing-period totals, as Home Assistant sensors.

BC Hydro has no public API for customers, so this scrapes the same data the website's consumption page shows. It only runs once a day.

## Install with HACS

1. In Home Assistant, open **HACS**, then the three-dot menu, then **Custom repositories**.
2. Repository: `https://github.com/errorkallu/ha-bcelectricity`, type **Integration**, then **Add**.
3. Search HACS for **BC Hydro**, download it, and restart Home Assistant.
4. Go to **Settings > Devices & services > Add integration > BC Hydro** and enter your BC Hydro email and password.

## Sensors

| Sensor | What it is |
| --- | --- |
| Yesterday consumption | kWh for the most recent day BC Hydro has posted (normally yesterday). Attributes: `date`, `last_7_days` |
| Yesterday cost | Estimated cost of that day, in CAD |
| Consumption this billing period | kWh so far this billing period (`total_increasing`, usable in the Energy dashboard) |
| Cost this billing period | CAD so far this billing period |
| Projected consumption / Projected cost | BC Hydro's estimate for the full billing period |
| Billing period start / end | Dates of the current billing period |
| Balance | Account balance shown on the account summary (if the page provides it) |
| Last bill amount | Most recent bill amount, with `bill_date` attribute (if the page provides it) |

Costs are BC Hydro's estimates and exclude taxes and fees, the same as on the website.

## Schedule

Data is fetched when the integration starts and then every day at 1:00 am (Home Assistant's time zone). If the 1 am fetch fails, it retries every hour up to three times. To fetch on demand, call `homeassistant.update_entity` on any BC Hydro sensor.

## Troubleshooting

Turn on debug logging to see what the scraper gets back:

```yaml
logger:
  logs:
    custom_components.bchydro: debug
```

You can also run the scraper on its own, outside Home Assistant:

```sh
pip install aiohttp
python scripts/test_api.py
```

## Credit

The login and data endpoints follow [emcniece/bchydro](https://github.com/emcniece/bchydro).

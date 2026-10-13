"""Try the BC Hydro scraper outside Home Assistant.

    pip install aiohttp
    BCH_USER=you@example.com BCH_PASS='secret' python scripts/test_api.py

Credentials come from the environment only; nothing is saved.
"""

import asyncio
import getpass
import importlib.util
import logging
import os
import pathlib

logging.basicConfig(level=logging.DEBUG if os.getenv("DEBUG") else logging.INFO)

# Load api.py directly so Home Assistant doesn't need to be installed.
_path = pathlib.Path(__file__).parents[1] / "custom_components/bchydro/api.py"
_spec = importlib.util.spec_from_file_location("bchydro_api", _path)
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)


async def main() -> None:
    user = os.getenv("BCH_USER") or input("BC Hydro email: ")
    password = os.getenv("BCH_PASS") or getpass.getpass("BC Hydro password: ")
    data = await api.BCHydroApi(user, password).async_fetch()
    latest = data.latest
    print(f"Account:              {data.account_number}")
    print(f"Billing period:       {data.billing_start} to {data.billing_end}")
    if latest:
        print(f"Latest day:           {latest.day}  {latest.kwh} kWh  ${latest.cost}")
    print(f"Consumption to date:  {data.consumption_to_date} kWh")
    print(f"Cost to date:         ${data.cost_to_date}")
    print(f"Projected:            {data.projected_consumption} kWh  ${data.projected_cost}")
    print(f"Balance:              {data.balance}")
    print(f"Last bill:            {data.last_bill_amount} ({data.last_bill_date})")
    print(f"Days of data:         {len(data.daily)}")


asyncio.run(main())

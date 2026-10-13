"""Fixtures: a fake BC Hydro portal served locally."""

import pytest
from aiohttp import web

from custom_components.bchydro import api

LOGIN_HTML = """<html><body>
<input type="hidden" name="bchydroparam" value="tok123"/>
<h1>Account summary</h1>
<div>Balance</div><div>$0.00</div>
<p>Withdrawal date: Sep 15, 2026</p>
<p>My bill amount for Sep 11, 2026: $163.54</p>
</body></html>"""

ACCOUNT_JSON = {
    "evpSlid": "1", "evpAccount": "9197473", "evpAccountId": "x", "evpProfileId": "p",
    "evpRateGroup": "RES1", "evpBillingStart": "2026-09-10T00:00:00-07:00",
    "evpBillingEnd": "2026-11-09T00:00:00-08:00", "evpConsToDate": "433.56",
    "evpCostToDate": "59.02", "evpEstConsCurPeriod": "830", "evpEstCostCurPeriod": "114.00",
}

CONSUMPTION_XML = """<?xml version="1.0"?>
<Data><Series name="current">
<Point dateTime="2026-10-11T00:00:00-07:00" endTime="2026-10-12T00:00:00-07:00" quality="ACTUAL" value="15.19" cost="2.03" type="CONSUMPTION"/>
<Point dateTime="2026-10-12T00:00:00-07:00" endTime="2026-10-13T00:00:00-07:00" quality="ACTUAL" value="14.30" cost="1.93" type="CONSUMPTION"/>
<Point dateTime="2026-10-13T00:00:00-07:00" endTime="2026-10-14T00:00:00-07:00" quality="ESTIMATED" value="3.1" cost="0.40" type="CONSUMPTION"/>
</Series>
<Rates daysSince="33" cons2date="433.56" cost2date="59.02" estCons="830" estCost="114.00"/>
</Data>"""


@pytest.fixture
async def fake_bchydro(socket_enabled, aiohttp_server, monkeypatch):
    """Point the scraper at a local server; yields a dict of request counters."""
    state = {"logins": 0, "bad_password": False}

    async def login(request):
        form = await request.post()
        state["logins"] += 1
        if form["password"] != "good":
            return web.Response(text="<html>Log in. Incorrect password.</html>", content_type="text/html")
        return web.Response(text=LOGIN_HTML, content_type="text/html")

    async def account(request):
        return web.json_response(ACCOUNT_JSON)

    async def consumption(request):
        assert request.headers["bchydroparam"] == "tok123"
        return web.Response(text=CONSUMPTION_XML, content_type="application/xml")

    app = web.Application()
    app.router.add_post("/login", login)
    app.router.add_get("/account", account)
    app.router.add_post("/consumption", consumption)
    server = await aiohttp_server(app)
    base = str(server.make_url(""))
    monkeypatch.setattr(api, "URL_LOGIN", base + "/login")
    monkeypatch.setattr(api, "URL_ACCOUNT_JSON", base + "/account")
    monkeypatch.setattr(api, "URL_CONSUMPTION_XML", base + "/consumption")
    yield state


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield

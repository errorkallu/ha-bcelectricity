"""Fixtures: a fake BC Hydro portal served locally."""

import pytest
from aiohttp import web

from custom_components.bchydro import api

# Shapes below were captured from the live portal on 2026-10-13.
LOGIN_HTML = """<html><body>
<span id="bchydroparam" class="hidden" >tok123</span>
<h1>Account summary</h1>
<p class="loading">Loading $</p>
<script>var sbVars = {"accountNumber" : "000001234567", "bchydroparam" : "tok123"};</script>
</body></html>"""

BAD_LOGIN_HTML = """<html><body>
<form id="login-form" action="/sso/UI/Login" method="post">
<p>The email or password entered is incorrect</p>
<input type="hidden" name="bchydroparam" value="tok000" />
</form></body></html>"""

BILLING_SUMMARY = {
    "lastBillingDate": "Sep 11, 2026", "lastBillingAmount": "163.54",
    "billDueDate": "Sep 15, 2026", "payment": "163.54", "lastPaymentDate": "Sep 15",
    "balance": "0.00", "creditFlag": None, "accountType": "ST", "onlineBilling": "Y",
    "isPPP": "Y", "accountNumber": None, "nickName": None, "lastBillSign": None,
}

CONSUMPTION_PAGE_HTML = """<html><body>
<span id="bchydroparam" class="hidden" >tok456</span>
</body></html>"""

ACCOUNT_JSON = {
    "evpCurrentDateTime": "2026-10-13T12:45:08-07:00", "evpSlid": "0000849152",
    "evpAccount": "000001234567", "accountType": "RES", "ratePlanType": "RIB",
    "hasEV": False, "evpBillingStart": "2026-09-10T00:00:00-07:00",
    "evpBillingEnd": "2026-11-09T00:00:00-08:00",
    "yesterdayDate": "2026-10-12T00:00:00-07:00", "evpConsToDate": "434",
    "evpCostToDate": "$59.02", "evpEstConsCurPeriod": "840", "evpEstCostCurPeriod": "$114",
}

CONSUMPTION_XML = """<Data evpCurrentDateTime="2026-10-13T12:46:46-07:00" blockStatus="0" nonWan="false"><Series type="CONSUMPTION" blockStatus="0">
<Point type="SMI" quality="ACTUAL" dateTime="2026-10-11T00:00:00-07:00" endTime="2026-10-11T00:00:00-07:00" value="15.19" cost="2.03"/>
<Point type="SMI" quality="ACTUAL" dateTime="2026-10-12T00:00:00-07:00" endTime="2026-10-12T00:00:00-07:00" value="14.30" cost="1.93" evpDateType="HOLIDAY" evpDateDescription="Thanksgiving Day"/>
<Point type="SMI" quality="INVALID" dateTime="2026-10-13T00:00:00-07:00" endTime="2026-10-13T00:00:00-07:00" value="0.00" cost="0.23"/>
</Series>
<Consumption type="RIB_TIER1"/>
<Event dateTime="2026-10-12T00:00:00-07:00" type="HOLIDAY" description="Thanksgiving Day"/>
<TPSDetails showBanner="false" daysLeft="0"/>
</Data>"""


@pytest.fixture
async def fake_bchydro(socket_enabled, aiohttp_server, monkeypatch):
    """Point the scraper at a local server; yields a dict of request counters."""
    state = {"logins": 0, "bad_password": False}

    async def login(request):
        form = await request.post()
        state["logins"] += 1
        if form["password"] != "good":
            return web.Response(text=BAD_LOGIN_HTML, content_type="text/html")
        return web.Response(text=LOGIN_HTML, content_type="text/html")

    async def account(request):
        return web.json_response(ACCOUNT_JSON)

    async def billing(request):
        assert request.headers["bchydroparam"] == "tok123"
        return web.json_response(BILLING_SUMMARY)

    async def consumption_page(request):
        return web.Response(text=CONSUMPTION_PAGE_HTML, content_type="text/html")

    async def consumption(request):
        assert request.headers["bchydroparam"] == "tok456"
        return web.Response(text=CONSUMPTION_XML, content_type="application/xml")

    app = web.Application()
    app.router.add_post("/login", login)
    app.router.add_get("/account", account)
    app.router.add_post("/billing", billing)
    app.router.add_get("/consumption-page", consumption_page)
    app.router.add_post("/consumption", consumption)
    server = await aiohttp_server(app)
    base = str(server.make_url(""))
    monkeypatch.setattr(api, "URL_LOGIN", base + "/login")
    monkeypatch.setattr(api, "URL_ACCOUNT_JSON", base + "/account")
    monkeypatch.setattr(api, "URL_BILLING_SUMMARY", base + "/billing")
    monkeypatch.setattr(api, "URL_CONSUMPTION_PAGE", base + "/consumption-page")
    monkeypatch.setattr(api, "URL_CONSUMPTION_XML", base + "/consumption")
    yield state


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield

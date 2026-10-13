"""Minimal async client that scrapes the BC Hydro customer portal.

BC Hydro has no public API, so this logs in like a browser would and reads
the same JSON/XML endpoints the "Consumption" page uses. It has no Home
Assistant dependency so it can be tested on its own (see scripts/test_api.py).
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://app.bchydro.com"
URL_LOGIN = f"{BASE_URL}/sso/UI/Login"
URL_LOGIN_GOTO = f"{BASE_URL}:443/BCHCustomerPortal/web/login.html"
URL_GET_ACCOUNTS = f"{BASE_URL}/BCHCustomerPortal/web/getAccounts.html"
URL_ACCOUNTS_OVERVIEW = f"{BASE_URL}/BCHCustomerPortal/web/accountsOverview.html"
URL_BILLING_SUMMARY = f"{BASE_URL}/BCHCustomerPortal/web/ajaxBillingSummary.html"
URL_CONSUMPTION_PAGE = (
    f"{BASE_URL}/evportlet/SystemServices/main"
    "?system:runTemplate=html/view/residential/ConsumptionOverview.xml"
)
URL_ACCOUNT_JSON = f"{BASE_URL}/evportlet/web/global-data.html"
URL_CONSUMPTION_XML = f"{BASE_URL}/evportlet/web/consumption-data.html"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 ha-bcelectricity"
)
TIMEOUT = aiohttp.ClientTimeout(total=60)


class BCHydroError(Exception):
    """Generic failure talking to BC Hydro."""


class BCHydroAuthError(BCHydroError):
    """Login was rejected (bad username or password)."""


@dataclass
class DailyReading:
    """One day of consumption as shown in the portal's daily table."""

    day: date
    kwh: float
    cost: float | None
    quality: str | None = None


@dataclass
class BCHydroData:
    """Everything one daily refresh produces."""

    account_number: str | None = None
    rate_group: str | None = None
    billing_start: date | None = None
    billing_end: date | None = None
    consumption_to_date: float | None = None
    cost_to_date: float | None = None
    projected_consumption: float | None = None
    projected_cost: float | None = None
    days_since_billing: int | None = None
    balance: float | None = None
    last_bill_amount: float | None = None
    last_bill_date: str | None = None
    daily: list[DailyReading] = field(default_factory=list)

    @property
    def latest(self) -> DailyReading | None:
        """Most recent day with data (normally yesterday)."""
        return self.daily[-1] if self.daily else None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def _to_date(value: Any) -> date | None:
    """Parse the handful of date formats the portal uses."""
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    match = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", text)
    if match:
        return date(int(match[1]), int(match[2]), int(match[3]))
    for fmt in ("%m/%d/%Y", "%b %d, %Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _find_csrf(html: str) -> str | None:
    """The portal's per-session token, sent back as the 'bchydroparam' header."""
    for pattern in (
        r'id="bchydroparam"[^>]*>\s*([^<\s]+)\s*<',
        r'name="bchydroparam"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="bchydroparam"',
    ):
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def _strip_tags(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def _csrf_headers(csrf: str) -> dict[str, str]:
    """Headers the portal's jQuery adds to every POST (see security.js)."""
    return {
        "bchydroparam": csrf,
        "X-CSRF-Token": csrf,
        "X-Requested-With": "XMLHttpRequest",
    }


class BCHydroApi:
    """Logs in and fetches the current billing period's daily data."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    async def async_validate_login(self) -> None:
        """Raise BCHydroAuthError if the credentials don't work."""
        async with self._session() as session:
            await self._login(session)

    async def async_fetch(self) -> BCHydroData:
        """Log in fresh and pull everything. Called at 1 am and 8 am."""
        async with self._session() as session:
            overview_html, csrf = await self._login(session)
            data = BCHydroData()
            await self._get_billing_summary(session, overview_html, csrf, data)
            account = await self._get_account(session, data)
            await self._get_consumption(session, account, csrf, data)
            return data

    def _session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(),
            trust_env=True,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )

    async def _login(self, session: aiohttp.ClientSession) -> tuple[str, str]:
        try:
            resp = await session.post(
                URL_LOGIN,
                data={
                    "realm": "bch-ps",
                    "email": self._username,
                    "password": self._password,
                    "gotoUrl": URL_LOGIN_GOTO,
                },
            )
            html = await resp.text()
        except aiohttp.ClientError as err:
            raise BCHydroError(f"Could not reach BC Hydro: {err}") from err

        _LOGGER.debug("Login landed on %s (HTTP %s)", resp.url, resp.status)
        if resp.status in (401, 403):
            raise BCHydroAuthError("BC Hydro rejected the username or password")
        if resp.status >= 400:
            raise BCHydroError(f"Login failed with HTTP {resp.status}")

        # A rejected login re-renders the sign-in form (which has its own token).
        if 'id="login-form"' in html:
            raise BCHydroAuthError("BC Hydro rejected the username or password")

        csrf = _find_csrf(html)
        if not csrf:
            if re.search(r"(?i)password|sign in|log in", _strip_tags(html)[:5000]):
                raise BCHydroAuthError("BC Hydro rejected the username or password")
            raise BCHydroError("Logged in but the portal page looked unfamiliar")

        # Customers with more than one account land on a picker first.
        if "accountListDiv" in html:
            resp = await session.post(URL_GET_ACCOUNTS, headers={"x-csrf-token": csrf})
            accounts = (await resp.json(content_type=None)).get("accounts", [])
            if not accounts:
                raise BCHydroError("No accounts found on this BC Hydro login")
            resp = await session.get(
                URL_ACCOUNTS_OVERVIEW, params={"aid": accounts[0]["accountId"]}
            )
            html = await resp.text()
            csrf = _find_csrf(html) or csrf

        return html, csrf

    async def _get_billing_summary(
        self,
        session: aiohttp.ClientSession,
        overview_html: str,
        csrf: str,
        data: BCHydroData,
    ) -> None:
        """Balance and last bill; the summary page loads these by AJAX."""
        match = re.search(r'"accountNumber"\s*:\s*"(\d+)"', overview_html)
        if not match:
            _LOGGER.debug("No account number on the overview page; skipping balance")
            return
        resp = await session.post(
            URL_BILLING_SUMMARY,
            data={"accountNumber": match[1], "bchydroparam": csrf},
            headers=_csrf_headers(csrf),
        )
        try:
            summary = await resp.json(content_type=None)
        except ValueError:
            _LOGGER.debug("Billing summary was not JSON (HTTP %s)", resp.status)
            return
        if not summary:
            return
        balance = _to_float(summary.get("balance"))
        if balance is not None and summary.get("creditFlag") == "CR":
            balance = -balance
        data.balance = balance
        amount = _to_float(summary.get("lastBillingAmount"))
        if amount is not None and summary.get("lastBillSign") == "CR":
            amount = -amount
        data.last_bill_amount = amount
        data.last_bill_date = summary.get("lastBillingDate")

    async def _get_account(
        self, session: aiohttp.ClientSession, data: BCHydroData
    ) -> dict[str, Any]:
        resp = await session.get(URL_ACCOUNT_JSON)
        try:
            account = await resp.json(content_type=None)
        except (aiohttp.ContentTypeError, ValueError) as err:
            raise BCHydroError("Account details were not JSON; session expired?") from err

        data.account_number = account.get("evpAccount")
        data.rate_group = account.get("evpRateGroup") or account.get("ratePlanType")
        data.billing_start = _to_date(account.get("evpBillingStart"))
        data.billing_end = _to_date(account.get("evpBillingEnd"))
        data.consumption_to_date = _to_float(account.get("evpConsToDate"))
        data.cost_to_date = _to_float(account.get("evpCostToDate"))
        data.projected_consumption = _to_float(account.get("evpEstConsCurPeriod"))
        data.projected_cost = _to_float(account.get("evpEstCostCurPeriod"))
        today = _to_date(account.get("evpCurrentDateTime"))
        if today and data.billing_start:
            data.days_since_billing = (today - data.billing_start).days
        return account

    async def _get_consumption(
        self,
        session: aiohttp.ClientSession,
        account: dict[str, Any],
        csrf: str,
        data: BCHydroData,
    ) -> None:
        # The data endpoints only answer with the token issued by the
        # consumption page itself, not the one from the login page.
        resp = await session.get(URL_CONSUMPTION_PAGE)
        csrf = _find_csrf(await resp.text()) or csrf
        resp = await session.post(
            URL_CONSUMPTION_XML,
            data={
                "StartDateTime": account.get("evpBillingStart"),
                "EndDateTime": account.get("evpBillingEnd"),
                "DateRange": "currentBill",
                "Granularity": "daily",
                "IncludeMeters": "all" if account.get("hasEV") else "",
                "Overlays": "none",
                "UserClick": "",
                "IsMobile": "false",
            },
            headers={**_csrf_headers(csrf), "Referer": URL_CONSUMPTION_PAGE},
        )
        if resp.status in (401, 403):
            raise BCHydroError(f"Consumption data refused (HTTP {resp.status})")
        text = await resp.text()
        try:
            root = ET.fromstring(text)
        except ET.ParseError as err:
            raise BCHydroError("Consumption data was not XML; session expired?") from err

        for series in root.iter("Series"):
            for point in series.iter("Point"):
                quality = point.get("quality")
                if quality and quality.upper() != "ACTUAL":
                    continue
                day = _to_date(point.get("dateTime"))
                kwh = _to_float(point.get("value"))
                if day is None or kwh is None:
                    continue
                data.daily.append(
                    DailyReading(day, kwh, _to_float(point.get("cost")), quality)
                )
            break  # first series is the current period; others are overlays
        data.daily.sort(key=lambda r: r.day)

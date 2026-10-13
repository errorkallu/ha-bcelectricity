"""Constants for the BC Hydro integration."""

DOMAIN = "bchydro"

# BC Hydro publishes the previous day's reading overnight; scrape once at 1 am.
UPDATE_HOUR = 1
UPDATE_MINUTE = 0

# If the 1 am scrape fails (site down, data not posted yet), try again later.
RETRY_DELAY_MINUTES = 60
MAX_RETRIES = 3

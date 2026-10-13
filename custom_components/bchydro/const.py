"""Constants for the BC Hydro integration."""

DOMAIN = "bchydro"

# BC Hydro posts the previous day's reading sometime overnight or in the
# morning, so scrape at 1 am and again at 8 am in case it was late.
UPDATE_HOURS = [1, 8]
UPDATE_MINUTE = 0

# If a scheduled scrape fails (site down, data not posted yet), try again later.
RETRY_DELAY_MINUTES = 60
MAX_RETRIES = 3

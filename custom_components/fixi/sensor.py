import logging
import requests
import homeassistant.helpers.config_validation as cv
from datetime import timedelta
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_RADIUS, CONF_COUNT
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
import voluptuous as vol
import json

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'fixi'

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=30)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_LATITUDE): cv.string,
    vol.Required(CONF_LONGITUDE): cv.string,
    vol.Optional(CONF_RADIUS, default=1000): cv.string,
    vol.Optional(CONF_COUNT, default=50): cv.string,
})


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Fixi sensor platform."""
    latitude = config[CONF_LATITUDE]
    longitude = config[CONF_LONGITUDE]
    radius = config[CONF_RADIUS]
    count = config[CONF_COUNT]

    fetcher = FixiDataFetcher(latitude, longitude, radius, count)
    fetcher.update()

    current_sensors = {sensor.unique_id: sensor for sensor in hass.data.get(DOMAIN, {}).get('sensors', [])}

    new_sensors = []
    for issue in fetcher.issues:
        issue_id = f"{DOMAIN}_{issue.get('publicID')}"
        if issue_id not in current_sensors:
            new_sensor = FixiSensor(issue)
            new_sensors.append(new_sensor)
            current_sensors[issue_id] = new_sensor

    to_remove = [
        sensor for sensor in current_sensors.values()
        if sensor.public_id not in [issue.get('publicID') for issue in fetcher.issues]
    ]
    for sensor in to_remove:
        _LOGGER.debug(f"Removing sensor: {sensor.unique_id}")
        hass.data[DOMAIN]['sensors'].remove(sensor)

    add_entities(new_sensors, True)

    hass.data[DOMAIN] = {
        'sensors': list(current_sensors.values())
    }


class FixiDataFetcher:
    """Class to fetch data from Fixi API."""

    def __init__(self, latitude, longitude, radius, count):
        self._latitude = latitude
        self._longitude = longitude
        self._radius = radius
        self._count = count
        self.issues = []

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Fetch the latest data from Fixi API."""
        url = (
            f"https://www.fixi.nl/api/issues/nearbylite?latitude={self._latitude}"
            f"&longitude={self._longitude}&radius={self._radius}"
            f"&sortOrder=newestFirst&page=1&count={self._count}&doNotIntercept=true"
        )

        response = requests.get(url=url, headers=get_headers())
        if response.status_code == 200:
            try:
                data = json.loads(response.json())  # Double parse JSON, as Fixi requires it
                _LOGGER.debug("Latest issues fetched successfully")
                self.issues = data.get('results', [])
            except ValueError as e:
                _LOGGER.error("Error parsing JSON response: %s", e)
        else:
            _LOGGER.error("Error fetching data from Fixi API (%s): %s", response.status_code, response.text)


class FixiSensor(Entity):
    """Representation of a Fixi sensor."""

    def __init__(self, issue):
        """Initialize the sensor."""
        self._issue = issue
        self._public_id = issue.get('publicID')
        self._attributes = self._initialize_attributes(issue)

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Fetch new state data for the sensor."""
        url = f"https://www.fixi.nl/api/issues/lite/{self._public_id}"
        response = requests.get(url, headers=get_headers())

        if response.status_code == 200:
            try:
                data = json.loads(response.json())  # Double parse JSON, as Fixi requires it
                _LOGGER.debug("Issue data fetched successfully")
                self._attributes = self._initialize_attributes(data)
                self._attributes.update({
                    'modified': data.get('modified', ''),
                    'attachments': [attachment['uri'] for attachment in data.get('attachments', [])]
                })
            except ValueError as e:
                _LOGGER.error("Error parsing JSON response: %s", e)
        else:
            _LOGGER.error("Error fetching data from Fixi API for sensor (%s): %s", response.status_code, response.text)

    def _initialize_attributes(self, issue_data):
        """Initialize sensor attributes."""
        return {
            'address': issue_data.get('address', ''),
            'addressDetails': issue_data.get('addressDetails', ''),
            'description': issue_data.get('description', ''),
            'created': issue_data.get('created', ''),
            'closed': issue_data.get('closed', ''),
            'fetchDateTime': issue_data.get('fetchDateTime', ''),
            'location': issue_data.get('location', {}),
            'likeCount': issue_data.get('likeCount', 0),
            'hasComments': issue_data.get('hasComments', False),
            'visibility': issue_data.get('visibility', ''),
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._public_id} - {self._issue.get('categoryName', 'unknown')}"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._issue.get('status', 'unknown')

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return f"{DOMAIN}_{self._public_id}"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def public_id(self):
        """Return the public id."""
        return self._public_id


def get_forgery_token():
    """Retrieve the anti-forgery token."""
    response = requests.get("https://www.fixi.nl/api/utility/antiForgeryToken", headers={
        "accept": "application/json, text/plain, */*",
        "accept-language": "nl,en-US;q=0.9,en;q=0.8,de;q=0.7,und;q=0.6,fr;q=0.5",
        "cache-control": "no-cache",
        "referrer": "https://www.fixi.nl/",
    })

    if response.status_code == 200:
        try:
            data = response.json()
            _LOGGER.debug("'antiForgeryToken' data fetched successfully")
            return data
        except ValueError as e:
            _LOGGER.error("Error parsing JSON response: %s", e)
    else:
        _LOGGER.error("Error fetching anti-forgery token (%s): %s", response.status_code, response.text)


def get_access_token():
    """Retrieve the access token for authentication."""
    url = "https://www.fixi.nl/api/auth/getGrantTokens"
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "nl,en-US;q=0.9,en;q=0.8,de;q=0.7,und;q=0.6,fr;q=0.5",
        "antiforgerytoken": get_forgery_token(),
        "content-type": "application/json;charset=UTF-8",
        "referrer": "https://www.fixi.nl/",
    }
    payload = "{\"SerializedObject\":\"grant_type=client_credentials&client_id=d%2BB1TdgkOEuirFhOYhw4guf0lPeQuT72tuKTIkkyJvI%3D&client_secret=c0DglPf3fBPDe%2FJRD2KLhPuO%2BnlRsPdjsTSD03U%2FhWg%3D\"}"

    response = requests.post(url=url, headers=headers, data=payload)
    if response.status_code == 200:
        try:
            data = json.loads(response.json())  # Double parse JSON, as Fixi requires it
            _LOGGER.debug("'getGrantTokens' data fetched successfully")
            return data.get('access_token', '')
        except ValueError as e:
            _LOGGER.error("Error parsing JSON response: %s", e)
    else:
        _LOGGER.error("Error fetching access token (%s): %s", response.status_code, response.text)


def get_headers():
    """Generate headers with authorization and anti-forgery token."""
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "nl,en-US;q=0.9,en;q=0.8,de;q=0.7,und;q=0.6,fr;q=0.5",
        "antiforgerytoken": get_forgery_token(),
        "authorization": f"Bearer {get_access_token()}",
        "content-type": "application/json;charset=UTF-8",
        "referrer": "https://www.fixi.nl/",
    }

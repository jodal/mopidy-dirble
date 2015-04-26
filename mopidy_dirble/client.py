from __future__ import unicode_literals

import logging
import time
import urllib

from mopidy import __version__ as mopidy_version

from requests import Session, exceptions
from requests.adapters import HTTPAdapter

from mopidy_dirble import __version__ as dirble_version

logger = logging.getLogger(__name__)


class Dirble(object):
    """Light wrapper for Dirble API lookup.

    Important things to note:
    - The client will retry up to three times before giving up for network
      errors etc.
    - The client will do exponential back off when requests fail or timeout.
    - The client will cache results aggressively.
    - Failed requests will return an empty default type appropriate for the
      lookup in question, normally a empty dict or list.
    - The data returned comes direct from the API's JSON.
    - The data is not copied, so beware of modifying what you get back.
    """

    def __init__(self, api_key, timeout):
        self._cache = {}
        self._stations = {}
        self._timeout = timeout / 1000.0
        self._backoff_until = time.time()
        self._backoff_max = 60
        self._backoff = 1

        self._base_uri = 'http://api.dirble.com/v2/'

        self._session = Session()
        self._session.params = {'token': api_key}
        self._session.headers['User-Agent'] = ' '.join([
            'Mopidy-Dirble/%s' % dirble_version,
            'Mopidy/%s' % mopidy_version,
            self._session.headers['User-Agent']])
        self._session.mount(self._base_uri, HTTPAdapter(max_retries=3))

    def flush(self):
        self._cache = {}
        self._stations = {}

    def categories(self):
        return self._fetch('categories/tree', [])

    def category(self, identifier):
        identifier = int(identifier)
        categories = self.categories()[:]
        while categories:
            c = categories.pop(0)
            if c['id'] == identifier:
                return c
            categories.extend(c['children'])
        return None

    def subcategories(self, identifier):
        category = self.category(identifier)
        return (category or {}).get('children', [])

    def stations(self, category=None, country=None):
        if category and not country:
            path = 'category/%s/stations' % category
        elif country and not category:
            path = 'countries/%s/stations?all=1' % country.lower()
        else:
            return []

        stations = self._fetch(path, [])
        for station in stations:
            self._stations.setdefault(station['id'], station)
        return stations

    def station(self, identifier):
        identifier = int(identifier)  # Ensure we are consistent for cache key.
        if identifier in self._stations:
            return self._stations[identifier]
        station = self._fetch('station/%s' % identifier, {})
        if station:
            if 'id' not in station:
                station['id'] = identifier
            self._stations.setdefault(station['id'], station)
        return station

    def continents(self):
        return self._fetch('continents', [])

    def countries(self, continent=None):
        result = []
        countries = self._fetch('countries', [])
        continent = int(continent) if continent is not None else None
        for c in countries:
            if continent is None or c['Continent_id'] == continent:
                result.append(c['country_code'].lower())
        return result

    def search(self, query):
        quoted_query = urllib.quote(query.encode('utf-8'))
        stations = self._fetch('search/%s' % quoted_query, [])
        for station in stations:
            self._stations.setdefault(station['id'], station)
        return stations

    def _fetch(self, path, default):
        uri = self._base_uri + path
        if uri in self._cache:
            logger.debug('Cache hit: %s', uri)
            return self._cache[uri]

        if time.time() < self._backoff_until:
            logger.debug('Back off fallback used: %s', uri)
            return default

        logger.debug('Fetching: %s', uri)
        try:
            resp = self._session.get(uri, timeout=self._timeout)

            if resp.status_code == 200:
                data = resp.json()
                self._cache[uri] = data
                self._backoff = 1
                return data

            logger.debug('Fetch failed, HTTP %s', resp.status_code)

            if resp.status_code == 404:
                self._cache[uri] = default
                return default

        except exceptions.RequestException as e:
            logger.debug('Fetch failed: %s', e)
        except ValueError as e:
            logger.warning('Fetch failed: %s', e)

        self._backoff = min(self._backoff_max, self._backoff*2)
        self._backoff_until = time.time() + self._backoff
        logger.debug('Entering back off mode for %d seconds.', self._backoff)
        return default

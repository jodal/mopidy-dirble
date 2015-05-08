from __future__ import unicode_literals

import logging

from mopidy import backend
from mopidy.models import Image, Ref, SearchResult

import pykka

from . import client, translator

logger = logging.getLogger(__name__)


class DirbleBackend(pykka.ThreadingActor, backend.Backend):
    uri_schemes = ['dirble']

    def __init__(self, config, audio):
        super(DirbleBackend, self).__init__()
        self.dirble = client.Dirble(config['dirble']['api_key'],
                                    config['dirble']['timeout'],
                                    config['proxy'])
        self.countries = config['dirble']['countries']
        self.library = DirbleLibrary(backend=self)
        self.playback = DirblePlayback(audio=audio, backend=self)


class DirbleLibrary(backend.LibraryProvider):
    root_directory = Ref.directory(uri='dirble:root', name='Dirble')

    # TODO: add countries when there is a lookup for countries with stations
    def browse(self, uri):
        result = []
        variant, identifier = translator.parse_uri(uri)

        if variant == 'root':
            for category in self.backend.dirble.categories():
                result.append(translator.category_to_ref(category))
            for country in self.backend.countries:
                result.append(translator.country_to_ref(country))
            for continent in self.backend.dirble.continents():
                result.append(translator.continent_to_ref(continent))
        elif variant == 'category' and identifier:
            for category in self.backend.dirble.subcategories(identifier):
                result.append(translator.category_to_ref(category))
            for station in self.backend.dirble.stations(category=identifier):
                result.append(translator.station_to_ref(station))
        elif variant == 'continent' and identifier:
            for country in self.backend.dirble.countries(identifier):
                result.append(translator.country_to_ref(country))
        elif variant == 'country' and identifier:
            for station in self.backend.dirble.stations(country=identifier):
                result.append(
                    translator.station_to_ref(station, show_country=False))
        else:
            logger.debug('Unknown URI: %s', uri)

        result.sort(key=lambda ref: ref.name)
        return result

    def refresh(self, uri=None):
        self.backend.dirble.flush()

    def lookup(self, uri):
        variant, identifier = translator.parse_uri(uri)
        if variant != 'station':
            return []
        station = self.backend.dirble.station(identifier)
        if not station:
            return []
        return [translator.station_to_track(station)]

    def search(self, query=None, uris=None, exact=False):
        if not query.get('any'):
            return None

        categories = set()
        countries = []

        for uri in uris or []:
            variant, identifier = translator.parse_uri(uri)
            if variant == 'country':
                countries.append(identifier.lower())
            elif variant == 'continent':
                countries.extend(self.backend.dirble.countries(identifier))
            elif variant == 'category':
                pending = [self.backend.dirble.category(identifier)]
                while pending:
                    c = pending.pop(0)
                    categories.add(c['id'])
                    pending.extend(c['children'])

        tracks = []
        for station in self.backend.dirble.search(' '.join(query['any'])):
            if countries and station['country'].lower() not in countries:
                continue
            station_categories = {c['id'] for c in station['categories']}
            if categories and not station_categories.intersection(categories):
                continue
            tracks.append(translator.station_to_track(station))

        return SearchResult(tracks=tracks)

    def get_images(self, uris):
        result = {}
        for uri in uris:
            result[uri] = []

            variant, identifier = translator.parse_uri(uri)
            if variant != 'station' or not identifier:
                continue

            station = self.backend.dirble.station(identifier)
            if not station:
                continue

            if station['image']['image']['url']:
                result[uri].append(Image(uri=station['image']['image']['url']))

        return result


class DirblePlayback(backend.PlaybackProvider):

    def translate_uri(self, uri):
        variant, identifier = translator.parse_uri(uri)
        if variant != 'station':
            return None
        station = self.backend.dirble.station(identifier)
        for stream in station['streams']:
            # TODO: add way to pick which variant to use?
            return stream['stream']
        return None

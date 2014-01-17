from __future__ import unicode_literals

import logging

import pykka

from mopidy import backend
from mopidy.models import Ref, Track

from . import client, translator

logger = logging.getLogger(__name__)


class DirbleBackend(pykka.ThreadingActor, backend.Backend):
    uri_schemes = ['dirble']

    def __init__(self, config, audio):
        super(DirbleBackend, self).__init__()
        self.dirble = client.Dirble(config['dirble']['api_key'],
                                    config['dirble']['timeout'])
        self.library = DirbleLibrary(backend=self)


class DirbleLibrary(backend.LibraryProvider):
    root_directory = Ref.directory(uri='dirble:root', name='Dirble')

    # TODO: add countries when there is a lookup for countries with stations
    def browse(self, uri):
        result = []
        variant, identifier = translator.parse_uri(uri)

        if variant == 'root':
            for category in self.backend.dirble.categories():
                result.append(translator.category_to_ref(category))

        elif variant == 'category' and identifier:
            for sub_category in self.backend.dirble.sub_categories(identifier):
                result.append(translator.category_to_ref(sub_category, primary=False))
            for station in self.backend.dirble.stations(identifier):
                result.append(translator.station_to_ref(station))

        elif variant == 'subcategory' and identifier:
            for station in self.backend.dirble.stations(identifier):
                result.append(translator.station_to_ref(station))

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
        ref = translator.station_to_ref(station)
        return [Track(uri=ref.uri, name=ref.name)]

    def find_exact(self, query=None, uris=None):
        return None

    def search(self, query=None, uris=None):
        return None

# -*- coding: utf-8 -*-
#
# Copyright 2017-2018 SENAITE SYNC.

import urllib
import urlparse
import requests

from BTrees.OOBTree import OOBTree
from zope.annotation.interfaces import IAnnotations
from senaite import api
from senaite.sync import logger
from senaite.sync.syncerror import SyncError

SYNC_STORAGE = "senaite.sync"
API_BASE_URL = "API/senaite/v1"


class SyncStep:
    """

    """

    def __init__(self, data):
        # VARIABLES TO BE USED IN FETCH AND IMPORT STEPS

        # Soup Handler to interact with the domain's soup table
        self.sh = None
        self.session = None
        self.portal = api.get_portal()
        self.url = data.get("url", None)
        self.domain_name = data.get("domain_name", None)
        self.username = data.get("ac_name", None)
        self.password = data.get("ac_password", None)
        # Import configuration
        self.import_settings = data.get("import_settings", False)
        self.import_users = data.get("import_users", False)
        self.import_registry = data.get("import_registry", False)

        if not any([self.domain_name, self.url, self.username, self.password]):
            self.fail("Missing parameter in Sync Step: {}".format(data))

    def translate_path(self, path):
        """Translate the physical path to a local path
        """
        portal_id = self.portal.getId()
        remote_portal_id = path.split("/")[1]
        return path.replace(remote_portal_id, portal_id)

    def get_items(self, url_or_endpoint, **kw):
        """Return the 'items' list from a std. JSON API response
        """
        data = self.get_json(url_or_endpoint, **kw)
        if not isinstance(data, dict):
            return []
        return data.get("items", [])

    def yield_items(self, url_or_endpoint, **kw):
        """Yield items of all pages
        """
        data = self.get_json(url_or_endpoint, **kw)
        for item in data.get("items", []):
            yield item

        next_url = data.get("next")
        if next_url:
            for item in self.yield_items(next_url, **kw):
                yield item

    def get_first_item(self, url_or_endpoint, **kw):
        """Fetch the first item of the 'items' list from a std. JSON API reponse
        """
        items = self.get_items(url_or_endpoint, **kw)
        if not items:
            return None
        return items[0]

    def get_json(self, url_or_endpoint, **kw):
        """Fetch the given url or endpoint and return a parsed JSON object
        """
        api_url = self.get_api_url(url_or_endpoint, **kw)
        logger.info("get_json::url={}".format(api_url))
        try:
            response = self.session.get(api_url)
        except Exception as e:
            message = "Could not connect to {} Please check.".format(
                api_url)
            logger.error(message)
            logger.error(e)
            return {}
        status = response.status_code
        if status != 200:
            message = "GET for {} ({}) returned Status Code {}. Please check.".format(
                url_or_endpoint, api_url, status)
            logger.error(message)
            return {}
        return response.json()

    def get_api_url(self, url_or_endpoint, **kw):
        """Create an API URL from an endpoint or absolute url
        """
        # Nothing to do if we have no base URL
        if self.url is None:
            raise SyncError("No base URL found")
        # Convert to an absolute URL
        if not url_or_endpoint.startswith(self.url):
            segments = API_BASE_URL.split("/") + url_or_endpoint.split("/")
            path = "/".join(segments)
            url_or_endpoint = "/".join([self.url, path])
        # Handle request parameters
        if kw:
            scheme, netloc, path, query, fragment = urlparse.urlsplit(url_or_endpoint)
            if query:
                query = dict(urlparse.parse_qsl(query))
                kw.update(query)
            q = urllib.urlencode(kw)
            return "{}://{}{}?{}".format(scheme, netloc, path, q)
        return url_or_endpoint

    def get_session(self):
        """Return a session object for authenticated requests
        """
        session = requests.Session()
        session.auth = (self.username, self.password)
        return session

    def fail(self, message, status):
        """Raise a SyncError
        """
        raise SyncError(message, status)

    def get_annotation(self):
        """Annotation storage on the portal object
        """
        return IAnnotations(self.portal)

    def get_storage(self):
        """Return a ready to use storage for the given domain (key)
        """
        if self.domain_name is None:
            self.domain_name = len(self.storage)
        domain = self.domain_name
        if not self.storage.get(domain):
            self.storage[domain] = OOBTree()
            self.storage[domain]["credentials"] = OOBTree()
            self.storage[domain]["registry"] = OOBTree()
            self.storage[domain]["settings"] = OOBTree()
            self.storage[domain]["ordered_uids"] = []
            self.storage[domain]["configuration"] = OOBTree()
        return self.storage[domain]

    @property
    def storage(self):
        """Raw storage property

        Please use get_storage to get a sync storage for a given domain
        """
        annotation = self.get_annotation()
        if annotation.get(SYNC_STORAGE) is None:
            annotation[SYNC_STORAGE] = OOBTree()
        return annotation[SYNC_STORAGE]

    def flush_storage(self):
        """Drop the whole storage
        """
        annotation = self.get_annotation()
        if annotation.get(SYNC_STORAGE) is not None:
            del annotation[SYNC_STORAGE]

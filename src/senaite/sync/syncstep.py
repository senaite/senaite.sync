# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.SYNC
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.

import urllib
import urlparse
import requests

from time import sleep
from DateTime import DateTime

from BTrees.OOBTree import OOBTree
from zope.annotation.interfaces import IAnnotations
from senaite import api
from senaite.sync import logger
from senaite.sync import utils
from senaite.sync.syncerror import SyncError
from senaite.sync.souphandler import REMOTE_PATH, LOCAL_PATH, PORTAL_TYPE

SYNC_STORAGE = "senaite.sync"
API_BASE_URL = "@@API/senaite/v1"
# Sometimes we might want to send the request to the source until we get the
# response
API_MAX_ATTEMPTS = 5
API_ATTEMPT_INTERVAL = 5


class SyncStep(object):
    """ Synchronization process can be done in multiple steps such as Fetch,
    Import and etc. This is the class to be extended in 'Step Classes' which
    contains some necessary functions.
    """

    def __init__(self, credentials, config):
        # Soup Handler to interact with the domain's soup table
        self.sh = None
        self.session = None
        self.portal = api.get_portal()

        # Set Credentials
        self.domain_name = credentials.get("domain_name", None)
        self.url = credentials.get("url", None)
        self.username = credentials.get("ac_name", None)
        self.password = credentials.get("ac_password", None)
        self.certificate_file = credentials.get("certificate_file", None)

        if not any([self.domain_name, self.url, self.username, self.password]):
            self.fail("Missing parameter in Sync Step: {}".format(credentials))

        # Import configuration
        self.import_settings = config.get("import_settings", False)
        self.import_users = config.get("import_users", False)
        self.import_registry = config.get("import_registry", False)

        # A prefix to be used in object ID's, representing the Remote Instance
        self.remote_prefix = config.get("remote_prefix", None)
        # Prefix of this instance in the Remote (if exists)
        self.local_prefix = config.get("local_prefix", None)

        # Types to be fully synchronized
        self.full_sync_types = config.get("full_sync_types", [])
        # Types to be skipped
        self.unwanted_content_types = config.get("unwanted_content_types", [])
        # Types which will not be editable on this instance
        self.read_only_types = config.get("read_only_types", [])
        # Types of objects that have been created on this instance and must have
        # the changes from Remote
        self.update_only_types = config.get("update_only_types", [])
        # Types to contain Remote's Prefix in their ID's on this instance
        self.prefixable_types = config.get("prefixable_types", [])

    def translate_path(self, remote_path):
        """ Translates a remote physical path into local path taking into account
        the prefix. If prefix is not enabled, then just the Remote Site ID will
        be replaced by the Local one. In case prefixes are enabled, then walk
        through all parents and add prefixes if necessary.
        :param remote_path: a path in a remote instance
        :return string: the translated path
        """
        if not remote_path or "/" not in remote_path:
            raise SyncError("error", "Invalid remote path: '{}'"
                            .format(remote_path))

        if self.is_portal_path(remote_path):
            return api.get_path(self.portal)

        portal_id = self.portal.getId()
        remote_portal_id = remote_path.split("/")[1]
        if not self.remote_prefix and not self.local_prefix:
            return str(remote_path.replace(remote_portal_id, portal_id))

        rec = self.sh.find_unique(REMOTE_PATH, remote_path)
        if rec is None:
            raise SyncError("error", "Missing Remote path in Soup table: {}"
                            .format(remote_path))

        # Check if previously translated and saved
        if rec[LOCAL_PATH]:
            return str(rec[LOCAL_PATH])

        # Get parent's local path
        remote_parent_path = utils.get_parent_path(remote_path)
        parent_path = self.translate_path(remote_parent_path)

        # Will check whether prefix needed by portal type
        portal_type = rec[PORTAL_TYPE]
        prefix = self.get_prefix(portal_type)

        # Remove Local Prefix
        rem_id = utils.get_id_from_path(remote_path)
        local_id = self.trim_local_prefix(rem_id)

        res = "{0}/{1}{2}".format(parent_path, prefix, local_id)
        res = res.replace(remote_portal_id, portal_id)
        # Save the local path in the Souper to use in the future
        self.sh.update_by_remote_path(remote_path, LOCAL_PATH = res)
        return str(res)

    def get_prefix(self, portal_type):
        """
        :param portal_type: content type to get the prefix for
        :return:
        """
        if self.remote_prefix and portal_type in self.prefixable_types:
            return self.remote_prefix
        return ""

    def trim_local_prefix(self, remote_id):
        """

        :param remote_id:
        :param portal_type:
        :return:
        """
        if self.local_prefix and remote_id.startswith(self.local_prefix):
            return remote_id.replace(self.local_prefix, "")
        return remote_id

    def is_portal_path(self, path):
        """ Check if the given path is the path of any portal object.
        :return:
        """
        if not path:
            return False

        portal_path = api.get_path(self.portal)
        if path == portal_path:
            return True

        # Can be portal path in remote
        parts = path.split("/")
        if len(parts) < 3:
            return True

        return False

    def get_items(self, url_or_endpoint, **kw):
        """Return the 'items' list from a std. JSON API response
        """
        data = self.get_json(url_or_endpoint, **kw)
        if not isinstance(data, dict):
            return []
        return data.get("items", [])

    def get_items_with_retry(self, max_attempts=API_MAX_ATTEMPTS,
                             interval=API_ATTEMPT_INTERVAL, **kwargs):
        """
        Retries to retrieve items if HTTP response fails.
        :param max_attempts: maximum number of attempts to try
        :param interval: time delay between attempts in seconds
        :param kwargs: query and parameters pass to get_items
        :return:
        """
        items = None
        for i in range(max_attempts):
            items = self.get_items(**kwargs)
            if items:
                break
            sleep(interval)
        return items

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
        items = self.get_items_with_retry(url_or_endpoint=url_or_endpoint, **kw)
        if not items:
            return None
        return items[0]

    def get_json(self, url_or_endpoint, **kw):
        """Fetch the given url or endpoint and return a parsed JSON object
        """
        api_url = self.get_api_url(url_or_endpoint, **kw)
        logger.debug("get_json::url={}".format(api_url))
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
        # if a certificate path has been specified
        #  use it for this session
        if self.certificate_file:
            session.verify = self.certificate_file
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
            self.storage[domain]["last_fetch_time"] = DateTime()
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

    def _parents_fetched(self, item):
        """
        If data was fetched with portal type filter, this method will be used
        to fill the missing parents for fetched objects.
        :return: True if ALL parents are fetched
        """
        # Never fetch parents of an unnecessary objects
        if not utils.has_valid_portal_type(item):
            return False
        parent_path = item.get("parent_path")
        # Skip if the parent is portal object
        if self.is_portal_path(parent_path):
            return True
        # Skip if already exists
        if self.sh.find_unique(REMOTE_PATH, parent_path):
            return True
        logger.debug("Inserting missing parent: {}".format(parent_path))
        parent = self.get_first_item(item.get("parent_url"))
        if not parent:
            logger.error("Cannot fetch parent info: {} ".format(parent_path))
            return False
        par_dict = utils.get_soup_format(parent)
        self.sh.insert(par_dict)
        # Recursively import grand parents too
        return self._parents_fetched(parent)

    def is_item_allowed(self, item):
        """ Checks if item is allowed based on its portal_type
        :param item: object data dict
        """
        if not utils.has_valid_portal_type(item):
            return False
        pt = item.get("portal_type")
        if pt in self.unwanted_content_types:
            return False

        # If it is update-only content type, then Remote Id should start with
        # this instance's prefix
        if pt in self.update_only_types:
            remote_path= item.get("path", "")
            remote_id = utils.get_id_from_path(remote_path)
            if not remote_id.startswith(self.local_prefix):
                return False

        return True

# -*- coding: utf-8 -*-
#
# Copyright 2017-2017 SENAITE LIMS.

import urllib
import urlparse
import requests

from BTrees.OOBTree import OOSet
from BTrees.OOBTree import OOBTree

from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from zope.interface import implements
from zope.annotation.interfaces import IAnnotations
from zope.globalrequest import getRequest

from plone import protect

from senaite import api
from senaite.sync import logger
from senaite.sync.browser.interfaces import ISync
from senaite.sync import _

API_BASE_URL = "API/senaite/v1"
SYNC_STORAGE = "senaite.sync"


class SyncError(Exception):
    """ Exception Class for Sync Errors
    """

    def __init__(self, status, message):
        self.message = message
        self.status = status
        self.setStatus(status)

    def setStatus(self, status):
        request = getRequest()
        request.response.setStatus(status)

    def __str__(self):
        return self.message


class Sync(BrowserView):
    """Sync Controller View
    """
    implements(ISync)

    template = ViewPageTemplateFile("templates/sync.pt")

    def __init__(self, context, request):
        super(BrowserView, self).__init__(context, request)
        self.context = context
        self.request = request

        self.url = None
        self.username = None
        self.password = None
        self.session = None

    def __call__(self):
        protect.CheckAuthenticator(self.request.form)

        self.portal = api.get_portal()
        self.request.set('disable_plone.rightcolumn', 1)
        self.request.set('disable_border', 1)

        # Handle form submit
        form = self.request.form
        fetchform = form.get("fetchform", False)
        dataform = form.get("dataform", False)
        if not any([fetchform, dataform]):
            return self.template()

        # remember the form field values
        url = form.get("url", None)
        if not url.startswith("http"):
            url = "http://{}".format(url)
        self.url = url
        self.username = form.get("ac_name", None)
        self.password = form.get("ac_password", None)

        # Handle "Import" action
        if form.get("import", False):
            key = form.get("key", None)
            self.import_data(key)
            return self.template()

        # Handle "Clear" action
        if form.get("clear", False):
            self.flush_storage()
            message = _("Cleared Data Storage")
            self.add_status_message(message, "info")
            return self.template()

        # Handle "Fetch" action
        if form.get("fetch", False):
            # check if all mandatory fields have values
            if not all([self.url, self.username, self.password]):
                message = _("Please fill in all required fields")
                self.add_status_message(message, "error")
                return self.template()

            # initialize the session
            self.session = self.get_session(self.username, self.password)

            # try to get the version of the remote JSON API
            version = self.get_version()
            if not version or not version.get('version'):
                message = _("Please install senaite.jsonapi on the source system")
                self.add_status_message(message, "error")
                return self.template()

            # try to get the current logged in user
            user = self.get_authenticated_user()
            if not user or user.get("authenticated") is False:
                message = _("Wrong username/password")
                self.add_status_message(message, "error")
                return self.template()

            # Fetch all users from the source
            self.fetch_users()
            # Start the fetch process beginning from the portal object
            self.fetch_data()

        # always render the template
        return self.template()

    def fetch_users(self):
        """Fetch all users from the source instance
        """
        storage = self.get_storage()
        userstore = storage["users"]

        for user in self.yield_items("users"):
            username = user.get("username")
            userstore[username] = user

    def import_data(self, key):
        """Import the data from the storage identified by key
        """
        logger.info("*** IMPORT DATA {} ***".format(key))

    def fetch_data(self, uid="0"):
        """Fetch the data from the source
        """
        # Fetch the object by uid
        parent = self.get_json(uid, complete=True, children=True)
        children = parent.pop("children", [])
        self.store(uid, parent)

        # Fetch the children of this object
        for child in children:
            child_uid = child.get("uid")
            if not child_uid:
                message = "Item '{}' has no UID key".format(child)
                self.add_status_message(message, "warn")
                continue

            child_item = self.get_json(child_uid, complete=True, children=True)
            child_children = child_item.pop("children", [])
            self.store(child_uid, child_item)

            for child_child in child_children:
                self.fetch_data(uid=child_child.get("uid"))

    def store(self, key, value):
        """Store item in storage
        """
        # Get the storage for the current URL
        storage = self.get_storage()
        datastore = storage["data"]
        indexstore = storage["index"]

        # already fetched
        if key in datastore:
            return

        # Create some indexes
        for index in ["portal_type", "parent_id"]:
            index_key = "by_{}".format(index)
            if not indexstore.get(index_key):
                indexstore[index_key] = OOBTree()
            indexvalue = value.get(index)
            # Check if the index value, e.g. the portal_type="Sample", is
            # already known as a key in the index.
            if not indexstore[index_key].get(indexvalue):
                indexstore[index_key][indexvalue] = OOSet()
            indexstore[index_key][indexvalue].add(key)

        # store the data
        datastore[key] = value

    def get_version(self):
        """Return the remote JSON API version
        """
        return self.get_json("version")

    def get_authenticated_user(self):
        """Return the remote user
        """
        return self.get_first_item("users/current")

    def get_first_item(self, url_or_endpoint, **kw):
        """Fetch the first item of the items list
        """
        items = self.get_items(url_or_endpoint, **kw)
        if not items:
            return None
        return items[0]

    def get_items(self, url_or_endpoint, **kw):
        """Return the items list from the data dict
        """
        data = self.get_json(url_or_endpoint, **kw)
        if not isinstance(data, dict):
            return []
        return data.get("items", [])

    def get_json(self, url_or_endpoint, **kw):
        """Returns the parsed JSON
        """
        api_url = self.get_api_url(url_or_endpoint, **kw)
        logger.info("get_json::url={}".format(api_url))
        try:
            response = self.session.get(api_url)
        except Exception as e:
            message = "Could not connect to {} Please check.".format(
                api_url)
            logger.error(e)
            self.add_status_message(message, "error")
            return {}
        status = response.status_code
        if status != 200:
            message = "GET for {} ({}) returned Status Code {}. Please check.".format(
                url_or_endpoint, api_url, status)
            self.add_status_message(message, "warning")
            return {}
        return response.json()

    def yield_items(self, url_or_endpoint, **kw):
        """Yield all items of all pages
        """
        data = self.get_json(url_or_endpoint, **kw)
        for item in data.get("items", []):
            yield item

        next_url = data.get("next")
        if next_url:
            for item in self.yield_items(next_url, **kw):
                yield item

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

    def get_session(self, username, password):
        """Return a 'requests' session object
        """
        session = requests.Session()
        session.auth = (username, password)
        return session

    def fail(self, message, status):
        """Raise a SyncError
        """
        raise SyncError(message, status)

    def add_status_message(self, message, level="info"):
        """Set a status message
        """
        return self.context.plone_utils.addPortalMessage(message, level)

    def get_annotation(self):
        return IAnnotations(self.portal)

    def get_storage(self, key=None):
        """Return a ready to use storage for the given key
        """
        if key is None:
            key = self.url

        if not self.storage.get(key):
            self.storage[key] = OOBTree()
            self.storage[key]["data"] = OOBTree()
            self.storage[key]["index"] = OOBTree()
            self.storage[key]["users"] = OOBTree()
        return self.storage[key]

    @property
    def storage(self):
        annotation = self.get_annotation()
        if annotation.get(SYNC_STORAGE) is None:
            annotation[SYNC_STORAGE] = OOBTree()
        return annotation[SYNC_STORAGE]

    def flush_storage(self):
        annotation = self.get_annotation()
        if annotation.get(SYNC_STORAGE) is not None:
            del annotation[SYNC_STORAGE]

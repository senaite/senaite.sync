# -*- coding: utf-8 -*-
#
# Copyright 2017-2017 SENAITE LIMS.

import urllib
import urlparse
import requests

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

        # Handle Form Submit
        form = self.request.form
        if not form.get("submitted", False):
            return self.template()

        # Clear the storage and return
        if form.get("clear", False):
            self.flush_storage()
            message = _("Cleared Data Storage")
            self.add_status_message(message, "info")
            return self.template()

        # Fetch the data into the storage
        if form.get("fetch", False):
            url = form.get("url", None)
            username = form.get("ac_name", None)
            password = form.get("ac_password", None)

            # check if all mandatory fields have values
            if not all([url, username, password]):
                message = _("Please fill in all required fields")
                self.add_status_message(message, "error")
                return self.template()
            else:
                self.url = url
                self.username = username
                self.password = password

            # initialize the session
            self.session = self.get_session(username, password)

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

            # Start the fetch process
            self.fetch()

        # always render the template
        return self.template()

    def fetch(self):
        """Fetch the data from the source
        """

        # Fetch Bika Setup Folder
        bikasetup = self.get_first_item("bikasetup", complete=True)
        self.store(bikasetup.get("uid"), bikasetup)

        # Fetch all Bika Setup Items
        for folder in self.yield_items("search", path=bikasetup.get("path"), depth=1, complete=True):
            self.store(folder.get("uid"), folder)
            for item in self.yield_items("search", path=folder.get("path"), depth=1, complete=True):
                self.store(item.get("uid"), item)

        # Fetch Method Folder
        methodfolder = self.get_first_item("methods", complete=True)
        self.store(methodfolder.get("uid"), methodfolder)

        # Fetch all Methods
        for item in self.yield_items("search", path=methodfolder.get("path"), depth=1, complete=True):
            self.store(item.get("uid"), item)

        # Fetch Client Folder
        clientfolder = self.get_first_item("clientfolder", complete=True)
        self.store(clientfolder.get("uid"), clientfolder)

        # Fetch all Clients, Contacts, ARs, Samples, Attachments ...
        for item in self.yield_items("search", path=clientfolder.get("path"), depth=1, complete=True):
            self.store(item.get("uid"), item)

        # Fetch Worksheet Folder
        worksheetfolder = self.get_first_item("worksheetfolder", complete=True)
        self.store(worksheetfolder.get("uid"), worksheetfolder)

        # Fetch Worksheets
        for item in self.yield_items("search", path=worksheetfolder.get("path"), depth=1, complete=True):
            self.store(item.get("uid"), item)

    def store(self, key, value):
        """Store item in storage
        """
        storage = None
        if self.storage.get(self.url):
            storage = self.storage[self.url]
        else:
            storage = OOBTree()
            self.storage[self.url] = storage

        # store the data
        storage[key] = value

        # Create indexes
        for index in ["path", "id", "portal_type"]:
            index_key = "by_{}".format(index)
            if not storage.get(index_key):
                storage[index_key] = OOBTree()
            if not storage[index_key].get(key):
                storage[index_key][key] = []
            storage[index_key][key].append(value.get(index))

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
            message = "Could not connect to {} Please check your URL.".format(api_url)
            logger.error(e)
            self.add_status_message(message, "error")
            return {}
        status = response.status_code
        if status != 200:
            message = "GET returned Status Code {}. Please check your URL.".format(status)
            self.add_status_message(message, "error")
            return {}
        return response.json()

    def yield_items(self, url_or_endpoint, **kw):
        """Yield the full items of all pages
        """
        data = self.get_json(url_or_endpoint, **kw)
        for item in data.get("items", []):
            yield item

        next_url = data.get("next")
        if next_url:
            for item in self.yield_items(next_url, **kw):
                yield item

    def get_api_url(self, url_or_endpoint, **kw):
        """Create an API URL
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
        """Return a session object
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

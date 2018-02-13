# -*- coding: utf-8 -*-
#
# Copyright 2017-2017 SENAITE LIMS.


from BTrees.OOBTree import OOBTree

from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from senaite.sync.importstep import ImportStep

from zope.interface import implements
from zope.annotation.interfaces import IAnnotations

from plone import protect

from senaite import api
from senaite.sync.browser.interfaces import ISync
from senaite.sync import _
from senaite.sync.fetchstep import FetchStep
from senaite.sync.souphandler import delete_soup

SYNC_STORAGE = "senaite.sync"


class Sync(BrowserView):
    """Sync Controller View
    """
    implements(ISync)

    template = ViewPageTemplateFile("templates/sync.pt")

    def __init__(self, context, request):
        super(BrowserView, self).__init__(context, request)
        self.context = context
        self.request = request

        # VARIABLES TO BE USED IN FETCH AND IMPORT STEPS
        self.domain_name = None
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

        # Handle "Import" action
        if form.get("import", False):
            domain_name = form.get("domain_name", None)
            # initialize the session
            storage = self.get_storage(domain_name)
            url = storage["credentials"]["url"]
            username = storage["credentials"]["username"]
            password = storage["credentials"]["password"]
            content_types = storage["credentials"]["content_types"]
            data = {
                "url": url,
                "domain_name": domain_name,
                "ac_name": username,
                "ac_password": password,
                "content_types": content_types,
            }
            step = ImportStep(data)
            step.run()
            return self.template()

        # Handle "Clear this Storage" action
        if form.get("clear_storage", False):
            domain = form.get("domain_name", None)
            del self.storage[domain]
            delete_soup(self.portal, domain)
            message = _("Cleared Storage {}".format(domain))
            self.add_status_message(message, "info")
            return self.template()

        # Handle "Fetch" action
        if form.get("fetch", False):

            url = form.get("url", "")
            if not url.startswith("http"):
                url = "http://{}".format(url)
            domain_name = form.get("domain_name", None)
            username = form.get("ac_name", None)
            password = form.get("ac_password", None)
            # check if all mandatory fields have values
            if not all([domain_name, url, username,
                        password]):
                message = _("Please fill in all required fields")
                self.add_status_message(message, "error")
                return self.template()

            ct = form.get("content_types", None)
            if ct:
                content_types = [t.strip() for t in ct.split(",") if t]
            else:
                content_types = None
            data = {
                "url": url,
                "domain_name": domain_name,
                "ac_name": username,
                "ac_password": password,
                "content_types": content_types,
            }

            fs = FetchStep(data)
            verified, message = fs.verify()
            if verified:
                fs.run()
                self.add_status_message(message, "info")
            else:
                self.add_status_message(message, "error")

        # always render the template
        return self.template()

    def add_status_message(self, message, level="info"):
        """Set a portal status message
        """
        return self.context.plone_utils.addPortalMessage(message, level)

    def get_annotation(self):
        """Annotation storage on the portal object
        """
        return IAnnotations(self.portal)

    def get_storage(self, domain=None):
        """Return a ready to use storage for the given domain (key)
        """
        if domain is None:
            domain = len(self.storage)

        if not self.storage.get(domain):
            self.storage[domain] = OOBTree()
            self.storage[domain]["credentials"] = OOBTree()
            self.storage[domain]["registry"] = OOBTree()
            self.storage[domain]["ordered_uids"] = []
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

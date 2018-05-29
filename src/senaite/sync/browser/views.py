# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.SYNC
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.

from BTrees.OOBTree import OOBTree
from DateTime import DateTime
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone import protect
from senaite import api
from senaite.sync import _
from senaite.sync.browser.interfaces import ISync
from senaite.sync.importstep import ImportStep
from senaite.sync.souphandler import delete_soup
from senaite.sync.updatestep import UpdateStep
from zope.annotation.interfaces import IAnnotations
from zope.interface import implements

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

        if not form.get("dataform", False):
            return self.template()

        domain_name = form.get("domain_name", None)

        # Handle "Clear this Storage" action
        if form.get("clear_storage", False):
            del self.storage[domain_name]
            delete_soup(self.portal, domain_name)
            message = _("Cleared Storage {}".format(domain_name))
            self.add_status_message(message, "info")
            return self.template()

        # Get the necessary data for the domain
        storage = self.get_storage(domain_name)
        credentials = storage["credentials"]
        config = storage["configuration"]

        # Handle "Import" action
        if form.get("import", False):
            step = ImportStep(credentials, config)

        # Handle "Update" action
        else:
            fetch_time = form.get("mod_date_limit", None) or \
                storage.get("last_fetch_time", None)
            if not fetch_time:
                message = 'Cannot get last fetched time, please re-run ' \
                          'the Fetch step.'
                self.add_status_message(message, "error")
                return self.template()
            if isinstance(fetch_time, str):
                try:
                    fetch_time = DateTime(fetch_time)
                except:
                    message = 'Please enter a valid Date & Time'
                    self.add_status_message(message, "error")
                    return self.template()

            step = UpdateStep(credentials, config, fetch_time)

        step.run()
        return self.template()

    def get_storage_config(self, domain_name, config_name, default = None):
        """ Get the advanced configuration setting for a given domain
        :param config_name: advanced configuration section name
        :param default: default value if configuration value is not set
        :return:
        """
        storage = self.get_storage(domain_name)
        return storage["configuration"].get(config_name, default)

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


class ContentTypesView:
    """ A view to list all the Content Types existing on the portal.
    """

    template = ViewPageTemplateFile("templates/content_types.pt")

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def __call__(self):
        return self.template()

    def get_content_types(self):
        return api.get_tool("portal_types").listContentTypes()

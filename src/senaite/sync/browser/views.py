# -*- coding: utf-8 -*-
#
# Copyright 2017-2017 SENAITE LIMS.

from BTrees.OOBTree import OOBTree

from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from zope.interface import implements
from zope.annotation.interfaces import IAnnotations

from plone import protect

from senaite import api
from senaite.sync import logger
from senaite.sync.browser.interfaces import ISync

API = "senaite/v1"
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

    def __call__(self):
        protect.CheckAuthenticator(self.request.form)
        logger.info("SYNC CONTROLLER CALLED")
        self.portal = api.get_portal()
        self.request.set('disable_plone.rightcolumn', 1)

        form = self.request.form
        if form.get("submitted", False) and form.get("sync", False):
            logger.info("TRIGGER SYNC")

        return self.template()

    def get_annotation(self):
        return IAnnotations(self.portal)

    @property
    def storage(self):
        annotation = self.get_annotation()
        if annotation.get(SYNC_STORAGE) is None:
            annotation[SYNC_STORAGE] = OOBTree()
        return annotation[SYNC_STORAGE]

    def flush(self):
        annotation = self.get_annotation()
        if annotation.get(SYNC_STORAGE) is not None:
            del annotation[SYNC_STORAGE]

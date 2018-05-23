# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.SYNC
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.
import senaite.sync.utils as u
from Products.Five import BrowserView
from plone import protect
from senaite import api
from senaite.sync import logger
from senaite.sync.browser.interfaces import ISync
from senaite.sync.browser.views import Sync, SYNC_STORAGE
from zope.interface import implements


class AutoSync(BrowserView):
    """
    A View to be called by clock server periodically in order to run Auto Sync.
    With an authentication required, it will go through all the domains
    registered in the system and run Update Step
    """
    implements(ISync)

    def __init__(self, context, request):
        super(BrowserView, self).__init__(context, request)
        self.context = context
        self.request = request

    def __call__(self):
        protect.CheckAuthenticator(self.request.form)

        logger.info("**** AUTO SYNC STARTED ****")

        self.portal = api.get_portal()
        storage = u.get_annotation(self.portal)[SYNC_STORAGE]

        for domain_name, values in storage.iteritems():

            # Check if Auto-Sync is enabled for this Remote
            if not values["configuration"]["auto_sync"]:
                continue

            logger.info("Updating data with: '{}' ".format(domain_name))
            self.request.form["dataform"] = 1
            self.request.form["update"] = 1
            self.request.form["domain_name"] = domain_name
            response = Sync(self.context, self.request)
            response()

        logger.info("**** AUTO SYNC FINISHED ****")
        return "Done..."

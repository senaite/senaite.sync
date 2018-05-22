# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.SYNC
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.
from DateTime import DateTime
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from zope.interface import implements

from plone import protect

from senaite import api
from senaite.sync import logger
from senaite.sync.browser.interfaces import ISync
from senaite.sync.browser.views import Sync, SYNC_STORAGE
import senaite.sync.utils as u


class AutoSync(BrowserView):
    """
    A View to be called by clock server periodically in order to run Auto Sync.
    With an authentication required, it will go through all the domains
    registered in the system and run 1. Fetch, 2. Import, 3. Clear steps for
    each of them.
    """
    implements(ISync)

    def __init__(self, context, request):
        super(BrowserView, self).__init__(context, request)
        self.context = context
        self.request = request

    def __call__(self):
        protect.CheckAuthenticator(self.request.form)
        self.portal = api.get_portal()

        # Credentials storage must be filled beforehand. Users with enough
        # privileges can add domains from 'edit_auto_sync' view.
        storage = u.get_annotation(self.portal)[SYNC_STORAGE]

        logger.info("**** AUTO SYNC STARTED ****")
        for domain_name, values in storage.iteritems():
            if not values["configuration"]["auto_sync"]:
                continue
            logger.info("Fetching data for: {} ".format(domain_name))
            self.request.form["dataform"] = 1
            self.request.form["complement"] = 1
            self.request.form["domain_name"] = domain_name
            self.request.form["mod_date_limit"] = DateTime().strftime(
                                                        u._default_date_format)
            response = Sync(self.context, self.request)
            response()

        logger.info("**** AUTO SYNC FINISHED ****")
        return "Done..."

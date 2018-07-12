# -*- coding: utf-8 -*-
#
# Copyright 2017-2018 SENAITE SYNC.

import re

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone import protect
from senaite import api
from senaite.sync import _
from senaite.sync import utils
from senaite.sync.browser.interfaces import ISync
from senaite.sync.browser.views import Sync
from senaite.sync.fetchstep import FetchStep
from zope.interface import implements

SYNC_STORAGE = "senaite.sync"
PREFIX_SPECIAL_CHARACTERS = u"*.!$%&/()=-+:'`´^"


class Add(Sync):
    """ Add new sync instance view
    """
    implements(ISync)

    template = ViewPageTemplateFile("templates/add.pt")

    def __init__(self, context, request):
        super(Sync, self).__init__(context, request)

    def __call__(self):
        protect.CheckAuthenticator(self.request.form)

        self.portal = api.get_portal()
        self.request.set('disable_plone.rightcolumn', 1)
        self.request.set('disable_border', 1)

        # Handle form submit
        form = self.request.form
        fetchform = form.get("fetchform", False)

        if not fetchform:
            return self.template()

        self.url = form.get("url", "")
        if not self.url.startswith("http"):
            self.url = "https://{}".format(self.url)

        self.domain_name = form.get("domain_name", None)
        self.username = form.get("ac_name", None)
        self.password = form.get("ac_password", None)
        self.certificate_file = form.get("certificate_file", None)

        # check if all mandatory fields have values
        if not all([self.domain_name, self.url, self.username, self.password]):
            message = _("Please fill in all required fields")
            self.add_status_message(message, "error")
            return self.template()

        self.auto_sync = (form.get("auto_sync") == 'on')

        self.import_settings = (form.get("import_settings") == 'on')
        self.import_users = (form.get("import_users") == 'on')
        self.import_registry = (form.get("import_registry") == 'on')

        self.remote_prefix = form.get("remote_prefix", None)
        self.local_prefix = form.get("local_prefix", None)

        self.full_sync_types = utils.filter_content_types(
                                    form.get("full_sync_types"))
        self.unwanted_content_types = utils.filter_content_types(
                                    form.get("unwanted_content_types"))
        self.read_only_types = utils.filter_content_types(
                                    form.get("read_only_types"))
        self.update_only_types = utils.filter_content_types(
                                    form.get("update_only_types"))
        self.prefixable_types = utils.filter_content_types(
                                    form.get("prefixable_types"))

        # Prefix Validation
        if not self.validate_prefix():
            return self.template()

        credentials = dict(
            url=self.url,
            domain_name=self.domain_name,
            ac_name=self.username,
            ac_password=self.password,
            certificate_file=self.certificate_file)

        config = dict(
            auto_sync=self.auto_sync,
            import_settings=self.import_settings,
            import_users=self.import_users,
            import_registry=self.import_registry,
            remote_prefix=self.remote_prefix,
            local_prefix=self.local_prefix,
            full_sync_types=self.full_sync_types,
            unwanted_content_types=self.unwanted_content_types,
            read_only_types=self.read_only_types,
            update_only_types=self.update_only_types,
            prefixable_types=self.prefixable_types,
        )

        fs = FetchStep(credentials, config)
        verified, message = fs.verify()
        if verified:
            fs.run()
            self.add_status_message(message, "info")
        else:
            self.add_status_message(message, "error")

        # render the template
        return self.template()

    def _get_attr(self, attr_name, default):
        """ Get an attribute for HTML elements
        :param attr_name:
        :param default:
        :return:
        """
        res = getattr(self, attr_name, default)
        if isinstance(res, basestring):
            res = res.replace(" ", "")

        if isinstance(res, (list, tuple)):
            res = ", ".join(res)

        return res

    def validate_prefix(self):
        """ Validate Prefix & Prefixable Types convenience
        """
        if not self.remote_prefix:
            # No prefix and no prefixable types, everything is okay
            if not self.prefixable_types:
                return True

            # There are prefixable types but not a valid prefix
            self.add_status_message("Please enter a valid Prefix.", "error")
            return False

        self.remote_prefix = self.remote_prefix.strip(PREFIX_SPECIAL_CHARACTERS)
        if not self.remote_prefix:
            self.add_status_message("Invalid Remote Prefix!", "error")
            return False

        if len(self.remote_prefix) > 3:
            self.add_status_message("Remote's Prefix is too long!!",
                                    "warning")

        if not self.prefixable_types:
            self.add_status_message("Please enter valid Content Types "
                                    "to be created with the Prefix.",
                                    "error")
            return False

        # Check if Prefix is used in ID generator for any content type
        config_map = api.get_bika_setup().getIDFormatting()
        for config in config_map:
            form = config.get("form", "")
            if re.match(self.remote_prefix, form, re.I):
                pt = config.get("portal_type")
                self.add_status_message("Introduced Remote Prefix is being"
                                        " used in {} ID's.".format(pt), "error")
                return False
        return True

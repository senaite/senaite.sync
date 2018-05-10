# -*- coding: utf-8 -*-
#
# Copyright 2017-2018 SENAITE SYNC.

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone import protect
from senaite import api
from senaite.sync import _
from senaite.sync.browser.interfaces import ISync
from senaite.sync.browser.views import Sync
from senaite.sync.fetchstep import FetchStep
from senaite.sync import utils
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
        dataform = form.get("dataform", False)
        if not any([fetchform, dataform]):
            return self.template()

        # Handle "Fetch" action
        if form.get("fetch", False):

            url = form.get("url", "")
            if not url.startswith("http"):
                url = "https://{}".format(url)
            domain_name = form.get("domain_name", None)
            username = form.get("ac_name", None)
            password = form.get("ac_password", None)
            # check if all mandatory fields have values
            if not all([domain_name, url, username, password]):
                message = _("Please fill in all required fields")
                self.add_status_message(message, "error")
                return self.template()

            import_settings = (form.get("import_settings") == 'on')
            import_users = (form.get("import_users") == 'on')
            import_registry = (form.get("import_registry") == 'on')
            content_types = utils.filter_content_types(
                                        form.get("content_types"))
            unwanted_content_types = utils.filter_content_types(
                                        form.get("unwanted_content_types"))

            prefix = form.get("prefix", None)
            prefixable_types = utils.filter_content_types(
                                        form.get("prefixable_types"))

            # Prefix Validation
            if prefix:
                prefix = prefix.strip(PREFIX_SPECIAL_CHARACTERS)
                if not prefix:
                    self.add_status_message("Invalid Prefix!", "error")
                    return self.template()

                if len(prefix) > 3:
                    self.add_status_message("Long Prefix!", "warning")

                if not prefixable_types:
                    self.add_status_message("Please enter valid Content Types "
                                    "to be created with the Prefix.", "error")
                    return self.template()
            else:
                if prefixable_types:
                    self.add_status_message("Please enter a valid Prefix.",
                                            "error")
                    return self.template()

            data = {
                "url": url,
                "domain_name": domain_name,
                "ac_name": username,
                "ac_password": password,
                "content_types": content_types,
                "unwanted_content_types": unwanted_content_types,
                "import_settings": import_settings,
                "import_users": import_users,
                "import_registry": import_registry,
                "prefix": prefix,
                "prefixable_types": prefixable_types,
            }

            fs = FetchStep(data)
            verified, message = fs.verify()
            if verified:
                fs.run()
                self.add_status_message(message, "info")
            else:
                self.add_status_message(message, "error")

        # render the template
        return self.template()


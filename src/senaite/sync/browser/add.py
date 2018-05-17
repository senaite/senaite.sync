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

        if not fetchform:
            return self.template()

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

        remote_prefix = form.get("remote_prefix", None)
        local_prefix = form.get("local_prefix", None)

        full_sync_types = utils.filter_content_types(
                                    form.get("full_sync_types"))
        unwanted_content_types = utils.filter_content_types(
                                    form.get("unwanted_content_types"))
        read_only_types = utils.filter_content_types(
                                    form.get("read_only_types"))
        update_only_types = utils.filter_content_types(
                                    form.get("update_only_types"))
        prefixable_types = utils.filter_content_types(
                                    form.get("prefixable_types"))

        # Prefix Validation
        if remote_prefix:
            remote_prefix = remote_prefix.strip(PREFIX_SPECIAL_CHARACTERS)
            if not remote_prefix:
                self.add_status_message("Invalid Remote Prefix!", "error")
                return self.template()

            if len(remote_prefix) > 3:
                self.add_status_message("Remote's Prefix is too long!!",
                                        "warning")

            if not prefixable_types:
                self.add_status_message("Please enter valid Content Types "
                                        "to be created with the Prefix.",
                                        "error")
                return self.template()
        else:
            if prefixable_types:
                self.add_status_message("Please enter a valid Prefix.",
                                        "error")
                return self.template()

        credentials = dict(
            url=url,
            domain_name=domain_name,
            ac_name=username,
            ac_password=password)

        config = dict(
            import_settings=import_settings,
            import_users=import_users,
            import_registry=import_registry,
            remote_prefix=remote_prefix,
            local_prefix=local_prefix,
            full_sync_types=full_sync_types,
            unwanted_content_types=unwanted_content_types,
            read_only_types=read_only_types,
            update_only_types=update_only_types,
            prefixable_types=prefixable_types,
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


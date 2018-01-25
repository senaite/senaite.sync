
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from zope.interface import implements

from plone import protect

from senaite import api
from senaite.sync import logger
from senaite.sync.browser.interfaces import ISync
from senaite.sync.browser.views import Sync
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
        storage = u.get_credentials_storage(self.portal)
        logger.info("**** AUTO SYNC STARTED ****")

        for key, value in storage.items():
            # First step is fetching data for the domain
            logger.info("Fetching data for: {} ".format(key))
            self.request.form["fetchform"] = 1
            self.request.form["fetch"] = 1
            self.request.form["url"] = value["url"]
            self.request.form["ac_name"] = value["ac_username"]
            self.request.form["ac_password"] = value["ac_password"]
            response = Sync(self.context, self.request)
            response()

            # Second step is importing fetched data
            self.request.form["fetchform"] = False
            self.request.form["fetch"] = False

            logger.info("Importing data for: {} ".format(key))
            self.request.form["dataform"] = 1
            self.request.form["import"] = 1
            self.request.form["domain"] = value["url"]
            response = Sync(self.context, self.request)
            response()

            # The last step is clearing fetched data from the storage to avoid
            # increase of the memory
            logger.info("Clearing storage data for: {} ".format(key))
            self.request.form["import"] = False
            self.request.form["clear_storage"] = 1
            response = Sync(self.context, self.request)
            response()

        logger.info("**** AUTO SYNC FINISHED ****")
        return "Done..."


class EditAutoSync(BrowserView):
    """
    View for editing domains and their data which will be used for
    Auto Synchronization. From this view, user cannot run fetch or import step,
    but can only add/remove remote instance (domain) parameters.
    """
    implements(ISync)

    template = ViewPageTemplateFile("templates/edit_sync_domains.pt")

    def __init__(self, context, request):
        super(BrowserView, self).__init__(context, request)
        self.context = context
        self.request = request

    def __call__(self):
        protect.CheckAuthenticator(self.request.form)

        self.portal = api.get_portal()
        self.request.set('disable_plone.rightcolumn', 1)
        self.request.set('disable_border', 1)

        # Handle form submit
        form = self.request.form
        if form.get("add_domain", False):
            self.add_new_credential(form)
        elif form.get("remove_domain", False):
            name = form.get("domain_name")
            self.remove_domain(name)

        return self.template()

    def get_domains(self):
        """
        This function returns all the domains registered for Auto Sync.
        :return: dictionary of the domains.
        """
        storage = u.get_credentials_storage(self.portal)
        return storage

    def add_new_credential(self, data):
        """
        Adds new domain parameters to the credentials storage.
        :param data: parameters dict of the new domain.
        :return:
        """
        if not isinstance(data, dict):
            return

        required_indexes = ["domain_name", "url", "ac_username", "ac_password"]
        credentials = {}
        for i in required_indexes:
            if not data.get(i, False):
                return
            credentials[i] = data[i]

        name = credentials.get("domain_name")
        storage = u.get_credentials_storage(self.portal)
        # Domain names must be unique
        if storage.get(name, False):
            return

        # store the data
        storage[name] = credentials
        logger.info("New credentials were added for: {}".format(name))

    def remove_domain(self, domain_name):
        """
        Removes selected domain from the credentials storage.
        :param domain_name: name of the domain to be removed
        :return:
        """
        storage = u.get_credentials_storage(self.portal)
        if storage.get(domain_name, False):
            del storage[domain_name]
            logger.info("Domain Removed: {}".format(domain_name))

    def reset(self):
        """Drop the whole storage of credentials
        """
        annotation = self.get_annotation()
        if annotation.get(u.SYNC_CREDENTIALS) is not None:
            del annotation[u.SYNC_CREDENTIALS]

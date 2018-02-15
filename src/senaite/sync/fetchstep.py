# -*- coding: utf-8 -*-
#
# Copyright 2017-2018 SENAITE SYNC.

import transaction

from BTrees.OOBTree import OOBTree

from senaite.sync.syncstep import SyncStep

from senaite.sync import logger
from senaite.sync import _
from senaite.sync.souphandler import SoupHandler
from senaite.sync import utils

SKIP_PORTAL_TYPES = ["SKIP"]


class FetchStep(SyncStep):
    """
    Fetch step of data migration.
    """

    def run(self):
        """
        :return:
        """
        logger.info("*** FETCH STARTED {} ***".format(
                                                self.domain_name))
        self._fetch_registry_records(keys=["bika", "senaite"])
        self._fetch_settings()
        self._fetch_data()
        logger.info("*** FETCH FINISHED {} ***".format(
                                                self.domain_name))
        return

    def verify(self):
        """
        Verifies if the credentials are valid to start a new session.
        :return:
        """
        self.session = self.get_session()
        # try to get the version of the remote JSON API
        version = self.get_version()
        if not version or not version.get('version'):
            message = _("Please install senaite.jsonapi on the source system")
            return False, message

        # try to get the current logged in user
        user = self.get_authenticated_user()
        if not user or user.get("authenticated") is False:
            message = _("Wrong username/password")
            return False, message

        # remember the credentials in the storage
        storage = self.get_storage()
        storage["credentials"]["url"] = self.url
        storage["credentials"]["username"] = self.username
        storage["credentials"]["password"] = self.password
        message = "Fetching Data started for {}".format(self.domain_name)
        return True, message

    def get_version(self):
        """Return the remote JSON API version
        """
        return self.get_json("version")

    def get_authenticated_user(self):
        """Return the current logged in remote user
        """
        return self.get_first_item("users/current")

    def _fetch_data(self, window=1000, overlap=10):
        """Fetch data from the uid catalog in the source URL
        :param window: number of elements to be retrieved with each query to
                       the catalog
        :type window: int
        :param overlap: overlap between windows
        :type overlap: int
        :return:
        """
        logger.info("*** FETCHING DATA: {} ***".format(
            self.domain_name))
        storage = self.get_storage()
        storage["ordered_uids"] = []
        ordered_uids = storage["ordered_uids"]
        self.sh = SoupHandler(self.domain_name)
        # Dummy query to get overall number of items in the specified catalog
        catalog_data = self.get_json("search", catalog='uid_catalog', limit=1)
        # Knowing the catalog length compute the number of pages we will need
        # with the desired window size and overlap
        effective_window = window-overlap
        number_of_pages = (catalog_data["count"]/effective_window) + 1
        # Retrieve data from catalog in batches with size equal to window,
        # format it and insert it into the import soup
        for current_page in xrange(number_of_pages):
            start_from = (current_page * window) - overlap
            items = self.get_items("search", catalog='uid_catalog',
                                   limit=window, b_start=start_from)
            if not items:
                logger.error("CAN NOT GET ITEMS FROM {} TO {}".format(
                    start_from, start_from+window))
            for item in items:
                # skip object or extract the required data for the import
                if item.get("portal_type", "SKIP") in SKIP_PORTAL_TYPES:
                    logger.info("Skipping unnecessary portal type: {}"
                                .format(item))
                    continue
                data_dict = utils.get_soup_format(item)
                rec_id = self.sh.insert(data_dict)
                ordered_uids.insert(0, data_dict['remote_uid'])

            logger.info("{} of {} pages fetched...".format(current_page+1,
                                                           number_of_pages))
        logger.info("*** FETCHING DATA FINISHED: {} ***".format(
            self.domain_name))

        transaction.commit()

    def _fetch_settings(self, keys=None):
        """Fetch source instance settings by keyword
        """
        logger.info("*** Fetching Settings: {} ***".format(self.domain_name))
        storage = self.get_storage()
        settings_store = storage["settings"]

        if keys is None:
            retrieved_settings = self._get_settings_by_key()
        else:
            retrieved_settings = []
            for key in keys:
                retrieved_settings += self._get_settings_by_key(key)

        for setting_dict in retrieved_settings:
            for key in setting_dict.keys():
                if not setting_dict[key]:
                    continue
                settings_store[key] = setting_dict[key]

    def _get_settings_by_key(self, key=None):
        """ Return the settings from the source instance associated
         to the keyword. If key is None it will return all the settings
        """
        if key is None:
            return self.get_items("settings")
        return self.get_items("/".join(["settings", key]))

    def _fetch_registry_records(self, keys=None):
        """Fetch configuration registry records of interest (those associated
        to the keywords passed) from source instance
        """
        logger.info("*** Fetching Registry Records: {} ***".format(
            self.domain_name))
        storage = self.get_storage()
        registry_store = storage["registry"]
        retrieved_records = {}

        if keys is None:
            retrieved_records["all"] = self._get_registry_records_by_key()
        else:
            for key in keys:
                retrieved_records[key] = self._get_registry_records_by_key(key)

        for key in retrieved_records.keys():
            if not retrieved_records[key]:
                continue
            registry_store[key] = OOBTree()
            for record in retrieved_records[key][0].keys():
                registry_store[key][record] = retrieved_records[key][0][record]
        logger.info("*** Registry Records Fetched: {} ***".format(
            self.domain_name))

    def _get_registry_records_by_key(self, key=None):
        """Return the values of the registry records
        associated to the specified keyword in the source instance.
        If keyword is None it returns the whole registry
        """
        if key is None:
            return self.get_items("registry")

        return self.get_items("registry/{}".format(key))

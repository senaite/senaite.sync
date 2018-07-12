# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.SYNC
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.

import transaction

from BTrees.OOBTree import OOBTree

from datetime import datetime
from DateTime import DateTime

from senaite import api
from senaite.sync.syncstep import SyncStep
from senaite.sync import logger
from senaite.sync import _
from senaite.sync.souphandler import SoupHandler
from senaite.sync.souphandler import REMOTE_UID
from senaite.sync import utils


class FetchStep(SyncStep):
    """
    Fetch step of data migration. During this step, the data must be retrieved
    from the source and saved in 'souper' table for the domain.
    """
    def __init__(self, credentials, config):
        super(FetchStep, self).__init__(credentials, config)
        self.credentials = credentials
        self.config = config

    def run(self):
        """
        :return:
        """
        logger.info("*** FETCH STARTED {} ***".format(
                                                self.domain_name))
        if self.import_registry:
            self._fetch_registry_records(keys=["bika", "senaite"])
        if self.import_settings:
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

        for k, v in self.credentials.iteritems():
            storage["credentials"][k] = v

        for k, v in self.config.iteritems():
            storage["configuration"][k] = v

        storage["last_fetch_time"] = DateTime()

        message = "Data fetched and saved: {}".format(self.domain_name)
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
        start_time = datetime.now()
        storage = self.get_storage()
        storage["ordered_uids"] = []
        ordered_uids = storage["ordered_uids"]
        self.sh = SoupHandler(self.domain_name)
        # Dummy query to get overall number of items in the specified catalog
        query = {
            "url_or_endpoint": "search",
            "catalog": 'uid_catalog',
            "limit": 1
        }
        if self.full_sync_types:
            types = list()
            types.extend(self.full_sync_types + self.prefixable_types +
                         self.update_only_types + self.read_only_types)
            query["portal_type"] = types
        cd = self.get_json(**query)
        # Knowing the catalog length compute the number of pages we will need
        # with the desired window size and overlap
        effective_window = window-overlap
        # When we receive an error message in JSON response or we
        # don't get any response at all the key 'count' doesn't exist.
        if not cd.get("count", None):
            error_message = "Error message: {}".format(cd.get('message', None) or '')
            logger.error(
                "A query to the JSON API returned and error. {}".format(error_message)
            )
            return

        number_of_pages = (cd["count"]/effective_window) + 1
        # Retrieve data from catalog in batches with size equal to window,
        # format it and insert it into the import soup
        for current_page in xrange(number_of_pages):
            start_from = (current_page * window) - overlap
            query["limit"] = window
            query["b_start"] = start_from
            items = self.get_items_with_retry(**query)
            if not items:
                logger.error("CAN NOT GET ITEMS FROM {} TO {}".format(
                    start_from, start_from+window))
            for item in items:
                # skip object or extract the required data for the import
                if not self.is_item_allowed(item):
                    continue
                data_dict = utils.get_soup_format(item)
                rec_id = self.sh.insert(data_dict)
                ordered_uids.insert(0, data_dict[REMOTE_UID])
                if not self._parents_fetched(item):
                    logger.warning("Some parents are missing: {} ".format(item))

            utils.log_process(task_name="Pages fetched", started=start_time,
                              processed=current_page+1, total=number_of_pages)

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
        return self.get_items("/".join(["registry", key]))

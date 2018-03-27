# -*- coding: utf-8 -*-
#
# Copyright 2017-2018 SENAITE SYNC.

from datetime import datetime
from DateTime import DateTime

from senaite import api
from senaite.sync.importstep import ImportStep

from senaite.sync import logger, utils
from senaite.sync.souphandler import SoupHandler, REMOTE_UID, LOCAL_UID


class ComplementStep(ImportStep):
    """ A Complement Step to be run after the Import Step. Might be useful when
    import takes too long and there are objects that have been created during
    that time.
    """

    def __init__(self, data):
        ImportStep.__init__(self, data)
        self.fetch_time = data.get("fetch_time", None)

    def run(self):
        """
        :return:
        """
        self.session = self.get_session()
        self._fetch_data()
        self._create_new_objects()
        self._import_missing_objects()
        return

    def _fetch_data(self):
        """ Fetch necessary objects and save their UIDs in memory.
        """
        logger.info("*** COMPLEMENT STEP - FETCHING DATA: {} ***".format(
            self.domain_name))

        self.uids = []
        self.sh = SoupHandler(self.domain_name)
        # Dummy query to get overall number of items in the specified catalog
        query = {
            "url_or_endpoint": "search",
            "catalog": 'uid_catalog',
            "limit": 1
        }
        if self.content_types:
            query["portal_type"] = self.content_types
        cd = self.get_json(**query)
        # Knowing the catalog length compute the number of pages we will need
        # with the desired window size and overlap
        window = 500
        overlap = 5
        effective_window = window-overlap
        number_of_pages = (cd["count"]/effective_window) + 1
        # Retrieve data from catalog in batches with size equal to window,
        # format it and insert it into the import soup
        for current_page in xrange(number_of_pages):
            start_from = (current_page * window) - overlap
            query["complete"] = True
            query["limit"] = window
            query["b_start"] = start_from
            items = self.get_items(**query)
            if not items:
                logger.error("CAN NOT GET ITEMS FROM {} TO {}".format(
                    start_from, start_from+window))
            for item in items:
                # skip object or extract the required data for the import
                if not item or not item.get("portal_type", True):
                    continue
                modified = DateTime(item.get('modification_date'))
                if modified < self.fetch_time:
                    continue
                data_dict = utils.get_soup_format(item)
                rec_id = self.sh.insert(data_dict)
                self.uids.insert(0, data_dict[REMOTE_UID])

        logger.info("*** FETCH FINISHED. {} OBJECTS WILL BE UPDATED".format(
                                                        len(self.uids)))
        return

    def _import_missing_objects(self):
        """ For each UID from the fetched data, creates and updates objects
        step by step.
        :return:
        """
        logger.info("*** IMPORT DATA STARTED: {} ***".format(self.domain_name))

        self.sh = SoupHandler(self.domain_name)
        self.uids_to_reindex = []
        storage = self.get_storage()
        total_object_count = len(self.uids)
        start_time = datetime.now()

        for item_index, r_uid in enumerate(self.uids):
            row = self.sh.find_unique(REMOTE_UID, r_uid)
            logger.debug("Handling: {} ".format(row["path"]))
            self._handle_obj(row, handle_dependencies=False)

            # Log.info every 50 objects imported
            utils.log_process(task_name="Complement Step", started=start_time,
                              processed=item_index+1, total=total_object_count,
                              frequency=50)

        self.uids_to_reindex = list(set(self.uids_to_reindex))
        logger.info("Reindexing {} objects...".format(
                    len(self.uids_to_reindex)))
        for uid in self.uids_to_reindex:
            try:
                obj = api.get_object_by_uid(uid)
                obj.reindexObject()
            except Exception, e:
                rec = self.sh.find_unique(LOCAL_UID, uid)
                logger.error("Error while reindexing {} - {}"
                             .format(rec, e))
        self.uids_to_reindex = []

        # Mark all objects as non-updated for the next import.
        self.sh.reset_updated_flags()
        logger.info("*** IMPORT DATA FINISHED: {} ***".format(self.domain_name))
        return

    def _create_new_objects(self):
        """         """
        logger.info("*** CREATING NEW OBJECTS: {} ***".format(self.domain_name))

        self.sh = SoupHandler(self.domain_name)

        for item_index, r_uid in enumerate(self.uids):
            row = self.sh.find_unique(REMOTE_UID, r_uid)
            self._do_obj_creation(row)

        logger.info("***OBJ CREATION FINISHED: {} ***".format(self.domain_name))
        return

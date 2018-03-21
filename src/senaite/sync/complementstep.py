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
        self._import_missing_objects()
        return

    def _fetch_data(self):
        """ Fetch necessary objects and save their UIDs in memory.
        """
        logger.info("*** COMPLEMENT STEP - FETCHING DATA: {} ***".format(
            self.domain_name))

        self.uids = []
        self.sh = SoupHandler(self.domain_name)

        # TODO: Find another way to do it without waking up objects.
        query = {
            "url_or_endpoint": "search",
            "catalog": 'uid_catalog',
            "b_start": 0,
            "complete": "yes",
            "limit": 500
        }
        if self.content_types:
            query["portal_type"] = self.content_types
        items = self._yield_items(**query)
        for item in items:
            # skip object or extract the required data for the import
            if not item or not item.get("portal_type", True):
                continue
            data_dict = utils.get_soup_format(item)
            rec_id = self.sh.insert(data_dict)
            self.uids.insert(0, data_dict[REMOTE_UID])

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
            self._handle_obj(row)

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

    def _yield_items(self, url_or_endpoint, **kw):
        """ Walk through all objects and yield items filtering by their
        modification date.
        """
        data = self.get_json(url_or_endpoint, **kw)
        for item in data.get("items", []):
            if not item:
                continue
            modified = DateTime(item.get('modification_date'))
            if modified > self.fetch_time:
                yield item

        next_url = data.get("next")
        if next_url:
            for item in self.yield_items(next_url, **kw):
                if not item:
                    continue
                modified = DateTime(item.get('modification_date'))
                if modified > self.fetch_time:
                    yield item

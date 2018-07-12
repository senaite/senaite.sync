# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.SYNC
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.

from datetime import datetime

import transaction
from DateTime import DateTime

from senaite import api
from senaite.sync.importstep import ImportStep

from senaite.sync import logger, utils
from senaite.sync.souphandler import SoupHandler, REMOTE_UID, LOCAL_UID, \
                                     REMOTE_PATH, LOCAL_PATH


class UpdateStep(ImportStep):
    """ An Update Step to be run after the Import Step. Might be useful when
    import takes too long and there are objects that have been created during
    that time.
    """

    def __init__(self, credentials, config, fetch_time):
        ImportStep.__init__(self, credentials, config)
        self.fetch_time = fetch_time
        # Keep modification times in a dictionary to restore after Update Step
        self.modification_dates = dict()

    def run(self):
        """
        :return:
        """
        self.session = self.get_session()
        self._fetch_data()
        transaction.commit()
        self._create_new_objects()
        self._update_objects()
        self.restore_modification_dates()
        return

    def _fetch_data(self):
        """ Fetch necessary objects and save their UIDs in memory.
        """
        logger.info("*** UPDATE STEP - FETCHING DATA: {} ***".format(
            self.domain_name))

        self.records = list()
        self.waiting_records = list()
        self.sh = SoupHandler(self.domain_name)

        # Dummy query to get overall number of items in the specified catalog
        query = {
            "url_or_endpoint": "search",
            "catalog": 'uid_catalog',
            "recent_modified": utils.date_to_query_literal(self.fetch_time),
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
        window = 500
        overlap = 5
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
                    start_from, start_from + window))

            for item in items:
                # skip object or extract the required data for the import
                if not self.is_item_allowed(item):
                    continue

                data_dict = utils.get_soup_format(item)
                existing_rec = self.sh.find_unique(
                    REMOTE_UID, data_dict[REMOTE_UID])
                # If remote UID is in the souper table already, just check if
                # remote path of the object has been updated
                if existing_rec:
                    rem_path = data_dict.get(REMOTE_PATH)
                    if rem_path != existing_rec.get(REMOTE_PATH):
                        self.sh.update_by_remote_uid(**data_dict)
                    rec_id = existing_rec.get("rec_int_id")
                else:
                    rec_id = self.sh.insert(data_dict)
                    # It is possible that insert failed because of non-unique
                    # path value. We add this object to list and will insert
                    # after updating path of 'duplicate' object
                    if rec_id is False:
                        self.waiting_records.append(data_dict)
                        continue
                self.records.append(rec_id)

        # All path values were updated, there cannot be any repeating paths.
        # Time to insert waiting objects
        for record in self.waiting_records:
            rec_id = self.sh.insert(record)
            self.records.append(rec_id)

        storage = self.get_storage()
        storage["last_fetch_time"] = DateTime()
        logger.info("*** FETCH FINISHED. {} OBJECTS WILL BE UPDATED".format(
                                                        len(self.records)))
        return

    def _update_objects(self):
        """ For each UID from the fetched data, updates objects step by step.
        Does NOT do anything with dependencies!
        :return:
        """
        logger.info("*** IMPORT DATA STARTED: {} ***".format(self.domain_name))

        self.sh = SoupHandler(self.domain_name)
        self.uids_to_reindex = []
        total_object_count = len(self.records)
        start_time = datetime.now()

        for item_index, rec_id in enumerate(self.records):
            row = self.sh.get_record_by_id(rec_id, as_dict=True)
            if not row:
                continue
            logger.debug("Handling: {} ".format(row[REMOTE_PATH]))
            self._handle_obj(row, handle_dependencies=False)

            # Log.info every 50 objects imported
            utils.log_process(task_name="Update Step", started=start_time,
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

    def _handle_obj(self, row, handle_dependencies=False):
        """ Override super's method due to the following reasons:
            1.  No need to create object slugs, they are already created in
                '_create_new_objects step.
            2. If object has been modified in local, it should not be updated
                by the data from the Remote.
            3. No need to handle Dependencies.

        :param row: A row dictionary from the souper
        :type row: dict
        """
        r_uid = row.get(REMOTE_UID)
        try:
            if row.get("updated", "0") == "1":
                return True
            obj_path = row.get(LOCAL_PATH)
            obj = self.portal.unrestrictedTraverse(obj_path, None)
            time_modified = obj.modified()
            obj_data = self.get_json(r_uid, complete=True,
                                     workflow=True)

            rem_modified = DateTime(obj_data.get('modified'))
            if time_modified > rem_modified:
                logger.info("'{}' has been modified in local and will not be "
                            "updated".format(repr(obj)))
                return True

            self._update_object_with_data(obj, obj_data)

            # In the end, we will restore the modification time
            self.modification_dates[row[LOCAL_UID]] = time_modified
        except Exception, e:
            logger.error('Failed to handle {} : {} '.format(row, str(e)))

        return True

    def _create_new_objects(self):
        """ Creates all the new objects from source without setting any
        field data. We use this to skip handling dependencies process. If any
        dependency of the object is new (or recently modified), it must be
        handled during Update Step. So before updating objects with data,
        we must be sure that all its dependencies are created.
        """
        logger.info("*** CREATING NEW OBJECTS: {} ***".format(self.domain_name))

        self.sh = SoupHandler(self.domain_name)

        for idx, rec_id in enumerate(self.records):
            row = self.sh.get_record_by_id(rec_id, as_dict=True)
            try:
                if row:
                    self._do_obj_creation(row)
            except Exception, e:
                logger.error("Object creation failed for: {} ... {}".
                             format(row, str(e)))
            if (idx % 500) == 0:
                transaction.commit()
                logger.info(" {} objects created.".format(idx))
        logger.info("***OBJ CREATION FINISHED: {} ***".format(self.domain_name))
        return

    def restore_modification_dates(self):
        """ When objects are updated by Sync, their 'modified' time should not
        be updated. Otherwise, it can cause an infinite loop between source and
        destination instances, since Update step based on 'modified' times.
        It must be handled manually because reindexing object updates 'modified'
        attribute.
        https://docs.plone.org/4/en/develop/plone/content/manipulating.html
        """
        logger.info(" *** Restoring Old Modification Dates ***")

        for uid, mod_time in self.modification_dates.iteritems():
            obj = api.get_object_by_uid(uid)
            obj.setModificationDate(mod_time)
            obj.reindexObject(idxs=['modified'])

        logger.info(" *** Modification Dates Restored ***")
        return

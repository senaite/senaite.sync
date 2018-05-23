# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.SYNC
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.

import requests
import transaction

from Products.CMFPlone.utils import _createObjectByType
from Products.AdvancedQuery import Eq
from datetime import datetime
from senaite.jsonapi.fieldmanagers import ProxyFieldManager
from senaite.jsonapi.fieldmanagers import ComputedFieldManager
from senaite.sync.syncstep import SyncStep

from zope.component import getUtility
from zope.component import getAdapter
from zope.component.interfaces import IFactory

from plone import api as ploneapi
from plone.registry.interfaces import IRegistry
import plone.app.controlpanel as cp

from senaite import api
from senaite.jsonapi.interfaces import IFieldManager
from senaite.sync import logger
from senaite.sync import _
from senaite.sync.souphandler import SoupHandler
from senaite.sync.souphandler import REMOTE_UID, LOCAL_UID, REMOTE_PATH,\
                                     PORTAL_TYPE, LOCAL_PATH
from senaite.sync import utils

COMMIT_INTERVAL = 1000

CONTROLPANEL_INTERFACE_MAPPING = {
    'mail': [cp.mail.IMailSchema],
    'calendar': [cp.calendar.ICalendarSchema],
    'ram': [cp.ram.IRAMCacheSchema],
    'language': [cp.language.ILanguageSelectionSchema],
    'editing': [cp.editing.IEditingSchema],
    'usergroups': [cp.usergroups.IUserGroupsSettingsSchema,
                   cp.usergroups.ISecuritySchema, ],
    'search': [cp.search.ISearchSchema],
    'filter': [cp.filter.IFilterAttributesSchema,
               cp.filter.IFilterEditorSchema,
               cp.filter.IFilterSchema,
               cp.filter.IFilterTagsSchema],
    'maintenance': [cp.maintenance.IMaintenanceSchema],
    'markup': [cp.markup.IMarkupSchema,
               cp.markup.ITextMarkupSchema,
               cp.markup.IWikiMarkupSchema, ],
    'navigation': [cp.navigation.INavigationSchema],
    'security': [cp.security.ISecuritySchema],
    'site': [cp.site.ISiteSchema],
    'skins': [cp.skins.ISkinsSchema],
}


class ImportStep(SyncStep):
    """ Class for the Import step of the Synchronization. It must create and
    update objects based on previously fetched data.

    """
    fields_to_skip = ['id',  # Overriding ID's can remove prefixes
                      'excludeFromNav', 'constrainTypesMode', 'allowDiscussion']

    def __init__(self, credentials, config):
        SyncStep.__init__(self, credentials, config)
        # A list to keep UID's of an object chunk
        self.uids_to_reindex = []
        # An 'infinite recursion preventative' list of objects which are
        # being updated.
        self._queue = []
        # An Integer to count the number of non-committed objects.
        self._non_commited_objects = 0
        self.skipped = []

    def run(self):
        """

        :return:
        """
        self.session = self.get_session()
        self._import_registry_records()
        self._import_settings()
        self._import_users()
        self._import_data()
        return

    def _import_settings(self):
        """Import the settings from the storage identified by domain
        """
        if not self.import_settings:
            return

        logger.info("*** Importing Settings: {} ***".format(self.domain_name))

        storage = self.get_storage()
        settings_store = storage["settings"]

        for key in settings_store:
            self._set_settings(key, settings_store[key])

    def _set_settings(self, key, data):
        """Set settings by key
        """
        # Get the Schema interface of the settings being imported
        ischemas = CONTROLPANEL_INTERFACE_MAPPING.get(key)
        if not ischemas:
            return
        for ischema_name in data.keys():
            ischema = None
            for candidate_schema in ischemas:
                if candidate_schema.getName() == ischema_name:
                    ischema = candidate_schema
            schema = getAdapter(api.get_portal(), ischema)
            # Once we have the schema set the data
            schema_import_data = data.get(ischema_name)
            for schema_field in schema_import_data:
                if schema_import_data[schema_field]:
                    self._set_attr_from_json(schema, schema_field, schema_import_data[schema_field])

    def _set_attr_from_json(self, schema, attribute, data):
        """Set schema attribute from JSON data. Since JSON converts tuples to lists
           we have to perform a preventive check before setting the value to see if the
           expected value is a tuple or a list. In the case it is a tuple we cast the list
           to tuple
        """
        if hasattr(schema, attribute) and data:
            current_value = getattr(schema, attribute)
            if type(current_value) == tuple:
                setattr(schema, attribute, tuple(data))
            else:
                setattr(schema, attribute, data)

    def _import_registry_records(self):
        """Import the registry records from the storage identified by domain
        """
        if not self.import_registry:
            return

        logger.info("***Importing Registry Records: {}***".format(
            self.domain_name))

        storage = self.get_storage()
        registry_store = storage["registry"]
        current_registry = getUtility(IRegistry)

        # For each of the keywords used to retrieve registry data
        # import the records that were found
        for key in registry_store.keys():
            records = registry_store[key]
            for record in records.keys():
                logger.debug("Updating record {} with value {}".format(
                            record, records.get(record)))
                if record not in current_registry.records:
                    logger.warn("Current Registry has no record named {}"
                                .format(record))
                    continue
                current_registry[record] = records.get(record)

        logger.info("*** Registry Records Imported: {}***".format(
            self.domain_name))

    def _import_users(self):
        """Import the users from the storage identified by domain
        """
        if not self.import_users:
            return

        logger.info("*** Importing Users: {} ***".format(self.domain_name))

        for user in self.yield_items("users"):
            username = user.get("username")
            if ploneapi.user.get(username):
                logger.debug("Skipping existing user {}".format(username))
                continue
            email = user.get("email", "")
            if not email:
                email = "{}@example.com".format(username)
            roles = user.get("roles", ())
            groups = user.get("groups", ())
            logger.debug("Creating user {}".format(username))
            message = _("Created new user {} with password {}".format(
                        username, username))
            # create new user with the same password as the username
            ploneapi.user.create(email=email,
                                 username=username,
                                 password=username,
                                 roles=roles,)
            for group in groups:
                # Try to add the user to the group if group exists.
                try:
                    ploneapi.group.add_user(groupname=group, username=username)
                except KeyError:
                    continue

            logger.debug(message)

        logger.info("*** Users Were Imported: {} ***".format(self.domain_name))

    def _import_data(self):
        """
        For each UID from the fetched data, creates and updates objects
        step by step.
        :return:
        """
        logger.info("*** IMPORT DATA STARTED: {} ***".format(self.domain_name))

        self.sh = SoupHandler(self.domain_name)
        self.uids_to_reindex = []
        storage = self.get_storage()
        ordered_uids = storage["ordered_uids"]
        total_object_count = len(ordered_uids)
        start_time = datetime.now()

        for item_index, r_uid in enumerate(ordered_uids):
            row = self.sh.find_unique(REMOTE_UID, r_uid)
            logger.debug("Handling: {} ".format(row[REMOTE_PATH]))
            self._handle_obj(row)

            # Handling object means there is a chunk containing several objects
            # which have been created and updated. Reindex them now.
            self.uids_to_reindex = list(set(self.uids_to_reindex))
            for uid in self.uids_to_reindex:
                # It is possible that the object has a method (not a Field
                # in its Schema) which is used as an index and it fails.
                # TODO: Make sure reindexing won't fail!
                try:
                    obj = api.get_object_by_uid(uid)
                    obj.reindexObject()
                except Exception, e:
                    rec = self.sh.find_unique(LOCAL_UID, uid)
                    logger.error("Error while reindexing {} - {}"
                                 .format(rec, e))
            self._non_commited_objects += len(self.uids_to_reindex)
            self.uids_to_reindex = []

            # Commit the transaction if necessary
            if self._non_commited_objects > COMMIT_INTERVAL:
                transaction.commit()
                logger.info("Committed: {} / {} ".format(
                            self._non_commited_objects, total_object_count))
                self._non_commited_objects = 0

            # Log.info every 50 objects imported
            utils.log_process(task_name="Data Import", started=start_time,
                              processed=item_index+1, total=total_object_count,
                              frequency=50)

        # Delete the UID list from the storage.
        storage["ordered_uids"] = []

        self._recover_failed_objects()

        # Mark all objects as non-updated for the next import.
        self.sh.reset_updated_flags()

        logger.info("*** END OF DATA IMPORT: {} ***".format(self.domain_name))

    def _handle_obj(self, row, handle_dependencies=True):
        """
        With the given dictionary:
            1. Creates object's slug
            2. Creates and updates dependencies of the object (which actually
               means this _handle_obj function will be called for the dependency
               if the dependency is not updated
            3. Updates the object

        :param row: A row dictionary from the souper
        :type row: dict
        """
        r_uid = row.get(REMOTE_UID)
        try:
            if row.get("updated", "0") == "1":
                return True
            self._queue.append(r_uid)
            obj = self._do_obj_creation(row)
            if obj is None:
                logger.error('Object creation failed: {}'.format(row))
                return
            obj_data = self.get_json(r_uid, complete=True,
                                     workflow=True)
            if handle_dependencies:
                self._create_dependencies(obj, obj_data)
            self._update_object_with_data(obj, obj_data)
            self._set_object_permission(obj)
            self.sh.mark_update(r_uid)
            self._queue.remove(r_uid)
        except Exception, e:
            self._queue.remove(r_uid)
            logger.error('Failed to handle {} : {} '.format(row, str(e)))

        return True

    def _do_obj_creation(self, row):
        """
        With the given dictionary:
            1. Finds object's parents, create them and update their local UID's
            2. Creates plain object and saves its local UID

        :param row: A row dictionary from the souper
        :type row: dict
        """
        remote_path = row.get(REMOTE_PATH)

        remote_parent_path = utils.get_parent_path(remote_path)
        # If parent creation failed previously, do not try to create the object
        if remote_parent_path in self.skipped:
            logger.warning("Parent creation failed previously, skipping: {}"
                           .format(remote_path))
            return None

        local_path = self.translate_path(remote_path)
        existing = self.portal.unrestrictedTraverse(local_path, None)
        if existing:
            rec = self.sh.find_unique(REMOTE_PATH, remote_path)
            if not rec.get(LOCAL_UID, None) or not rec.get(LOCAL_PATH, None):
                local_uid = api.get_uid(existing)
                self.sh.update_by_remote_path(remote_path, local_uid=local_uid,
                                              local_path=local_path)

            return existing

        if not self._parents_created(remote_path):
            logger.warning("Parent creation failed, skipping: {}".format(
                remote_path))
            return None

        parent_path = utils.get_parent_path(local_path)
        container = self.portal.unrestrictedTraverse(str(parent_path), None)
        obj_data = {
            "id": utils.get_id_from_path(local_path),
            "portal_type": row.get(PORTAL_TYPE)}
        obj = self._create_object_slug(container, obj_data)
        if obj is not None:
            local_uid = api.get_uid(obj)
            self.sh.update_by_remote_path(remote_path, local_uid=local_uid)
        return obj

    def _parents_created(self, remote_path):
        """ Check if parents have been already created and create all non-existing
        parents and updates local UIDs for the existing ones.
        :param path: object path in the remote
        :return: True if ALL the parents were created successfully
        """
        p_path = utils.get_parent_path(remote_path)
        if p_path == "/":
            return True

        # Skip if its the portal object.
        if self.is_portal_path(p_path):
            return True

        # Incoming path was remote path, translate it into local one
        local_p_path = self.translate_path(p_path)

        # Check if the parent already exists. If yes, make sure it has
        # 'local_uid' value set in the soup table.
        existing = self.portal.unrestrictedTraverse(local_p_path, None)
        if existing:
            p_row = self.sh.find_unique(REMOTE_PATH, p_path)
            if p_row is None:
                # This should never happen
                return False
            p_local_uid = p_row.get(LOCAL_UID, None)
            if not p_local_uid:
                # Update parent's local path if it is not set already
                if hasattr(existing, "UID") and existing.UID():
                    p_local_uid = existing.UID()
                    self.sh.update_by_remote_path(p_path, local_uid=p_local_uid)
            return True

        # Before creating an object's parent, make sure grand parents are
        # already ready.
        if not self._parents_created(p_path):
            return False

        parent = self.sh.find_unique(REMOTE_PATH, p_path)
        grand_parent = utils.get_parent_path(local_p_path)
        container = self.portal.unrestrictedTraverse(grand_parent, None)
        parent_data = {
            "id": utils.get_id_from_path(local_p_path),
            "remote_path": p_path,
            "portal_type": parent.get(PORTAL_TYPE)}

        parent_obj = self._create_object_slug(container, parent_data)
        if parent_obj is None:
            logger.warning("Couldn't create parent of {}".format(remote_path))
            return False

        # Parent is created, update it in the soup table.
        p_local_uid = api.get_uid(parent_obj)
        self.sh.update_by_remote_path(p_path, local_uid=p_local_uid)
        return True

    def _create_dependencies(self, obj, data):
        """
        Creates and updates objects' dependencies if they are not in the queue.
        Dependencies are found as UIDs in object data.
        :param obj: an object to get dependencies created
        :param data: object data
        """

        dependencies = []

        for fieldname, field in api.get_fields(obj).items():

            if fieldname in self.fields_to_skip:
                continue

            value = data.get(fieldname)

            if isinstance(value, dict) and value.get("uid"):
                dependencies.append(value.get("uid"))
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, dict):
                        for k, v in item.iteritems():
                            if 'uid' in k:
                                dependencies.append(v)

        logger.debug("Dependencies of {} are : {} ".format(repr(obj),
                                                          dependencies))
        dependencies = list(set(dependencies))
        for r_uid in dependencies:
            dep_row = self.sh.find_unique(REMOTE_UID, r_uid)
            if dep_row is None:
                # If dependency doesn't exist in fetched data table,
                # just try to create its object for the first time
                dep_item = self.get_json(r_uid)
                if not dep_item:
                    logger.error("Remote UID not found in fetched data: {}".
                                 format(r_uid))
                    continue
                if not utils.has_valid_portal_type(dep_item):
                    logger.error("Skipping dependency with unknown portal type:"
                                 " {}".format(dep_item))
                    continue
                data_dict = utils.get_soup_format(dep_item)
                rec_id = self.sh.insert(data_dict)
                dep_row = self.sh.get_record_by_id(rec_id, as_dict=True)
                if self._parents_fetched(dep_item):
                    self._handle_obj(dep_row, handle_dependencies=False)
                continue

            # If Dependency is being processed, skip it.
            if r_uid in self._queue:
                continue

            # No need to handle already updated objects
            if dep_row.get("updated") == "0":
                self._handle_obj(dep_row)
            # Reindex dependency just in case it has a field that uses
            # BackReference of this object.
            else:
                self.uids_to_reindex.append(dep_row.get(LOCAL_UID))

        return True

    def _update_object_with_data(self, obj, data):
        """Update an existing object with data
        """
        # Proxy Fields must be set after its dependency object is already set.
        # Thus, we will store all the ProxyFields and set them in the end
        proxy_fields = []

        for fieldname, field in api.get_fields(obj).items():

            if fieldname in self.fields_to_skip:
                continue

            fm = IFieldManager(field)
            value = data.get(fieldname)
            kwargs = {}

            # Computed Fields don't have set methods.
            if isinstance(fm, ComputedFieldManager):
                continue

            # handle JSON data reference fields
            if isinstance(value, dict) and value.get("uid"):
                # dereference the referenced object
                local_uid = self.sh.get_local_uid(value.get("uid"))
                if local_uid:
                    value = api.get_object_by_uid(local_uid)
                else:
                    value = None

            elif isinstance(value, (list, tuple)):
                for item in value:
                    # If it is list of json data dict of objects, add local
                    # uid to that dictionary. This local_uid can be used in
                    # Field Managers.
                    if isinstance(item, dict):
                        for k, v in item.iteritems():
                            if 'uid' in k:
                                local_uid = self.sh.get_local_uid(v)
                                item[k] = local_uid

            # handle file fields
            if field.type in ("file", "image", "blob"):
                if data.get(fieldname) is not None:
                    fileinfo = data.get(fieldname)
                    url = fileinfo.get("download")
                    filename = fileinfo.get("filename")
                    kwargs["filename"] = filename
                    response = self.session.get(url)
                    value = response.content

            # Leave the Proxy Fields for later
            if isinstance(fm, ProxyFieldManager):
                proxy_fields.append({'field_name': fieldname,
                                     'fm': fm, 'value': value})
                continue
            try:
                fm.set(obj, value, **kwargs)
            except:
                logger.debug(
                    "Could not set field '{}' with value '{}'".format(
                        fieldname, value))

        # All reference fields are set. We can set the proxy fields now.
        for pf in proxy_fields:
            field_name = pf.get("field_name")
            fm = pf.get("fm")
            value = pf.get("value")
            try:
                fm.set(obj, value)
            except:
                logger.debug(
                    "Could not set field '{}' with value '{}'".format(
                        field_name,
                        value))

        # Set the workflow states
        wf_info = data.get("workflow_info", [])
        for wf_dict in wf_info:
            wf_id = wf_dict.get("workflow")
            review_history = wf_dict.get("review_history")
            self._import_review_history(obj, wf_id, review_history)

        # finally reindex the object
        self.uids_to_reindex.append(api.get_uid(obj))

    def _create_object_slug(self, container, data, *args, **kwargs):
        """Create an content object slug for the given data
        """
        id = data.get("id")
        remote_path = data.get("remote_path")
        portal_type = data.get("portal_type")
        types_tool = api.get_tool("portal_types")
        fti = types_tool.getTypeInfo(portal_type)
        if not fti:
            self.skipped.append(remote_path)
            logger.error("Type Info not found for {}".format(portal_type))
            return None
        logger.debug("Creating {} with ID {} in parent path {}".format(
            portal_type, id, api.get_path(container)))

        if fti.product:
            obj = _createObjectByType(portal_type, container, id)
        else:
            # new style factory
            factory = getUtility(IFactory, fti.factory)
            obj = factory(id, *args, **kwargs)
            if hasattr(obj, '_setPortalTypeName'):
                obj._setPortalTypeName(fti.getId())
            # notifies ObjectWillBeAddedEvent, ObjectAddedEvent and
            # ContainerModifiedEvent
            container._setObject(id, obj)
            # we get the object here with the current object id, as it
            # might be renamed
            # already by an event handler
            obj = container._getOb(obj.getId())

        # Be sure that Creation Flag is Cleared.
        if obj.checkCreationFlag():
            obj.unmarkCreationFlag()

        return obj

    def _import_review_history(self, content, wf_id, review_history, **kw):
        """Change the workflow state of an object
        @param content: Content obj which state will be changed
        @param review_history: Review history of the object
        @param wf_id: workflow name
        @param kw: change the values of same name of the state mapping
        @return: None
        """

        portal_workflow = api.get_tool('portal_workflow')

        # Might raise IndexError if no workflow is associated to this type
        for wf_def in portal_workflow.getWorkflowsFor(content):
            if wf_id == wf_def.getId():
                break
        else:
            logger.warn("%s: Cannot find workflow id %s" % (content, wf_id))

        for rh in sorted(review_history, key=lambda k: k['time']):
            if not utils.is_review_history_imported(content, rh, wf_def):
                portal_workflow.setStatusOf(wf_id, content,
                                            utils.to_review_history_format(rh))

        wf_def.updateRoleMappingsFor(content)
        return

    def _recover_failed_objects(self):
        """ Checks for non-updated objects (by filtering null Title) and
        re-updates them.
        :return:
        """
        uc = api.get_tool('uid_catalog', self.portal)
        # Reference objects must be skipped
        query = Eq('Title', '') & ~ Eq('portal_type', 'Reference') & ~ \
            Eq('portal_type', 'ARReport')
        brains = uc.evalAdvancedQuery(query)
        total = len(brains)
        logger.info('*** Recovering {} objects ***'.format(total))
        for idx, brain in enumerate(brains):
            # Check if object has been created during migration
            uid = brain.UID
            existing = self.sh.find_unique(LOCAL_UID, uid)
            if existing is None:
                continue
            logger.info('Recovering {0}/{1} : {2} '.format(
                                        idx+1, total, existing[REMOTE_PATH]))
            # Mark that update failed previously
            existing['updated'] = '0'
            self._handle_obj(existing, handle_dependencies=False)
            obj = brain.getObject()
            obj.reindexObject()
        return

    def _set_object_permission(self, obj):
        """
        :param obj:
        :return:
        """
        portal_type = api.get_portal_type(obj)

        # Don't do anything, if it is just a dependency
        if portal_type in self.unwanted_content_types:
            return

        if portal_type in self.read_only_types:
            obj.manage_permission('Modify portal content', roles=[])

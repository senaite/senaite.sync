# -*- coding: utf-8 -*-
#
# Copyright 2017-2017 SENAITE LIMS.

import urllib
import urlparse
import requests
import transaction

from BTrees.OOBTree import OOBTree

from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFPlone.utils import _createObjectByType
from senaite.sync.importstep import ImportStep
from senaite.sync.syncerror import SyncError

from zope.interface import implements
from zope.annotation.interfaces import IAnnotations
from zope.component import getUtility
from zope.component.interfaces import IFactory

from plone import protect
from plone import api as ploneapi
from plone.registry.interfaces import IRegistry

from senaite import api
from senaite.jsonapi.interfaces import IFieldManager
from senaite.sync import logger
from senaite.sync.browser.interfaces import ISync
from senaite.sync import _
from senaite.sync.souphandler import SoupHandler
import senaite.sync.utils as u
from senaite.sync.fetchstep import FetchStep

from senaite.jsonapi.fieldmanagers import ProxyFieldManager

API_BASE_URL = "API/senaite/v1"
SYNC_STORAGE = "senaite.sync"

SKIP_PORTAL_TYPES = ["SKIP"]
COMMIT_INTERVAL = 1000


class Sync(BrowserView):
    """Sync Controller View
    """
    implements(ISync)

    template = ViewPageTemplateFile("templates/sync.pt")
    fields_to_skip = ['excludeFromNav', 'constrainTypesMode', 'allowDiscussion']

    def __init__(self, context, request):
        super(BrowserView, self).__init__(context, request)
        self.context = context
        self.request = request

        # VARIABLES TO BE USED IN FETCH AND IMPORT STEPS
        self.domain_name = None
        self.url = None
        self.username = None
        self.password = None
        self.session = None
        # Soup Handler to interact with the domain's soup table
        self.sh = None
        # A list to keep UID's of an object chunk
        self.uids_to_reindex = []
        # An 'infinite recursion preventative' list of objects which are
        # being updated.
        self._queue = []
        # An Integer to count the number of non-committed objects.
        self._non_commited_objects = 0

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

        # remember the form field values
        url = form.get("url", "")
        if not url.startswith("http"):
            url = "http://{}".format(url)
        self.url = url
        self.domain_name = form.get("domain_name", None)
        self.username = form.get("ac_name", None)
        self.password = form.get("ac_password", None)

        # Handle "Import" action
        if form.get("import", False):
            domain_name = form.get("domain_name", None)
            # initialize the session
            storage = self.get_storage(self.domain_name)
            url = storage["credentials"]["url"]
            username = storage["credentials"]["username"]
            password = storage["credentials"]["password"]
            data = {
                "url": url,
                "domain_name": domain_name,
                "ac_name": username,
                "ac_password": password,
            }
            step = ImportStep(data)
            step.run()
            return self.template()

        # Handle "Clear this Storage" action
        if form.get("clear_storage", False):
            domain = form.get("domain_name", None)
            del self.storage[domain]
            message = _("Cleared Storage {}".format(domain))
            self.add_status_message(message, "info")
            return self.template()

        # Handle "Clear all Storages" action
        if form.get("clear", False):
            self.flush_storage()
            message = _("Cleared Data Storage")
            self.add_status_message(message, "info")
            return self.template()

        # Handle "Fetch" action
        if form.get("fetch", False):
            # check if all mandatory fields have values
            if not all([self.domain_name, self.url, self.username,
                        self.password]):
                message = _("Please fill in all required fields")
                self.add_status_message(message, "error")
                return self.template()

            data = {
                "url": form.get("url", None),
                "domain_name": form.get("domain_name", None),
                "ac_name": form.get("ac_name", None),
                "ac_password": form.get("ac_password", None),
            }

            fs = FetchStep(data)
            verified, message = fs.verify()
            if verified:
                fs.run()
                self.add_status_message(message, "info")
            else:
                self.add_status_message(message, "error")

        # always render the template
        return self.template()

    def import_registry_records(self, domain):
        """Import the registry records from the storage identified by domain
        """
        logger.info("*** IMPORT REGISTRY RECORDS {} ***".format(domain))

        storage = self.get_storage(domain=domain)
        registry_store = storage["registry"]
        current_registry = getUtility(IRegistry)
        # For each of the keywords used to retrieve registry data
        # import the records that were found
        for key in registry_store.keys():
            records = registry_store[key]
            for record in records.keys():
                logger.info("Updating record {} with value {}".format(record, records.get(record)))
                if record not in current_registry.records:
                    logger.warn("Current Registry has no record named {}".format(record))
                    continue
                current_registry[record] = records.get(record)

    def import_users(self, domain):
        """Import the users from the storage identified by domain
        """
        logger.info("*** IMPORT USERS {} ***".format(domain))

        for user in self.yield_items("users"):
            username = user.get("username")
            if ploneapi.user.get(username):
                logger.info("Skipping existing user {}".format(username))
                continue
            email = user.get("email", "")
            roles = user.get("roles", ())
            logger.info("Creating user {}".format(username))
            message = _("Created new user {} with password {}".format(
                        username, username))
            # create new user with the same password as the username
            ploneapi.user.create(email=email,
                                 username=username,
                                 password=username,
                                 roles=roles,)
            self.add_status_message(message, "info")
            logger.info(message)

    def import_data(self, domain_name):
        """
        For each UID from the fetched data, creates and updates objects
        step by step.
        :param domain_name: name of the domain to import data for
        :return:
        """
        logger.info("*** IMPORT DATA STARTED FOR {} ***".format(domain_name))

        self.sh = SoupHandler(domain_name)
        self.uids_to_reindex = []
        storage = self.get_storage(domain=domain_name)
        ordered_uids = storage["ordered_uids"]

        for r_uid in ordered_uids:
            row = self.sh.find_unique("remote_uid", r_uid)
            logger.info("Creating {}".format(row["path"]))
            self._handle_obj(row)

            # Handling object means there is a chunk containing several objects
            # which have been created and updated. Reindex them now.
            self.uids_to_reindex = list(set(self.uids_to_reindex))
            for uid in self.uids_to_reindex:
                api.get_object_by_uid(uid).reindexObject()
            self._non_commited_objects += len(self.uids_to_reindex)
            self.uids_to_reindex = []

            # Commit the transaction if necessary
            if self._non_commited_objects > COMMIT_INTERVAL:
                transaction.commit()
                logger.info("OBJECTS IMPORTED: {} / {} ".format(
                            self._non_commited_objects, len(ordered_uids)))
                self._non_commited_objects = 0

        # Delete the UID list from the storage.
        storage["ordered_uids"] = []
        # Mark all objects as non-updated for the next import.
        self.sh.reset_updated_flags()

        logger.info("*** END OF DATA IMPORT {} ***".format(domain_name))

    def update_object_with_data(self, obj, data):
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

            # handle JSON data reference fields
            if isinstance(value, dict) and value.get("uid"):
                # dereference the referenced object
                local_uid = self.sh.get_local_uid(value.get("uid"))
                value = api.get_object_by_uid(local_uid)

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
                    data["filename"] = filename
                    response = requests.get(url)
                    value = response.content

            # Leave the Proxy Fields for later
            if isinstance(fm, ProxyFieldManager):
                proxy_fields.append({'field_name': fieldname,
                                     'fm': fm, 'value': value})
                continue

            logger.info("Setting value={} on field={} of object={}".format(
                repr(value), fieldname, api.get_id(obj)))
            try:
                fm.set(obj, value)
            except:
                logger.warn(
                    "Could not set field '{}' with value '{}'".format(
                        fieldname, value))

        # All reference fields are set. We can set the proxy fields now.
        for pf in proxy_fields:
            field_name = pf.get("field_name")
            fm = pf.get("fm")
            value = pf.get("value")
            logger.info("Setting value={} on field={} of object={}".format(
                repr(value), field_name, api.get_id(obj)))
            try:
                fm.set(obj, value)
            except:
                logger.warn(
                    "Could not set field '{}' with value '{}'".format(
                        field_name,
                        value))

        # Set the workflow states
        wf_info = data.get("workflow_info", [])
        for wf_dict in wf_info:
            wf_id = wf_dict.get("workflow")
            review_history = wf_dict.get("review_history")
            self.import_review_history(obj, wf_id, review_history)

        # finally reindex the object
        self.uids_to_reindex.append(api.get_uid(obj))

    def create_object_slug(self, container, data, *args, **kwargs):
        """Create an content object slug for the given data
        """
        id = data.get("id")
        portal_type = data.get("portal_type")
        types_tool = api.get_tool("portal_types")
        fti = types_tool.getTypeInfo(portal_type)
        if not fti:
            logger.error("Type Info not found for {}".format(portal_type))
            return None
        logger.info("Creating {} with ID {} in parent path {}".format(
            portal_type, id, api.get_path(container)))

        if fti.product:
            obj = _createObjectByType(portal_type, container, id)
        else:
            # newstyle factory
            factory = getUtility(IFactory, fti.factory)
            obj = factory(id, *args, **kwargs)
            if hasattr(obj, '_setPortalTypeName'):
                obj._setPortalTypeName(fti.getId())
            # notifies ObjectWillBeAddedEvent, ObjectAddedEvent and ContainerModifiedEvent
            container._setObject(id, obj)
            # we get the object here with the current object id, as it might be renamed
            # already by an event handler
            obj = container._getOb(obj.getId())
        return obj

    def import_review_history(self, content, wf_id, review_history, **kw):
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
            logger.error("%s: Cannot find workflow id %s" % (content, wf_id))

        for rh in sorted(review_history, key=lambda k: k['time']):
            if not u.review_history_imported(content, rh, wf_def):
                portal_workflow.setStatusOf(wf_id, content,
                                            u.to_review_history_format(rh))

        wf_def.updateRoleMappingsFor(content)
        return

    def translate_path(self, path):
        """Translate the physical path to a local path
        """
        portal_id = self.portal.getId()
        remote_portal_id = path.split("/")[1]
        return path.replace(remote_portal_id, portal_id)

    def _handle_obj(self, row):
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
        r_uid = row.get("remote_uid")
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
            self._create_dependencies(obj, obj_data)
            self.update_object_with_data(obj, obj_data)
            self.sh.mark_update(r_uid)
            self._queue.remove(r_uid)
        except Exception, e:
            self._queue.remove(r_uid)
            logger.error('Failed to handle: {} \n {} '.format(row, str(e)))

        return True

    def _do_obj_creation(self, row):
        """
        With the given dictionary:
            1. Finds object's parents, create them and update their local UID's
            2. Creates plain object and saves its local UID

        :param row: A row dictionary from the souper
        :type row: dict
        """
        path = row.get("path")
        existing = self.portal.unrestrictedTraverse(
                            str(self.translate_path(path)), None)
        if existing:
            local_uid = self.sh.find_unique("path", path).get("local_uid",
                                                              None)
            if not local_uid:
                local_uid = api.get_uid(existing)
                self.sh.update_by_path(path, local_uid=local_uid)
            return existing

        self._create_parents(path)
        parent = self.translate_path(u.get_parent_path(path))
        container = self.portal.unrestrictedTraverse(str(parent), None)
        obj_data = {
            "id": u.get_id_from_path(path),
            "portal_type": row.get("portal_type")}
        obj = self.create_object_slug(container, obj_data)
        if obj is not None:
            local_uid = api.get_uid(obj)
            self.sh.update_by_path(path, local_uid=local_uid)
        return obj

    def _create_parents(self, path):
        """
        Creates all non-existing parents and updates local UIDs for the existing
        ones.
        :param path: object path in the remote
        :return:
        """
        p_path = u.get_parent_path(path)
        if p_path == "/":
            return True

        # Incoming path was remote path, translate it into local one
        local_path = self.translate_path(p_path)

        # Check if the parent already exists. If yes, make sure it has
        # 'local_uid' value set in the soup table.
        try:
            existing = self.portal.unrestrictedTraverse(str(local_path), None)
            if existing:
                # Skip if its the portal object.
                if len(p_path.split("/")) < 3:
                    return
                p_row = self.sh.find_unique("path", p_path)
                if p_row is None:
                    return
                p_local_uid = self.sh.find_unique("path", p_path).get("local_uid",
                                                                      None)
                if not p_local_uid:
                    if hasattr(existing, "UID") and existing.UID():
                        p_local_uid = existing.UID()
                        self.sh.update_by_path(p_path, local_uid=p_local_uid)
                return
        except TypeError, e:
            logger.warn("ERROR WHILE ACCESSING AN EXISTING OBJECT: {} "
                        .format(str(e)))
            return
        # Before creating an object's parent, make sure grand parents are
        # already ready.
        self._create_parents(p_path)
        parent = self.sh.find_unique("path", p_path)
        grand_parent = self.translate_path(u.get_parent_path(p_path))
        container = self.portal.unrestrictedTraverse(str(grand_parent), None)
        parent_data = {
            "id": u.get_id_from_path(p_path),
            "portal_type": parent.get("portal_type")}
        parent_obj = self.create_object_slug(container, parent_data)

        # Parent is created, update it in the soup table.
        p_local_uid = api.get_uid(parent_obj)
        self.sh.update_by_path(p_path, local_uid=p_local_uid)
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

        logger.info("Dependencies of {} are : {} ".format(repr(obj),
                                                          dependencies))
        for r_uid in dependencies:
            dep_row = self.sh.find_unique("remote_uid", r_uid)
            if dep_row is None:
                logger.error("Reference UID {} not found for {}: ".format(
                                        r_uid, repr(obj)))
                continue
            # If Dependency is not being processed, handle it.
            if r_uid not in self._queue:
                # No need to handle already updated objects
                if dep_row.get("updated") == "0":
                    logger.info("Resolving Dependency of {} with {} ".format(
                                repr(obj), dep_row))
                    self._handle_obj(dep_row)
                    logger.info("Resolved Dependency of {} with {} ".format(
                                repr(obj), dep_row))
                # Reindex dependency just in case it has a field uses
                # BackReference of this object.
                else:
                    logger.info("Reindexing already updated object... {}"
                                .format(dep_row.get("local_uid")))
                    self.uids_to_reindex.append(dep_row.get("local_uid"))

        return True

    def get_data_from_uids(self, uids=None):
        """Get the data of a list of uids

        :param uids: list of uids whose data is wanted
        :return: dictionary mapping uids to its json data
        """
        retrieved_data = {}
        if not uids:
            return retrieved_data
        for uid in uids:
            uid_data = self.get_json(uid, complete=True, children=False, workflow=True)
            retrieved_data[uid] = uid_data
        return retrieved_data

    def get_first_item(self, url_or_endpoint, **kw):
        """Fetch the first item of the 'items' list from a std. JSON API reponse
        """
        items = self.get_items(url_or_endpoint, **kw)
        if not items:
            return None
        return items[0]

    def get_items(self, url_or_endpoint, **kw):
        """Return the 'items' list from a std. JSON API response
        """
        data = self.get_json(url_or_endpoint, **kw)
        if not isinstance(data, dict):
            return []
        return data.get("items", [])

    def get_json(self, url_or_endpoint, **kw):
        """Fetch the given url or endpoint and return a parsed JSON object
        """
        api_url = self.get_api_url(url_or_endpoint, **kw)
        logger.info("get_json::url={}".format(api_url))
        try:
            response = self.session.get(api_url)
        except Exception as e:
            message = "Could not connect to {} Please check.".format(
                api_url)
            logger.error(e)
            self.add_status_message(message, "error")
            return {}
        status = response.status_code
        if status != 200:
            message = "GET for {} ({}) returned Status Code {}. Please check.".format(
                url_or_endpoint, api_url, status)
            self.add_status_message(message, "warning")
            return {}
        return response.json()

    def yield_items(self, url_or_endpoint, **kw):
        """Yield items of all pages
        """
        data = self.get_json(url_or_endpoint, **kw)
        for item in data.get("items", []):
            yield item

        next_url = data.get("next")
        if next_url:
            for item in self.yield_items(next_url, **kw):
                yield item

    def get_api_url(self, url_or_endpoint, **kw):
        """Create an API URL from an endpoint or absolute url
        """
        # Nothing to do if we have no base URL
        if self.url is None:
            raise SyncError("No base URL found")
        # Convert to an absolute URL
        if not url_or_endpoint.startswith(self.url):
            segments = API_BASE_URL.split("/") + url_or_endpoint.split("/")
            path = "/".join(segments)
            url_or_endpoint = "/".join([self.url, path])
        # Handle request parameters
        if kw:
            scheme, netloc, path, query, fragment = urlparse.urlsplit(url_or_endpoint)
            if query:
                query = dict(urlparse.parse_qsl(query))
                kw.update(query)
            q = urllib.urlencode(kw)
            return "{}://{}{}?{}".format(scheme, netloc, path, q)
        return url_or_endpoint

    def get_session(self, username, password):
        """Return a session object for authenticated requests
        """
        session = requests.Session()
        session.auth = (username, password)
        return session

    def fail(self, message, status):
        """Raise a SyncError
        """
        raise SyncError(message, status)

    def add_status_message(self, message, level="info"):
        """Set a portal status message
        """
        return self.context.plone_utils.addPortalMessage(message, level)

    def get_annotation(self):
        """Annotation storage on the portal object
        """
        return IAnnotations(self.portal)

    def get_storage(self, domain=None):
        """Return a ready to use storage for the given domain (key)
        """
        if domain is None:
            domain = len(self.storage)

        if not self.storage.get(domain):
            self.storage[domain] = OOBTree()
            self.storage[domain]["credentials"] = OOBTree()
            self.storage[domain]["registry"] = OOBTree()
            self.storage[domain]["ordered_uids"] = []
        return self.storage[domain]

    @property
    def storage(self):
        """Raw storage property

        Please use get_storage to get a sync storage for a given domain
        """
        annotation = self.get_annotation()
        if annotation.get(SYNC_STORAGE) is None:
            annotation[SYNC_STORAGE] = OOBTree()
        return annotation[SYNC_STORAGE]

    def flush_storage(self):
        """Drop the whole storage
        """
        annotation = self.get_annotation()
        if annotation.get(SYNC_STORAGE) is not None:
            del annotation[SYNC_STORAGE]

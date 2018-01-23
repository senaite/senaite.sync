# -*- coding: utf-8 -*-
#
# Copyright 2017-2017 SENAITE LIMS.

import urllib
import urlparse
import requests
import transaction
from DateTime import DateTime
from datetime import datetime

from BTrees.OOBTree import OOSet
from BTrees.OOBTree import OOBTree

from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFPlone.utils import _createObjectByType

from zope.interface import implements
from zope.annotation.interfaces import IAnnotations
from zope.globalrequest import getRequest
from zope.component import getUtility
from zope.component import getAdapter
from zope.component.interfaces import IFactory

from plone import protect
from plone import api as ploneapi
from plone.registry.interfaces import IRegistry
import plone.app.controlpanel as cp

from senaite import api
from senaite.jsonapi.interfaces import IFieldManager
from senaite.sync import logger
from senaite.sync.browser.interfaces import ISync
from senaite.sync import _

from senaite.jsonapi.fieldmanagers import ProxyFieldManager

API_BASE_URL = "API/senaite/v1"
SYNC_STORAGE = "senaite.sync"


class SyncError(Exception):
    """ Exception Class for Sync Errors
    """

    def __init__(self, status, message):
        self.message = message
        self.status = status
        self.setStatus(status)

    def setStatus(self, status):
        request = getRequest()
        request.response.setStatus(status)

    def __str__(self):
        return self.message


class Sync(BrowserView):
    """Sync Controller View
    """
    implements(ISync)

    template = ViewPageTemplateFile("templates/sync.pt")

    def __init__(self, context, request):
        super(BrowserView, self).__init__(context, request)
        self.context = context
        self.request = request

        self.url = None
        self.username = None
        self.password = None
        self.session = None

        self.uids_to_reindex = []

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
        self.username = form.get("ac_name", None)
        self.password = form.get("ac_password", None)

        # Handle "Import" action
        if form.get("import", False):
            domain = form.get("domain", None)
            self.import_settings(domain)
            self.import_registry_records(domain)
            self.import_users(domain)
            self.import_data(domain)
            logger.info("*** END OF DATA IMPORT {} ***".format(domain))
            return self.template()

        # Handle "Clear this Storage" action
        if form.get("clear_storage", False):
            domain = form.get("domain", None)
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
            if not all([self.url, self.username, self.password]):
                message = _("Please fill in all required fields")
                self.add_status_message(message, "error")
                return self.template()

            # initialize the session
            self.session = self.get_session(self.username, self.password)

            # remember the credentials in the storage
            storage = self.get_storage(self.url)
            storage["credentials"]["username"] = self.username
            storage["credentials"]["password"] = self.password

            # try to get the version of the remote JSON API
            version = self.get_version()
            if not version or not version.get('version'):
                message = _("Please install senaite.jsonapi on the source system")
                self.add_status_message(message, "error")
                return self.template()

            # try to get the current logged in user
            user = self.get_authenticated_user()
            if not user or user.get("authenticated") is False:
                message = _("Wrong username/password")
                self.add_status_message(message, "error")
                return self.template()

            domain = self.url
            self.fetch_settings(domain)
            # Fetch all users from the source
            self.fetch_users(domain)
            # Start the fetch process beginning from the portal object
            self.fetch_data(domain, uid="0")
            # Fetch registry records that contain the word bika or senaite
            self.fetch_registry_records(domain, keys=["bika", "senaite"])
            logger.info("*** FETCHING DATA FINISHED {} ***".format(domain))

        # always render the template
        return self.template()

    def import_settings(self, domain):
        """Import the settings from the storage identified by domain
        """
        logger.info("*** IMPORT SETTINGS {} ***".format(domain))

        storage = self.get_storage(domain=domain)
        settings_store = storage["settings"]
        for key in settings_store:
            self.set_settings(key, settings_store[key])

    def set_settings(self, key, data):
        """Set settings by key
        """
        key_to_ischema = {
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
        # Get the Schema interface of the settings being imported
        ischemas = key_to_ischema[key]
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
                    self.set_attr_from_json(schema, schema_field, schema_import_data[schema_field])

    def set_attr_from_json(self, schema, attribute, data):
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
                current_registry[record] = records.get(record)

    def import_users(self, domain):
        """Import the users from the storage identified by domain
        """
        logger.info("*** IMPORT USERS {} ***".format(domain))

        storage = self.get_storage(domain=domain)
        userstore = storage["users"]

        for username, userdata in userstore.items():

            if ploneapi.user.get(username):
                logger.info("Skipping existing user {}".format(username))
                continue
            email = userdata.get("email", "")
            roles = userdata.get("roles", ())
            # TODO handle groups
            # groups = userdata.get("groups",  groups=groups)())
            logger.info("Creating user {}".format(username))
            message = _("Created new user {} with password {}".format(username, username))
            # create new user with the same password as the username
            ploneapi.user.create(email=email,
                                 username=username,
                                 password=username,
                                 roles=roles,)
            self.add_status_message(message, "info")
            logger.info(message)

    def import_data(self, domain):
        """Import the data from the storage identified by domain
        """
        logger.info("*** IMPORT DATA {} ***".format(domain))

        storage = self.get_storage(domain=domain)
        datastore = storage["data"]
        indexstore = storage["index"]
        uidmap = storage["uidmap"]
        credentials = storage["credentials"]

        # At some points api cannot retrieve objects by UID in the end of
        # creation process. Thus we keep them in an dictionary to access easily.
        objmap = {}
        # We will create objects from top to bottom, but will update from bottom
        # to up.
        ordered_uids = []

        # initialize a new session with the stored credentials for later requests
        username = credentials.get("username")
        password = credentials.get("password")
        self.session = self.get_session(username, password)
        logger.info("Initialized a new session for user {}".format(username))

        # Get UIDs grouped by their parent path
        ppaths = indexstore.get("by_parent_path")
        if ppaths is None:
            message = _("No parent path info found in the import data. "
                        "Please install senaite.jsonapi>=1.1.1 on the source instance "
                        "and clear&refetch this storage")
            self.add_status_message(message, "warning")
            return

        # Import by paths from top to bottom
        for ppath in sorted(ppaths):
            # nothing to do
            if not ppath:
                continue

            logger.info("Importing items for parent path {}".format(ppath))
            uids = ppaths[ppath]

            for uid in uids:
                ordered_uids.append(uid)
                # get the data for this uid
                data = datastore[uid]
                # check if the object exists in this instance
                remote_path = data.get("path")
                local_path = self.translate_path(remote_path)
                existing = self.portal.unrestrictedTraverse(str(local_path), None)

                if existing:
                    # remember the UID -> object UID mapping for the update step
                    uidmap[uid] = api.get_uid(existing)
                    objmap[uid] = existing
                else:
                    # get the container object by path
                    container_path = self.translate_path(ppath)
                    container = self.portal.unrestrictedTraverse(str(container_path), None)
                    # create an object slug in this container
                    obj = self.create_object_slug(container, data)
                    # remember the UID -> object UID mapping for the update step
                    uidmap[uid] = api.get_uid(obj)
                    objmap[uid] = obj

        # When creation process is done, commit the transaction to avoid
        # ReferenceField relation problems.
        transaction.commit()

        # UIDs were added from up to bottom. Reverse the list to update objects
        # from bottom to up.
        ordered_uids.reverse()

        # Update all objects with the given data
        for uid in ordered_uids:
            obj = objmap.get(uid, None)
            if obj is None:
                logger.warn("Object not found: {} ".format(uid))
                continue
            logger.info("Update object {} with import data".format(api.get_path(obj)))
            self.update_object_with_data(obj, datastore[uid], domain)

        self.reindex_updated_objects()

    def update_object_with_data(self, obj, data, domain):
        """Update an existing object with data
        """

        # get the storage and UID map
        storage = self.get_storage(domain=domain)
        uidmap = storage["uidmap"]
        # Proxy Fields must be set after its dependency object is already set.
        # Thus, we will store all the ProxyFields and set them in the end
        proxy_fields = []

        for fieldname, field in api.get_fields(obj).items():

            fm = IFieldManager(field)
            value = data.get(fieldname)

            # handle JSON data reference fields
            if isinstance(value, dict) and value.get("uid"):
                # dereference the referenced object
                value = self.dereference_object(value.get("uid"), uidmap)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    # If it is list of json data dict of objects, add local
                    # uid to that dictionary. This local_uid can be used in
                    # Field Managers.
                    if isinstance(item, dict):
                        for k, v in item.iteritems():
                            if 'uid' in k:
                                local_uid = uidmap.get(v)
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
                logger.error(
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
                logger.error(
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
        self.uids_to_reindex.append([api.get_uid(obj), repr(obj)])

    def dereference_object(self, uid, uidmap):
        """Dereference an object by uid

        uidmap is a mapping of remote uid -> local object uid
        """
        ref_uid = uidmap.get(uid, None)
        ref_obj = api.get_object_by_uid(ref_uid, None)
        return ref_obj

    def create_object_slug(self, container, data, *args, **kwargs):
        """Create an content object slug for the given data
        """
        id = data.get("id")
        portal_type = data.get("portal_type")
        types_tool = api.get_tool("portal_types")
        fti = types_tool.getTypeInfo(portal_type)

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
            if not self.review_history_imported(content, rh, wf_def):
                portal_workflow.setStatusOf(wf_id, content,
                                            self.to_review_history_format(rh))

        wf_def.updateRoleMappingsFor(content)
        return

    def to_review_history_format(self, review_history):
        """
        Format review history dictionary
        :param review_history: Review State Dictionary
        :return: formatted dictionary
        """

        raw = review_history.get("time")
        if isinstance(raw, basestring):
            parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
            review_history['time'] = DateTime(parsed)
        return review_history

    def review_history_imported(self, obj, review_history, wf_tool=None):
        """
        Check if review History info is already imported for given workflow.
        :param obj: the object to be checked
        :param review_history: Review State Dictionary
        :param wf_tool: Objects Workflow tool. Will be set to 'portal_worklow'
                if is None.
        :return: formatted dictionary
        """
        if wf_tool is None:
            wf_tool = api.get_tool('portal_workflow')

        state = review_history.get('review_state')
        current_rh = wf_tool.getInfoFor(obj, 'review_history', '')
        for rh in current_rh:
            if rh.get('review_state') == state:
                return True

        return False

    def translate_path(self, path):
        """Translate the physical path to a local path
        """
        portal_id = self.portal.getId()
        remote_portal_id = path.split("/")[1]
        return path.replace(remote_portal_id, portal_id)

    def fetch_settings(self, domain, keys=None):
        """Fetch source instance settings by keyword
        """
        logger.info(" FETCH SETTINGS {} ***".format(domain))
        storage = self.get_storage(domain=domain)
        settings_store = storage["settings"]

        if keys is None:
            retrieved_settings = self.get_settings_by_key()
        else:
            retrieved_settings = []
            for key in keys:
                retrieved_settings += self.get_settings_by_key(key)

        for setting_dict in retrieved_settings:
            for key in setting_dict.keys():
                if not setting_dict[key]:
                    continue
                settings_store[key] = setting_dict[key]

    def fetch_registry_records(self, domain, keys=None):
        """Fetch configuration registry records of interest (those associated
        to the keywords passed) from source instance
        """
        logger.info("*** FETCH REGISTRY RECORDS {} ***".format(domain))
        storage = self.get_storage(domain=domain)
        registry_store = storage["registry"]
        retrieved_records = {}

        if keys is None:
            retrieved_records["all"] = self.get_registry_records_by_key()
        else:
            for key in keys:
                retrieved_records[key] = self.get_registry_records_by_key(key)

        for key in retrieved_records.keys():
            if not retrieved_records[key]:
                continue
            registry_store[key] = OOBTree()
            for record in retrieved_records[key][0].keys():
                registry_store[key][record] = retrieved_records[key][0][record]

    def fetch_users(self, domain):
        """Fetch all users from the source URL
        """
        logger.info("*** FETCH USERS {} ***".format(domain))
        storage = self.get_storage(domain=domain)
        userstore = storage["users"]

        for user in self.yield_items("users"):
            username = user.get("username")
            userstore[username] = user

    def fetch_data(self, domain, uid="0"):
        """Fetch the data from the source URL
        """
        # Fetch the object by uid
        parent = self.get_json(uid, complete=True, children=True, workflow=True)
        children = parent.pop("children", [])
        self.store(domain, uid, parent)

        # Fetch the children of this object
        for child in children:
            child_uid = child.get("uid")
            if not child_uid:
                message = "Item '{}' has no UID key".format(child)
                self.add_status_message(message, "warn")
                continue

            child_item = self.get_json(child_uid, complete=True, children=True,
                                       workflow=True)
            child_children = child_item.pop("children", [])
            self.store(self.url, child_uid, child_item)

            for child_child in child_children:
                self.fetch_data(domain=domain, uid=child_child.get("uid"))

    def store(self, domain, key, value, overwrite=False):
        """Store a dictionary in the domain's storage
        """
        # Get the storage for the current URL
        storage = self.get_storage(domain=domain)
        datastore = storage["data"]
        indexstore = storage["index"]

        # already fetched
        if key in datastore and not overwrite:
            logger.info("Skipping existing key {}".format(key))
            return

        # Create some indexes
        for index in ["portal_type", "parent_id", "parent_path"]:
            index_key = "by_{}".format(index)
            if not indexstore.get(index_key):
                indexstore[index_key] = OOBTree()
            indexvalue = value.get(index)
            # Check if the index value, e.g. the portal_type="Sample", is
            # already known as a key in the index.
            if not indexstore[index_key].get(indexvalue):
                indexstore[index_key][indexvalue] = OOSet()
            indexstore[index_key][indexvalue].add(key)

        # store the data
        datastore[key] = value

    def get_version(self):
        """Return the remote JSON API version
        """
        return self.get_json("version")

    def get_authenticated_user(self):
        """Return the current logged in remote user
        """
        return self.get_first_item("users/current")

    def get_registry_records_by_key(self, key=None):
        """Return the values of the registry records
        associated to the specified keyword in the source instance.
        If keyword is None it returns the whole registry
        """
        if key is None:
            return self.get_items("registry")

        return self.get_items("registry/{}".format(key))

    def get_settings_by_key(self, key=None):
        """ Return the settings from the source instance associated
         to the keyword. If key is None it will return all the settings
        """
        if key is None:
            return self.get_items("settings")
        return self.get_items("/settings/{}".format(key))

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
            self.storage[domain]["data"] = OOBTree()
            self.storage[domain]["index"] = OOBTree()
            self.storage[domain]["users"] = OOBTree()
            self.storage[domain]["uidmap"] = OOBTree()
            self.storage[domain]["credentials"] = OOBTree()
            self.storage[domain]["registry"] = OOBTree()
            self.storage[domain]["settings"] = OOBTree()
        return self.storage[domain]

    def reindex_updated_objects(self):
        """
        Reindexes updated objects.
        """
        total = len(self.uids_to_reindex)
        logger.info('Reindexing {} objects which were updated...'.format(total))
        indexed = 0
        for uid in self.uids_to_reindex:
            obj = api.get_object_by_uid(uid[0], None)
            if obj is None:
                logger.error("Object not found: {} ".format(uid[1]))
                continue
            obj.reindexObject()
            indexed += 1
            if indexed % 100 == 0:
                logger.info('{} objects were reindexed, remain {}'.format(
                                indexed, total-indexed))

        logger.info('Reindexing finished...')

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

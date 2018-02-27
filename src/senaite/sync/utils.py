
from BTrees.OOBTree import OOBTree

from zope.annotation.interfaces import IAnnotations

from senaite import api
from DateTime import DateTime
from datetime import datetime


SOUPER_REQUIRED_FIELDS = {"uid": "remote_uid",
                          "path": "path",
                          "portal_type": "portal_type"}

SYNC_CREDENTIALS = "senaite.sync.credentials"
SKIP_PORTAL_TYPES = ["SKIP"]


def to_review_history_format(review_history):
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


def is_item_allowed(item):
    """
    Check if an item can be handled based in its portal type.
    :return:
    """
    if not isinstance(item, dict):
        return False

    portal_types = api.get_tool("portal_types")
    pt = item.get("portal_type", "SKIP")
    if pt in SKIP_PORTAL_TYPES or pt not in portal_types:
        return False

    return True


def get_parent_path(path):
    """
    Gets the parent path for a given object path.
    :param path: path of an object
    :return: parent path of the object
    """
    if path == "/":
        return "/"
    if path.endswith("/"):
        path = path[:-1]
    parts = path.split("/")
    return "/".join(parts[:-1])


def get_id_from_path(path):
    """
    Extracts the ID from a given path.
    :param path:
    :return:
    """
    parts = path.split("/")
    return parts[-1]


def get_soup_format(item):
    """ From a fetched item return a dictionary prepared for being inserted
     into the import soup. This means that the returned dictionary will only
     contain the data fields specified in SOUPER_REQUIRED_FIELDS and
     also that the keys of the returned dictionary will have been mapped
     the keys that the import soup expects.

    :param item: dictionary with item data as obtained from the json API
    :type item: dict
    :return: dictionary with the required data and expected key names
    :rtype: dict
    """
    data_dict = {}
    for key, mapped_key in SOUPER_REQUIRED_FIELDS.items():
            data_dict[mapped_key] = item.get(key)
    return data_dict


def review_history_imported(obj, review_history, wf_tool=None):
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


def get_annotation(portal):
    """Annotation storage on the portal object
    """
    if portal is None:
        portal = api.get_portal()
    return IAnnotations(portal)


def get_credentials_storage(portal):
    """
    Credentials for domains to be used for Auto Sync are stored in a different
    annotation. Required parameters for each domain are following:
        -domain_name:   Unique name for the domain,
        -url:           URL of the remote instance,
        -ac_username:   Username to log in the remote instance,
        -ac_password:   Unique name for the domain,

    Credentials are saved in a OOBTree with the structure as in the example:
    E.g:
        {
            'server_1': {
                        'url': 'http://localhost:8080/Plone/',
                        'ac_username': 'lab_man',
                        'ac_password': 'lab_man',
                        'domain_name': 'server_1',
                        },
            'client_1': {
                        'url': 'http://localhost:9090/Plone/',
                        'ac_username': 'admin',
                        'ac_password': 'admin',
                        'domain_name': 'client_1',
                        },
        }

    :param portal: Portal object.
    :return:
    """
    annotation = get_annotation(portal)
    if not annotation.get(SYNC_CREDENTIALS):
        annotation[SYNC_CREDENTIALS] = OOBTree()
    return annotation[SYNC_CREDENTIALS]


from BTrees.OOBTree import OOBTree

from zope.annotation.interfaces import IAnnotations

from senaite import api
from senaite.sync import logger
from DateTime import DateTime
from datetime import datetime


SOUPER_REQUIRED_FIELDS = {"uid": "remote_uid",
                          "path": "path",
                          "portal_type": "portal_type"}

SYNC_CREDENTIALS = "senaite.sync.credentials"

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


def is_review_history_imported(obj, review_history, wf_tool=None):
    """
    Check if review History info is already imported for given workflow.
    :param obj: the object to be checked
    :param review_history: Review State Dictionary
    :param wf_tool: Objects Workflow tool. Will be set to 'portal_worklow'
            if is None.
    :return: True if the state was found in the current review history
    """
    if wf_tool is None:
        wf_tool = api.get_tool('portal_workflow')

    state_variable = wf_tool.variables.getStateVar()
    state = review_history.get(state_variable)
    current_rh = wf_tool.getInfoFor(obj, 'review_history', '')
    for rh in current_rh:
        if rh.get(state_variable) == state:
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


def log_process(self, task_name, started, processed, total, frequency=1):
    """Logs the current status of the process
    :param task_name: name of the task
    :param started: datetime when the process started
    :param processed: number of processed items
    :param total: total number of items to be processed
    :param frequency: number of items to be processed before logging more
    :return:
    """
    if frequency <= 0 or processed % frequency > 0 or total <= 0:
        return

    percentage = "0.0"
    if processed > 0:
        percentage = "{0:.1f}".format(processed * 100.0 / total)

    estimated = get_estimated_end_date(started, processed, total)
    estimated = estimated and estimated.strftime("%Y-%m-%d %H:%M:%S") or "-"
    msg = "{}: {} / {} ({}%) - ETD: {}".format(task_name, processed, total,
                                               percentage, estimated)
    logger.info(msg)


def get_estimated_end_date(started, processed, total):
    """Returns the estimated date when the process will finish
    :param started: datetime when the process started
    :param processed: number of processed items
    :param total: total number of items to be processed
    :return: datetime object or None
    """
    remaining_items = total-processed
    if remaining_items <= 0:
        return None
    current_time = datetime.now()
    elapsed_time = current_time - started
    if elapsed_time.total_seconds() <= 0:
        return None
    remaining_time = remaining_items * elapsed_time / processed
    return current_time + remaining_time

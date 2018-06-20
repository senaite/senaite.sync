# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.SYNC
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.

from datetime import datetime

from BTrees.OOBTree import OOBTree
from DateTime import DateTime
from Products.ATContentTypes.utils import DT2dt
from senaite import api
from senaite.sync import logger
from senaite.sync.souphandler import REMOTE_UID, REMOTE_PATH, PORTAL_TYPE
from zope.annotation.interfaces import IAnnotations
from senaite.sync.souphandler import REMOTE_UID, REMOTE_PATH, PORTAL_TYPE

SOUPER_REQUIRED_FIELDS = {"uid": REMOTE_UID,
                          "path": REMOTE_PATH,
                          "portal_type": PORTAL_TYPE}

SYNC_CREDENTIALS = "senaite.sync.credentials"

_default_date_format = "%Y-%m-%d"


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


def has_valid_portal_type(item):
    """ Check if an item can be handled based on its portal type.
    :return: True if the item can be handled
    """
    if not isinstance(item, dict):
        return False

    portal_types = api.get_tool("portal_types").listContentTypes()
    pt = item.get("portal_type", None)
    if pt not in portal_types:
        return False

    return True


def filter_content_types(content_types):
    """

    :param content_types:
    :return:
    """
    ret = list()
    if not content_types:
        return ret

    # Get available portal types and make it all lowercase
    portal_types = api.get_tool("portal_types").listContentTypes()
    portal_types = [t.lower() for t in portal_types]

    ret = [t.strip() for t in content_types.split(",") if t]
    ret = filter(lambda ct, types=portal_types: ct.lower() in types, ret)
    ret = list(set(ret))
    return ret


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
    if len(parts) < 3:
        return "/"
    return str("/".join(parts[:-1]))


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
    time = DateTime(review_history.get('time'))
    current_rh = wf_tool.getInfoFor(obj, 'review_history', '')
    for rh in current_rh:
        if rh.get(state_variable) == state and time <= rh.get('time'):
            return True

    return False


def get_annotation(portal):
    """Annotation storage on the portal object
    """
    if portal is None:
        portal = api.get_portal()
    return IAnnotations(portal)


def log_process(task_name, started, processed, total, frequency=1):
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


def date_to_query_literal(date, date_format=_default_date_format):
    """ Convert a date to a valid JSONAPI URL query string.
    :param date: date to be converted in datetime, DateTime or string format
    :param date_format: in case the date is string, format to parse it
    :return string: literal date
    """
    if not date:
        return None

    if isinstance(date, DateTime):
        date = DT2dt(date)

    if isinstance(date, basestring):
        date = datetime.strptime(date, date_format)

    days = (datetime.now() - date.replace(tzinfo=None)).days

    if days < 1:
        return "today"
    if days < 2:
        return "yesterday"
    if days < 8:
        return "this-week"
    if days < 32:
        return "this-month"
    if days < 367:
        return "this-year"

    logger.warn("Interval is too long to be converted to string: {} days"
                .format(days))
    return ""

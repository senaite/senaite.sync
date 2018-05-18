# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.SYNC
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.

from Acquisition import aq_inner
from Acquisition import aq_parent
from zope.annotation.interfaces import IAnnotations

from bika.lims import api
from bika.lims import logger
from bika.lims.upgrade import upgradestep

version = '1.0.0'
profile = 'profile-{senaite.sync}:default'


@upgradestep('senaite.sync', version)
def upgrade(tool):
    portal = aq_parent(aq_inner(tool))
    annotation = IAnnotations(portal)
    if annotation.get("senaite.sync") is not None:
        del annotation["senaite.sync"]

    # New modified index on uid_catalog to query items faster
    modify_uid_catalog(portal)

    return True


def modify_uid_catalog(portal):
    """

    :param portal: portal object
    :return:
    """
    uc = api.get_tool('uid_catalog', portal)
    if 'modified' not in uc.indexes():
        logger.info("Adding a new index to 'uid_catalog'... ")
        uc.addIndex('modified', 'DateIndex')
        uc.reindexIndex('modified', None)
        logger.info("New 'modified' index added to 'uid_catalog'. ")
    return
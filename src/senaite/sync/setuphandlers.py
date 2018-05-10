# -*- coding: utf-8 -*-
#
# Copyright 2017-2018 SENAITE SYNC.

from bika.lims import logger
from bika.lims import api


def setupHandler(context):
    """SENAITE SYNC setup handler
    """

    if context.readDataFile('senaite.sync.txt') is None:
        return

    logger.info("SENAITE setup handler [BEGIN]")

    portal = context.getSite()
    modify_uid_catalog(portal)
    logger.info("SENAITE setup handler [DONE]")
    return


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

# -*- coding: utf-8 -*-
#
# Copyright 2017 SENAITE

import logging

from zope.i18nmessageid import MessageFactory

logger = logging.getLogger("senaite.sync")
_ = MessageFactory('senaite.sync')


def initialize(context):
    """Initializer called when used as a Zope 2 product."""
    logger.info("*** Initializing SENAITE SYNC ***")

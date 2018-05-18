# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.SYNC
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.

import logging

from zope.i18nmessageid import MessageFactory

logger = logging.getLogger("senaite.sync")
_ = MessageFactory('senaite.sync')


def initialize(context):
    """Initializer called when used as a Zope 2 product."""
    logger.info("*** Initializing SENAITE SYNC ***")

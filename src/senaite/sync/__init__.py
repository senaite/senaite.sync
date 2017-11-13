# -*- coding: utf-8 -*-
#
# Copyright 2017 SENAITE

import logging

logger = logging.getLogger("senaite.sync")


def initialize(context):
    """Initializer called when used as a Zope 2 product."""
    logger.info("*** Initializing SENAITE SYNC ***")

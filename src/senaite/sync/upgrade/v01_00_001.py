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

version = '1.0.1'
profile = 'profile-{senaite.sync}:default'


@upgradestep('senaite.sync', version)
def upgrade(tool):
    portal = aq_parent(aq_inner(tool))
    annotation = IAnnotations(portal)

    # -------- ADD YOUR STUFF HERE --------

    return True


# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.SYNC
#
# Copyright 2018 by it's authors.

from Acquisition import aq_inner
from Acquisition import aq_parent

from bika.lims.upgrade import upgradestep

version = '1.0.0'
profile = 'profile-{senaite.sync}:default'


@upgradestep('senaite.sync', version)
def upgrade(tool):
    portal = aq_parent(aq_inner(tool))
    return True
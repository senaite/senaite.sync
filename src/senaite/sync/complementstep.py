# -*- coding: utf-8 -*-
#
# Copyright 2017-2018 SENAITE SYNC.

from senaite.sync.importstep import ImportStep

from senaite.sync import logger


class ComplementStep(ImportStep):
    """ Class for the Import step of the Synchronization. It must create and
    update objects based on previously fetched data.

    """

    def __init__(self, data):
        ImportStep.__init__(self, data)
        self.fetch_time = data.get("fetch_time", None)

    def run(self):
        """
        :return:
        """
        self.session = self.get_session()
        return


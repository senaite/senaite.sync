# -*- coding: utf-8 -*-
#
# Copyright 2017-2017 SENAITE LIMS.

from zope import interface

from senaite.jsonapi.fieldmanagers import ATFieldManager
from senaite.jsonapi.interfaces import IFieldManager


class StringFieldManager(ATFieldManager):
    """Adapter to set/get the value of String Fields
    """
    interface.implements(IFieldManager)

    def set(self, instance, value, **kw):
        """Set the value of the field
        """
        if value is None:
            if self.field.multiValued:
                value = []
            else:
                value = ''
        return self._set(instance, value, **kw)

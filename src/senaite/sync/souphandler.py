# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.SYNC
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.

from senaite import api
from senaite.sync import logger

from zope.interface import Interface
from zope.component import provideAdapter
from souper.interfaces import IStorageLocator
from souper.soup import SoupData
from zope.interface import implementer
from souper.interfaces import ICatalogFactory
from zope.component.interfaces import ComponentLookupError
from souper.soup import NodeAttributeIndexer
from souper.soup import get_soup as souper_get_soup
from zope.component import getUtility
from zope.component import provideUtility
from repoze.catalog.catalog import Catalog
from repoze.catalog.indexes.field import CatalogFieldIndex
from souper.soup import Record
from repoze.catalog.query import Eq
from repoze.catalog.query import Or


# SOUPER TABLE COLUMNS
REMOTE_UID = 'remote_uid'
REMOTE_PATH = 'remote_path'
LOCAL_UID = 'local_uid'
LOCAL_PATH = 'local_path'
PORTAL_TYPE = 'portal_type'
UPDATED = 'updated'


class SoupHandler:
    """
    A basic class to interact with soup tables.
    """

    def __init__(self, domain_name):
        self.domain_name = domain_name
        self.portal = api.get_portal()
        self.soup = self._set_soup()

    def get_soup(self):
        return self.soup

    def _set_soup(self):
        """
        Make the soup ready.
        """
        soup = souper_get_soup(self.domain_name, self.portal)
        try:
            getUtility(ICatalogFactory, name=self.domain_name)
        except ComponentLookupError:
            self._create_domain_catalog()

        return soup

    def insert(self, data):
        """
        Inserts a row to the soup table.
        :param data: row dictionary
        :return: intid of created record
        """
        if self._already_exists(data):
            logger.debug("Trying to insert existing record... {}".format(data))
            return False
        record = Record()
        record.attrs[REMOTE_UID] = data[REMOTE_UID]
        record.attrs[LOCAL_UID] = data.get(LOCAL_UID, "")
        record.attrs[REMOTE_PATH] = data[REMOTE_PATH]
        record.attrs[LOCAL_PATH] = data.get(LOCAL_PATH, "")
        record.attrs[PORTAL_TYPE] = data[PORTAL_TYPE]
        record.attrs[UPDATED] = data.get(UPDATED, "0")
        r_id = self.soup.add(record)
        logger.info("Record {} inserted: {}".format(r_id, data))
        return r_id

    def _already_exists(self, data):
        """
        Checks if the record already exists.
        :param data: row dictionary
        :return: True or False
        """
        r_uid = data.get(REMOTE_UID, False) or '-1'
        l_uid = data.get(LOCAL_UID, False) or '-1'
        r_path = data.get(REMOTE_PATH, False) or '-1'
        l_path = data.get(LOCAL_PATH, False) or '-1'
        r_uid_q = Eq(REMOTE_UID, r_uid)
        l_uid_q = Eq(LOCAL_UID, l_uid)
        r_p_q = Eq(REMOTE_PATH, r_path)
        l_p_q = Eq(LOCAL_PATH, l_path)
        ret = [r for r in self.soup.query(Or(r_uid_q, l_uid_q, r_p_q, l_p_q))]
        return ret != []

    def get_record_by_id(self, rec_id, as_dict=False):
        try:
            record = self.soup.get(rec_id)
        except KeyError:
            return None
        if as_dict:
            record = record_to_dict(record)
        return record

    def find_unique(self, column, value):
        """
        Gets the record row by the given column and value.
        :param column: column name
        :param value: column value
        :return: record dictionary
        """
        recs = [r for r in self.soup.query(Eq(column, value))]
        if recs:
            return record_to_dict(recs[0])
        return None

    def get_local_uid(self, r_uid):
        """
        Get the local uid by remote uid
        :param r_uid: remote uid of the row
        :return: local uid from the row
        """
        recs = [r for r in self.soup.query(Eq(REMOTE_UID, r_uid))]
        if recs and len(recs) == 1:
            return record_to_dict(recs[0])[LOCAL_UID]
        return None

    def update_by_remote_uid(self, remote_uid, **kwargs):
        """
        Update the row by remote_uid column.
        :param remote_uid: UID of the object in the source
        :param kwargs: columns and their values to be updated.
        """
        recs = [r for r in self.soup.query(Eq(REMOTE_UID, remote_uid))]
        if not recs:
            logger.error("Could not find any record with remote_uid: '{}'"
                         .format(remote_uid))
            return False
        for k, v in kwargs.iteritems():
            recs[0].attrs[k] = v
        self.soup.reindex([recs[0]])
        return True

    def update_by_remote_path(self, remote_path, **kwargs):
        """
        Update the row by path column.
        :param path: path of the record
        :param kwargs: columns and their values to be updated.
        """
        recs = [r for r in self.soup.query(Eq(REMOTE_PATH, remote_path))]
        if not recs:
            logger.error("Could not find any record with path: '{}'"
                         .format(REMOTE_PATH))
            return False
        for k, v in kwargs.iteritems():
            recs[0].attrs[k] = v
        self.soup.reindex([recs[0]])
        return True

    def mark_update(self, remote_uid):
        """
        Marks that record's object has been updated.
        """
        recs = [r for r in self.soup.query(Eq(REMOTE_UID, remote_uid))]
        if not recs:
            logger.error("Could not find any record with remote_uid: '{}'"
                         .format(remote_uid))
            return False
        recs[0].attrs[UPDATED] = "1"
        self.soup.reindex([recs[0]])
        return True

    def reset_updated_flags(self):
        """
        Set all updated values to '0'
        :return:
        """
        for intid in self.soup.data:
            rec = self.soup.get(intid)
            rec.attrs[UPDATED] = "0"
        self.soup.reindex()
        return True

    def _create_domain_catalog(self):
        """
        To query and access soup table, create a catalog.
        :return:
        """
        @implementer(ICatalogFactory)
        class DomainSoupCatalogFactory(object):
            def __call__(self, context=None):
                catalog = Catalog()
                r_uid_indexer = NodeAttributeIndexer(REMOTE_UID)
                catalog[unicode(REMOTE_UID)] = CatalogFieldIndex(r_uid_indexer)

                l_uid_indexer = NodeAttributeIndexer(LOCAL_UID)
                catalog[unicode(LOCAL_UID)] = CatalogFieldIndex(l_uid_indexer)

                r_path_indexer = NodeAttributeIndexer(REMOTE_PATH)
                catalog[unicode(REMOTE_PATH)] = CatalogFieldIndex(r_path_indexer)

                l_path_indexer = NodeAttributeIndexer(LOCAL_PATH)
                catalog[unicode(LOCAL_PATH)] = CatalogFieldIndex(l_path_indexer)

                return catalog

        provideUtility(DomainSoupCatalogFactory(), name=self.domain_name)

    @implementer(IStorageLocator)
    class StorageLocator(object):
        """
        Compulsory locator class for the soup.
        """
        def __init__(self, context):
            # Context is the portal object.
            self.context = context

        def storage(self, soup_name):
            if soup_name not in self.context:
                try:
                    self.context[soup_name] = SoupData()
                except AttributeError:
                    pass
            return self.context[soup_name]

    provideAdapter(StorageLocator, adapts=[Interface])


def record_to_dict(record):
    """
    Convert the soup record to dictionary
    :param record: to be converted
    :return: dictionary with necessary data
    """
    ret = {
        'rec_int_id': record.intid,
        REMOTE_UID: record.attrs.get(REMOTE_UID, ""),
        LOCAL_UID: record.attrs.get(LOCAL_UID, ""),
        REMOTE_PATH: record.attrs.get(REMOTE_PATH, ""),
        LOCAL_PATH: record.attrs.get(LOCAL_PATH, ""),
        UPDATED: record.attrs.get(UPDATED, "0"),
        PORTAL_TYPE: record.attrs.get(PORTAL_TYPE, "")
    }
    return ret


def delete_soup(portal, domain_name):
    """
    Clears soup data.
    :param portal: portal object
    :param domain_name:
    :return:
    """
    soup = souper_get_soup(domain_name, portal)
    try:
        soup.clear()
    except ComponentLookupError:
        pass
    return True

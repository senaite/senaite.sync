

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
            logger.info("Trying to insert existing record... {}".format(data))
            return False
        record = Record()
        record.attrs['remote_uid'] = data['remote_uid']
        record.attrs['path'] = data['path']
        record.attrs['portal_type'] = data['portal_type']
        record.attrs['local_uid'] = data.get('local_uid', "")
        record.attrs['updated'] = data.get('updated', "0")
        r_id = self.soup.add(record)
        logger.info("Record {} inserted: {}".format(r_id, data))
        return r_id

    def _already_exists(self, data):
        """
        Checks if the record already exists.
        :param data: row dictionary
        :return: True or False
        """
        r_uid = data.get("remote_uid", False) or '-1'
        l_uid = data.get("local_uid", False) or '-1'
        path = data.get("path", False) or '-1'
        r_uid_q = Eq('remote_uid', r_uid)
        l_uid_q = Eq('local_uid', l_uid)
        p_q = Eq('path', path)
        ret = [r for r in self.soup.query(Or(r_uid_q, l_uid_q, p_q))]
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
        recs = [r for r in self.soup.query(Eq("remote_uid", r_uid))]
        if recs and len(recs) == 1:
            return record_to_dict(recs[0])["local_uid"]
        return None

    def update_by_remote_uid(self, remote_uid, **kwargs):
        """
        Update the row by remote_uid column.
        :param remote_uid: UID of the object in the source
        :param kwargs: columns and their values to be updated.
        """
        recs = [r for r in self.soup.query(Eq('remote_uid', remote_uid))]
        if not recs:
            logger.error("Could not find any record with remote_uid: '{}'"
                         .format(remote_uid))
            return False
        for k, v in kwargs.iteritems():
            recs[0].attrs[k] = v
        self.soup.reindex([recs[0]])
        return True

    def update_by_path(self, path, **kwargs):
        """
        Update the row by path column.
        :param path: path of the record
        :param kwargs: columns and their values to be updated.
        """
        recs = [r for r in self.soup.query(Eq('path', path))]
        if not recs:
            logger.error("Could not find any record with path: '{}'"
                         .format(path))
            return False
        for k, v in kwargs.iteritems():
            recs[0].attrs[k] = v
        self.soup.reindex([recs[0]])
        return True

    def mark_update(self, remote_uid):
        """
        Marks that record's object has been updated.
        """
        recs = [r for r in self.soup.query(Eq('remote_uid', remote_uid))]
        if not recs:
            logger.error("Could not find any record with remote_uid: '{}'"
                         .format(remote_uid))
            return False
        recs[0].attrs["updated"] = "1"
        self.soup.reindex([recs[0]])
        return True

    def reset_updated_flags(self):
        """
        Set all updated values to '0'
        :return:
        """
        for intid in self.soup.data:
            rec = self.soup.get(intid)
            rec.attrs["updated"] = "0"
            self.soup.reindex(rec)
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
                r_uid_indexer = NodeAttributeIndexer('remote_uid')
                catalog[u'remote_uid'] = CatalogFieldIndex(r_uid_indexer)
                path_indexer = NodeAttributeIndexer('path')
                catalog[u'path'] = CatalogFieldIndex(path_indexer)
                l_uid_indexer = NodeAttributeIndexer('local_uid')
                catalog[u'local_uid'] = CatalogFieldIndex(l_uid_indexer)
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
        'remote_uid': record.attrs.get('remote_uid', ""),
        'local_uid': record.attrs.get('local_uid', ""),
        'path': record.attrs.get('path', ""),
        'updated': record.attrs.get('updated', "0"),
        'portal_type': record.attrs.get('portal_type', "")
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

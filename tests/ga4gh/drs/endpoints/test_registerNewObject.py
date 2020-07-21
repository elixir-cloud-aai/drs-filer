from drs_filer.ga4gh.drs.endpoints.registerNewObject import registerNewObject
import mongomock
import pytest


def test_registerNewObject():
    """registerNewObject should raise an exception on duplicate key"""
    collection = mongomock.MongoClient().db.collection
    jsonData = {"_id": "1"}
    collection.insert_one(jsonData)
    with pytest.raises(Exception):
        registerNewObject(collection, jsonData)

from drs_filer.ga4gh.drs.endpoints.register_new_objects import (
    register_new_objects)
import mongomock
import pytest

from addict import Dict


def test_register_new_object():
    """registerNewObject should raise an exception on duplicate key"""
    collection = mongomock.MongoClient().db.collection
    json_data = Dict()
    json_data.json = {"id": "1"}
    collection.insert_one(json_data.json)
    with pytest.raises(Exception):
        register_new_objects(json_data)

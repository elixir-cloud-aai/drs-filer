import logging

from flask import (current_app)
from flask.globals import request

from drs_filer.ga4gh.drs.endpoints import registerNewObject

from werkzeug.exceptions import NotFound

logger = logging.getLogger(__name__)


def RegisterObject():
    db_collection = (
        current_app.config['FOCA'].db.dbs['drsStore'].
        collections['objects'].client
    )
    json_data = request.json
    response = registerNewObject.registerNewObject(
        db_collection,
        json_data
    )
    return response


def GetObject(object_id):
    db_collection = (
        current_app.config['FOCA'].db.dbs['drsStore'].
        collections['objects'].client
    )

    obj = db_collection.find_one({"id": object_id})
    del obj["_id"]
    return obj


def GetAccessURL(object_id, access_id):
    db_collection = (
        current_app.config['FOCA'].db.dbs['drsStore'].
        collections['objects'].client
    )

    obj = db_collection.find_one({"id": object_id})
    # create the response

    access_methods = obj["access_methods"]
    response = dict()
    logger.info(access_methods)
    found = False
    for access_method in access_methods:
        if access_method["access_id"] == access_id:
            response = access_method["access_url"]
            found = True
            break
    if found:
        return response
    else:
        raise NotFound

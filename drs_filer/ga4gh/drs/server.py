import logging

from flask import (current_app)
from flask.globals import request

from drs_filer.ga4gh.drs.endpoints import registerNewObject

logger = logging.getLogger(__name__)


def registerObject():
    db_collection = (
        current_app.config['FOCA'].db.dbs['drsStore'].
        collections['objects'].client
    )
    response = registerNewObject.registerNewObject(
        db_collection,
        request.json
    )
    return response


def getObject(object_id):
    db_collection = (
        current_app.config['FOCA'].db.dbs['drsStore'].
        collections['objects'].client
    )

    obj = db_collection.find_one_or_404({"id": object_id})
    obj.pop("_id")
    print("obj: ", obj)
    return obj, 200


def getAccessURL(object_id, access_id):
    db_collection = (
        current_app.config['FOCA'].db.dbs['drsStore'].
        collections['objects'].client
    )

    obj = db_collection.find_one_or_404({"id": object_id})
    # create the response
    access_methods = obj["access_methods"]

    response = {
        "detail": "The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.",
        "status": 404,
        "title": "Not Found",
        "type": "about:blank"
    }
    found = False
    for access_method in access_methods:
        if access_method["access_id"] == access_id:
            response = access_method["access_url"]
            found = True
            break
    if found:
        return response, 200
    else:
        return response, 404

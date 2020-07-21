import logging
from foca.errors.exceptions import handle_problem

logger = logging.getLogger(__name__)


def registerNewObject(db_collection, jsonData):
    try:
        db_collection.insert_one(jsonData)
        del jsonData['_id']
        return jsonData
    except Exception as e:
        return handle_problem(e)

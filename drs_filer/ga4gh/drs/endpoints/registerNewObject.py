import logging
from foca.errors.exceptions import handle_problem

logger = logging.getLogger(__name__)


def registerNewObject(db_collection, jsonData):
    try:
        db_collection.insert(jsonData)
        return {"object created id: ": jsonData['id']}
    except Exception as e:
        return handle_problem(e)

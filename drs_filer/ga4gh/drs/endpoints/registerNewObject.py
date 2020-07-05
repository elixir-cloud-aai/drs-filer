import logging
import logging

logger = logging.getLogger(__name__)

error_respose = {
    "status": "Something is wrong"
}


def registerNewObject(db_collection, jsonData):
    try:
        db_collection.insert(jsonData)
        return jsonData
    except Exception as e:
        logger.error(f"{type(e).__name__}: {e}")
        return error_respose

"""Controller for adding new DRS objects."""

from flask import (current_app, request)


def register_new_objects(request: request) -> str:
    """Add new objects to DRS registry.

    Args:
        request: API request object.

    Returns:
        A unique identifier for the object.
    """
    db_collection = (
        current_app.config['FOCA'].db.dbs['drsStore'].
        collections['objects'].client
    )
    db_collection.insert_one(request.json)
    return request.json['id']

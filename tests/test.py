import os
import requests
import time
import pytest

DRS_FILER_URL = os.getenv('DRS_FILER_URL')

@pytest.fixture(scope="function")
def get_object_id():
    object_id = test_create_object()
    yield object_id

@pytest.fixture(scope="function")
def get_access_id(get_object_id):
    access_id = test_get_object(get_object_id).get('access_methods')[0].get('access_id')
    yield access_id

def handle_error(response):
    """Helper function to handle common error cases."""
    if response.status_code == 400:
        print(f"400 Bad Request: {response.json().get('msg')}")
    elif response.status_code == 401:
        print(f"401 Unauthorized: {response.json().get('msg')}")
    elif response.status_code == 403:
        print(f"403 Forbidden: {response.json().get('msg')}")
    elif response.status_code == 404:
        print(f"404 Not Found: {response.json().get('msg')}")
    elif response.status_code == 409:
        print(f"409 Conflict: {response.json()}")
    elif response.status_code == 500:
        print(f"500 Internal Server Error: {response.json().get('msg')}")
    else:
        print(f"Unexpected status code {response.status_code}: {response.json().get('msg')}")

def test_create_object():
    data = {
        "access_methods": [
            {
                "access_url": {
                    "headers": [],
                    "url": "http://example.com/data"
                },
                "region": "us-east-1",
                "type": "s3"
            }
        ],
        "aliases": [
            "example_alias"
        ],
        "checksums": [
            {
                "checksum": "abc123",
                "type": "sha-256"
            }
        ],
        "contents": [],
        "created_time": "2024-06-12T12:58:19Z",
        "description": "An example object",
        "mime_type": "application/json",
        "name": "example_object",
        "size": 1024,
        "updated_time": "2024-06-12T12:58:19Z",
        "version": "1.0"
    }
    
    response = requests.post(f"{DRS_FILER_URL}/objects", json=data)
    
    if response.status_code == 200:
        object_id = response.json()
        print(f"Created object with ID: {object_id}")
        return object_id
    else:
        handle_error(response)
        return None

def test_get_objects():
    response = requests.get(f"{DRS_FILER_URL}/objects")
    if response.status_code == 200:
        print("Following are the objects: ")
        print(response.json())
    else:
        handle_error(response)

def test_get_object(get_object_id):
    object_id = get_object_id

    response = requests.get(f"{DRS_FILER_URL}/objects/{object_id}")
    
    if response.status_code == 200:
        print(f"Following is the object retrieved based on {object_id}:")
        print(response.json())
        return response.json()
    elif response.status_code == 202:
        retry_after = int(response.headers.get("Retry-After", 5))
        print(f"202 Accepted: Operation is delayed. Retry after {retry_after} seconds.")
        time.sleep(retry_after)
        return test_get_object(object_id)  # Retry the request
    else:
        handle_error(response)
        return None

def test_get_object_access(get_object_id, get_access_id):
    object_id = get_object_id
    access_id = get_access_id

    response = requests.get(f"{DRS_FILER_URL}/objects/{object_id}/access/{access_id}")
    
    if response.status_code == 200:
        print(f"Following is the object retrieved based on {object_id} and {access_id}:")
        print(response.json())
    elif response.status_code == 202:
        retry_after = int(response.headers.get("Retry-After", 5))
        print(f"202 Accepted: Operation is delayed. Retry after {retry_after} seconds.")
        time.sleep(retry_after)
        return test_get_object_access(object_id, access_id)  # Retry the request
    else:
        handle_error(response)

def test_update_object(get_object_id):
    object_id = get_object_id
    
    data = {
        "access_methods": [
            {
                "access_url": {
                    "headers": ["string"],
                    "url": "string"
                },
                "region": "us-east-1",
                "type": "s3"
            }
        ],
        "aliases": ["string"],
        "checksums": [
            {
                "checksum": "string",
                "type": "sha-256"
            }
        ],
        "contents": [
            {
                "contents": [],
                "drs_uri": [
                    "drs://drs.example.org/314159",
                    "drs://drs.example.org/213512"
                ],
                "id": "string",
                "name": "string"
            }
        ],
        "created_time": "2024-07-03T14:16:59.268Z",
        "description": "string",
        "mime_type": "application/json",
        "name": "string",
        "size": 0,
        "updated_time": "2024-07-03T14:16:59.268Z",
        "version": "string"
    }
    
    response = requests.put(f"{DRS_FILER_URL}/objects/{object_id}", json=data)
    
    if response.status_code == 200:
        print(f"Updated the object with ID: {object_id}")
    else:
        handle_error(response)

def test_delete_object_access(get_object_id, get_access_id):
    object_id=get_object_id
    access_id=get_access_id
    
    response = requests.delete(f"{DRS_FILER_URL}/objects/{object_id}/access/{access_id}")
    
    if response.status_code == 404:
        print(f"Object with ID {object_id} or access ID {access_id} not found.")
    elif response.status_code == 409:
        print(f"Refusing to delete the last remaining access method for object {object_id}.")
    elif response.status_code == 200:
        print(f"Deleted access method with ID {access_id} for object {object_id}.")
    else:
        handle_error(response)

def test_delete_object(get_object_id):
    object_id=get_object_id

    response = requests.delete(f"{DRS_FILER_URL}/objects/{object_id}")
    
    if response.status_code == 200:
        print(f"Deleted the object with ID: {object_id}")
    else:
        handle_error(response)

def test_post_service_info():
    data = {
        "contactUrl": "mailto:support@example.com",
        "createdAt": "2024-06-12T12:58:19Z",
        "description": "This service provides...",
        "documentationUrl": "https://docs.myservice.example.com",
        "environment": "test",
        "id": "org.ga4gh.myservice",
        "name": "My project",
        "organization": {
            "name": "My organization",
            "url": "https://example.com"
        },
        "type": {
            "artifact": "beacon",
            "group": "org.ga4gh",
            "version": "1.0.0"
        },
        "updatedAt": "2024-06-12T12:58:19Z",
        "version": "1.0.0"
    }
    
    response = requests.post(f"{DRS_FILER_URL}/service-info", json=data)
    
    if response.status_code == 201:
        print("Service info was successfully created.")
    else:
        handle_error(response)

def test_get_service_info():
    response = requests.get(f"{DRS_FILER_URL}/service-info")
    if response.status_code == 200:
        print("Retrieved service info:")
        print(response.json())
    else:
        handle_error(response)

if __name__ == "__main__":
    test_get_objects()
    test_get_object()
    test_get_object_access()
    test_update_object()
    test_delete_object_access()
    test_delete_object()
    test_post_service_info()
    test_get_service_info()
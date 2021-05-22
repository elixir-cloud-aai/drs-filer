import json
import requests

from tests.mock_data import (
    MOCK_OBJECT,
    MOCK_SERVICE_INFO
)


access_id = ""
base_url = "http://localhost:8080/ga4gh/drs/v1"
headers = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}
object_id = ""
payload_objects = json.dumps(MOCK_OBJECT)
payload_service_info = json.dumps(MOCK_SERVICE_INFO)


def test_error_404():
    """Test `GET /` for response 404 (Page not found)"""
    endpoint = "/test_endpoint"
    response = requests.request("GET", base_url + endpoint, headers=headers,
                                data={})
    assert response.status_code == 404


def test_post_service_info():
    """Test `POST /service-info` for successfully creating or updating a new
    service-info.
    """
    endpoint = "/service-info"
    response = requests.request("POST", base_url + endpoint, headers=headers,
                                data=payload_service_info)
    assert response.status_code == 201


def test_get_service_info():
    """Test `GET /service-info` for fetching service info."""
    endpoint = "/service-info"
    response = requests.request("GET", base_url + endpoint, headers=headers)
    assert response.status_code == 200
    assert json.loads(response.content) == json.loads(payload_service_info)


def test_error_400_service_info():
    """Test `POST /service-info` for response 400 (Bad request)"""
    endpoint = "/service-info"
    response = requests.request("POST", base_url + endpoint, headers=headers,
                                data={})
    assert response.status_code == 400


def test_post_objects():
    """Test `POST /objects` for successfully registering an DrsObject."""
    global object_id
    endpoint = "/objects"
    response = requests.request("POST", base_url + endpoint, headers=headers,
                                data=payload_objects)
    object_id = response.text.replace("\"", "").replace("\n", "")
    assert response.status_code == 200


def test_get_objects():
    """Test `GET /objects/{object_id}` for fetching info about DrsObject."""
    global access_id
    is_expand = "True"
    endpoint = "/objects/" + object_id + "?expand=" + is_expand
    response = requests.request("GET", base_url + endpoint, headers=headers)
    response_content = json.loads(response.text)
    access_id = response_content['access_methods'][0]['access_id']
    assert response.status_code == 200
    assert response_content['name'] == json.loads(payload_objects)['name']


def test_error_404_get_objects():
    """Test `GET /objects/{object_id}` for response 404 (Page not
    found)
    """
    endpoint = "/objects" + "/test_id"
    response = requests.request("GET", base_url + endpoint, headers=headers,
                                data={})
    assert response.status_code == 404


def test_error_400_objects():
    """Test `POST /objects` for response 400 (Bad request)"""
    endpoint = "/objects"
    response = requests.request("POST", base_url + endpoint, headers=headers,
                                data={})
    assert response.status_code == 400


def test_get_objects_access():
    """Test `GET /objects/{object_id}/access/{access_id}` for fetching URL to
    fetch the bytes of a DrsObject
    """
    endpoint = "/objects/" + object_id + "/access/" + access_id
    response = requests.request("GET", base_url + endpoint, headers=headers)
    response_content = json.loads(response.text)
    assert response.status_code == 200
    assert response_content['url'] == \
        json.loads(payload_objects)['access_methods'][0]['access_url']['url']


def test_error_404_get_objects_access():
    """Test 'GET /objects/{object_id}/access/{access_id}' for handling
    ERROR 404 (Page not found)
    """
    endpoint = "/objects/" + object_id + "/access/" + "test_access_id"
    response = requests.request("GET", base_url + endpoint, headers=headers)
    assert response.status_code == 404


def test_put_objects():
    """Test `PUT /objects/{object_id}` to modify or update a DrsObject"""
    global access_id
    endpoint = "/objects/" + object_id
    object_put_payload = json.loads(payload_objects)
    object_put_payload['name'] = "gerp_constrained_elements.tetraodon_" + \
        "nigroviridis.bed.gz"
    response = requests.request("PUT", base_url + endpoint, headers=headers,
                                data=json.dumps(object_put_payload))
    assert response.status_code == 200
    is_expand = "True"
    endpoint = "/objects/" + object_id + "?expand=" + is_expand
    response = requests.request("GET", base_url + endpoint, headers=headers)
    response_content = json.loads(response.text)
    access_id = response_content['access_methods'][0]['access_id']
    assert response.status_code == 200
    assert response_content['name'] == \
        "gerp_constrained_elements.tetraodon_nigroviridis.bed.gz"


def test_delete_objects_access():
    """Test `DELETE /objects/{object_id}/access/{access_id}` to delete
    DrsObject's access method.
    """
    endpoint = "/objects/" + object_id + "/access/" + access_id
    response = requests.request("DELETE", base_url + endpoint, headers=headers)
    assert response.status_code == 200
    assert response.text.replace("\"", "").replace("\n", "") == access_id


def test_delete_objects():
    """Test `DELETE /objects/{object_id}` to delete existing DrsObject"""
    endpoint = "/objects/" + object_id
    response = requests.request("DELETE", base_url + endpoint, headers=headers)
    assert response.status_code == 200
    assert response.text.replace("\"", "").replace("\n", "") == object_id

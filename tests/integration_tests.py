import json
import requests

base_url = "http://localhost:8080/ga4gh/drs/v1"
data_objects_path = "data_objects.json"
headers = {
    'accept': 'application/json',
    'Content-Type': 'application/json'
}
payload_objects = json.dumps({
    "name": "Homo_sapiens.GRCh38.dna.chromosome.19.fa.gz",
    "size": 16700000,
    "created_time": "2021-05-04T11:59:56.400Z",
    "updated_time": "2021-05-04T11:59:56.400Z",
    "version": "38",
    "mime_type": "application/json",
    "checksums": [
        {
            "checksum": "18c2f5517e4ddc02cd57f6c7554b8e88",
            "type": "md5"
        }
    ],
    "access_methods": [
        {
            "type": "ftp",
            "access_url": {
                "url": "ftp://ftp.ensembl.org/pub/release-96/fasta/homo_sapien"
                "s/dna//Homo_sapiens.GRCh38.dna.chromosome.19.fa.gz",
                "headers": [
                    "None"
                ]
            },
            "region": "us-east-1"
        },
        {
            "type": "ftp",
            "access_url": {
                "url": "ftp://ftp.ensembl.org/pub/release-96/fasta/homo_sapien"
                "s/dna//Homo_sapiens.GRCh38.dna.chromosome.19.fa.gz",
                "headers": [
                    "None"
                ]
            },
            "region": "us-east-1"
        },
    ],
    "contents": [
        {
            "name": "Homo_sapiens",
            "id": "b001",
            "drs_uri": [
                "drs://drs.example.org/314159",
                "drs://drs.example.org/213512"
            ],
            "contents": []
        }
    ],
    "description": "description",
    "aliases": [
        "alias1"
    ]
})
payload_service_info = json.dumps({
    "contactUrl": "mailto:support@example.com",
    "createdAt": "2019-06-04T12:58:19Z",
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
    "updatedAt": "2019-06-04T12:58:19Z",
    "version": "1.0.0"
})
access_id = ""
object_id = ""


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

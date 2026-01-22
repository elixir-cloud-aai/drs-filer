"""Mock data for testing."""

MOCK_OBJECT = {
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
}

MOCK_SERVICE_INFO = {
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
}

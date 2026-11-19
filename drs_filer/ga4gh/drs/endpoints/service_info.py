"""Controller for service info endpoint.

The service info is stored as a single record, with `_id` `CURRENT_ID`,
which `GET /service-info` serves, with the DRS fields that the app computes
(`drs_service_fields()`, with the stats of the objects of `object_stats()`).
On startup, the service info of the config
(FOCA's section `service_info`, with the version of the package unless
`service_info.service.version` is set) replaces it, if it differs; `POST
/service-info` replaces it until the next startup. Both remove the records
that earlier versions stored (one per service info `id`).
"""

import logging
from typing import Any

from foca.api.service_info import get_service_info as get_config_service_info
from pymongo.errors import DuplicateKeyError

from drs_filer.errors.exceptions import NotFound
from drs_filer.utils import get_collection

logger = logging.getLogger(__name__)

# `_id` of the record of the service info that is served
CURRENT_ID = "current"
# The maximum number of identifiers of bulk requests (`maxBulkRequestLength`
# of DRS 1.5.0, which `DrsService` requires): the bulk operations aren't
# implemented (`501`, see "Passport POST endpoints" in `docs/api.md`), so it
# is the least that the specification allows
MAX_BULK_REQUEST_LENGTH = 1
# The service type of the API that the app serves (DRS 1.5.0); the service
# info must have it (config and `POST /service-info`)
SERVICE_TYPE = {"group": "org.ga4gh", "artifact": "drs", "version": "1.5.0"}


def object_stats() -> dict[str, int]:
    """Get the stats of the registered objects, from the database.

    They are computed on each request: a count of the objects, and an
    aggregate over the sizes of the blobs.

    Returns:
        The stats of `DrsService` (DRS 1.5.0): `objectCount`, the number of
        objects, blobs and bundles; `totalObjectSize`, the total size of the
        blobs (objects without `contents`), in bytes. Bundles aren't added,
        as their size is that of their contents, nor are the access methods
        of an object, which are copies of the same bytes (as the
        specification recommends: "file bytes are counted for each unique
        file and not cloud mirrors or other redundant copies").
    """
    objects = get_collection("objects")
    count = objects.count_documents({})
    totals = list(
        objects.aggregate(
            [
                {"$match": {"contents": {"$exists": False}}},
                {"$group": {"_id": None, "size": {"$sum": "$size"}}},
            ]
        )
    )
    size = int(totals[0]["size"]) if totals else 0
    return {"objectCount": count, "totalObjectSize": size}


def drs_service_fields() -> dict[str, Any]:
    """Get the DRS fields of the service info, which the app computes.

    They are added to the stored service info when it is served (`GET
    /service-info`), not stored, and can't be posted.

    Returns:
        The fields of `DrsService` (DRS 1.5.0): `maxBulkRequestLength`
        (deprecated) and `drs`, with the bulk maximum and the stats of the
        objects (`object_stats()`).
    """
    return {
        "maxBulkRequestLength": MAX_BULK_REQUEST_LENGTH,
        "drs": {"maxBulkRequestLength": MAX_BULK_REQUEST_LENGTH, **object_stats()},
    }


class RegisterServiceInfo:
    """Tool class for registering service info.

    Sets the service info from the config on startup, and from requests.
    """

    def __init__(self) -> None:
        """Initialize class requirements.

        Attributes:
            db_coll_info: Database collection storing service info objects.
        """
        self.db_coll_info = get_collection("service_info")

    def get_service_info(self) -> dict[str, Any]:
        """Get the current service info from the database.

        Returns:
            Current service info details.

        Raises:
            drs_filer.errors.exceptions.NotFound: No service info is set.
        """
        record: dict[str, Any] | None = self.db_coll_info.find_one(
            {"_id": CURRENT_ID}, {"_id": False}
        )
        if record is None:
            raise NotFound
        return record

    def set_service_info_from_config(
        self,
    ) -> None:
        """Create or update service info from service configuration.

        Will create service info if it does not exist or current
        configuration differs from available one, replacing service info
        set by a request (`POST /service-info`). FOCA validates the service
        info of the config on startup, against the service info
        specification.

        Raises:
            RuntimeError: No service info is configured (`service_info`).
        """
        conf_info = get_config_service_info()
        try:
            db_info = self.get_service_info()
        except NotFound:
            db_info = {}
        if db_info != conf_info:
            self._upsert_service_info(data=conf_info)
            logger.info("Service info registered.")
        else:
            logger.info("Using available service info.")

    def _upsert_service_info(
        self,
        data: dict[str, Any],
    ) -> None:
        """Insert or replace the current service info document.

        Removes the records stored by earlier versions first, as the unique
        index on `id` refuses a second record with the same `id`. The
        current record is never removed, so service info can only be
        missing briefly before it is set for the first time. If an instance
        of an earlier version stores a record with the same `id` in between
        (e.g., during a rolling update), it is removed, and the replacement
        is tried once more.

        Args:
            data: Service info according to API specification.
        """
        self.db_coll_info.delete_many({"_id": {"$ne": CURRENT_ID}})
        try:
            self._replace_current(data=data)
        except DuplicateKeyError:
            self.db_coll_info.delete_many(
                {"id": data["id"], "_id": {"$ne": CURRENT_ID}}
            )
            self._replace_current(data=data)

    def _replace_current(self, data: dict[str, Any]) -> None:
        """Insert or replace the current service info document.

        Args:
            data: Service info according to API specification.
        """
        self.db_coll_info.replace_one(
            filter={"_id": CURRENT_ID},
            replacement=data,
            upsert=True,
        )

    def set_service_info_from_app_context(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Set service info from a request.

        Arguments:
            data: Service info according to API specification.

        Returns:
            Response headers.
        """
        self._upsert_service_info(data=data)
        return self._get_headers()

    def _get_headers(self) -> dict[str, Any]:
        """Build dictionary of response headers.

        The `Location` of the service info is a relative reference (RFC
        3986, section 4.2), which clients resolve against the URL that the
        service info was posted to (`POST /service-info`, the same as that
        of `GET /service-info`), so that it needs no public URL and holds
        behind proxies with other hosts, ports or path prefixes.

        Returns:
            Response headers.
        """
        return {
            "Content-type": "application/json",
            "Location": "service-info",
        }

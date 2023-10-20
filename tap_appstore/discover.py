import requests
import singer
from appstoreconnect import Api
from appstoreconnect.api import APIError
from singer.catalog import Catalog, CatalogEntry
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from tap_appstore.schema import load_schemas
from tap_appstore.streams import STREAMS

LOGGER = singer.get_logger()


def do_discover(client: Api) -> Catalog:
    LOGGER.info("Running discover")
    catalog = discover(client)
    LOGGER.info("Completed discover")
    return catalog


@retry(
    stop=stop_after_attempt(5),
    wait=wait_fixed(1),
    retry=retry_if_exception_type(APIError),
    after=lambda retry_state: LOGGER.info(f"Retrying... Attempt {retry_state.attempt_number} "
                                          f"failed with error: {retry_state.outcome.exception()}"),
    reraise=True
)
def discover(client: Api) -> Catalog:
    """
    Run the discovery mode, prepare the catalog file and return catalog.
    """
    schemas, field_metadata = load_schemas()
    catalog = Catalog([])
    for schema_name, schema in schemas.items():
        LOGGER.info("Discovering schema for %s", schema_name)

        try:
            # checking API credentials
            assert len(client.list_users()) > 0, 'API call failed - List of users is empty'
        except APIError as e:
            raise Exception(f'API Call failed {e}')

        if schema_name in STREAMS:
            # create and add catalog entry
            catalog_entry = CatalogEntry(
                stream=schema_name,
                tap_stream_id=schema_name,
                schema=schema,
                key_properties=[],
                metadata=field_metadata[schema_name]
            )
            catalog.streams.append(catalog_entry)

    if len(catalog.streams) == 0:
        LOGGER.warning("Could not find any reports types to download for the input configuration.")

    return catalog

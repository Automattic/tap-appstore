#!/usr/bin/env python3
import atexit
import json
import os
import tempfile

import singer
from appstoreconnect import Api
from singer import Catalog, utils

from tap_appstore.discover import discover, do_discover
from tap_appstore.sync import sync

REQUIRED_CONFIG_KEYS = [
    'key_id',
    'issuer_id',
    'vendor',
    'start_date'
]

LOGGER = singer.get_logger()

def _delete_temp_file(temp_filename) -> None:
    try:
        LOGGER.info(f"Cleaning up: {temp_filename}")
    finally:
        os.remove(temp_filename)
        LOGGER.info(f"Temporary key_file deleted: {temp_filename}")

def _create_temp_key_file(key_file_str) -> str:
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_filename = temp_file.name
    with open(temp_filename, "w") as file:
        file.write(key_file_str)
    LOGGER.info(f"Temporary key_file created: {temp_filename}")
    atexit.register(_delete_temp_file, temp_filename)
    return temp_filename

@utils.handle_top_exception(LOGGER)
def main():
    # Parse command line arguments
    args = utils.parse_args(REQUIRED_CONFIG_KEYS)

    config = args.config
    if "key_file" not in config and "key_file_str" not in config:
        raise Exception("Config is missing required keys: key_file or key_file_str.")

    if config.get('key_file_str'):
        config['key_file'] = _create_temp_key_file(config.pop("key_file_str"))

    client = Api(config['key_id'], config['key_file'], config['issuer_id'], submit_stats=False)

    state = {}
    if args.state:
        state = args.state

    if args.discover:
        # If discover flag was passed, run discovery mode and dump output to stdout
        catalog = do_discover(client)
        print(json.dumps(catalog.to_dict(), indent=2))
    elif args.properties:
        catalog = Catalog.from_dict(args.properties)
        sync(client, config, state, catalog)
    elif args.catalog:
        sync(client, config, state, args.catalog)
    else:
        catalog = do_discover(client)
        sync(client, config, state, catalog)


if __name__ == '__main__':
    main()

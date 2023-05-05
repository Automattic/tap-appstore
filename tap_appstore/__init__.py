#!/usr/bin/env python3
from datetime import datetime
import os
import json
from enum import Enum
from pprint import pprint
from typing import Dict, Union, List

import singer
from dateutil.relativedelta import relativedelta
from singer import utils, metadata, Transformer, Catalog, CatalogEntry, Schema

from appstoreconnect import Api
from appstoreconnect.api import APIError

REQUIRED_CONFIG_KEYS = [
    'key_id',
    'key_file',
    'issuer_id',
    'vendor',
    'start_date'
]

STATE = {}

LOGGER = singer.get_logger()

BOOKMARK_DATE_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
TIME_EXTRACTED_FORMAT = '%Y-%m-%dT%H:%M:%S%z'

SALES_API_REQUEST_FIELDS = {
    'subscription_event_report': {
        'reportType': 'SUBSCRIPTION_EVENT',
        'frequency': 'DAILY',
        'reportSubType': 'SUMMARY',
        'version': '1_3'
    },
    'subscriber_report': {
        'reportType': 'SUBSCRIBER',
        'frequency': 'DAILY',
        'reportSubType': 'DETAILED',
        'version': '1_3'
    },
    'subscription_report': {
        'reportType': 'SUBSCRIPTION',
        'frequency': 'DAILY',
        'reportSubType': 'SUMMARY',
        'version': '1_3'
    },
    'sales_report': {
        'reportType': 'SALES',
        'frequency': 'DAILY',
        'reportSubType': 'SUMMARY',
        'version': '1_0'
    },
    'subscription_offer_code_redemption_report': {
        'reportType': 'SUBSCRIPTION_OFFER_CODE_REDEMPTION',
        'frequency': 'DAILY',
        'reportSubType': 'SUMMARY',
        'version': '1_0'
    },
    'newsstand_report': {
        'reportType': 'NEWSSTAND',
        'frequency': 'DAILY',
        'reportSubType': 'DETAILED',
        'version': '1_0'
    },
    'pre_order_report': {
        'reportType': 'PRE_ORDER',
        'frequency': 'DAILY',
        'reportSubType': 'SUMMARY',
        'version': '1_0'
    }
}

FINANCIAL_REPORT = 'financial_report'


class ReportType(Enum):
    SALES = 1
    FINANCE = 2


class Context:
    config = {}
    state = {}
    catalog: Catalog = None
    tap_start = None
    stream_map = {}

    @classmethod
    def get_catalog_entry(cls, stream_name):
        if not cls.stream_map:
            cls.stream_map = {s.tap_stream_id: s for s in cls.catalog.streams}
        return cls.stream_map.get(stream_name)

    @classmethod
    def get_schema(cls, stream_name):
        stream = [s for s in cls.catalog.streams if s.tap_stream_id == stream_name][0]
        return stream.schema

    @classmethod
    def get_selected_streams(cls):
        selected_streams = []
        for stream in cls.catalog.streams:
            stream_metadata = stream.metadata
            for entry in stream_metadata:
                # Stream metadata will have an empty breadcrumb
                if not entry['breadcrumb'] and entry['metadata'].get('selected', None):
                    selected_streams.append((stream.tap_stream_id, stream.to_dict()))

        return selected_streams


def get_abs_path(path):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), path)


# Load schemas from schemas folder
def load_schemas():
    schemas = {}
    field_metadata = {}

    for filename in os.listdir(get_abs_path('schemas')):
        path = os.path.join(get_abs_path('schemas'), filename)
        stream_name = filename.replace('.json', '')
        with open(path) as file:
            schema = json.load(file)

        schemas[stream_name] = schema
        field_metadata[stream_name] = metadata.get_standard_metadata(schema=schema)

    return schemas, field_metadata


def get_report_type(schema_name):
    if schema_name in SALES_API_REQUEST_FIELDS:
        return ReportType.SALES
    elif schema_name == FINANCIAL_REPORT:
        return ReportType.FINANCE
    else:
        return None


def discover_catalog(api: Api):
    schemas, field_metadata = load_schemas()
    catalog = Catalog([])
    for schema_name, schema_dict in schemas.items():
        LOGGER.info("Discovering schema for %s", schema_name)

        try:
            schema = Schema.from_dict(schema_dict)
            mdata = field_metadata[schema_name]
        except Exception as err:
            LOGGER.error(err)
            LOGGER.error('schema_name: %s', schema_name)
            LOGGER.error('type schema_dict: %s', type(schema_dict))
            raise err

        if report_type := get_report_type(schema_name):
            report_date = datetime.strptime(get_bookmark(schema_name), "%Y-%m-%dT%H:%M:%SZ").strftime(
                "%Y-%m-%d" if report_type == ReportType.SALES else "%Y-%m")
            filters = get_api_request_fields(report_date, schema_name, report_type)
            report = _attempt_download_report(api, filters, report_type)
        else:
            raise Exception(f'Schema {schema_name} not found!')

        if report:
            # create and add catalog entry
            catalog_entry = CatalogEntry(
                stream=schema_name,
                tap_stream_id=schema_name,
                schema=schema,
                key_properties=[],
                metadata=mdata
            )
            catalog.streams.append(catalog_entry)

    if len(catalog.streams) == 0:
        LOGGER.warning("Could not find any reports types to download for the input configuration.")

    return catalog.to_dict()


def do_discover(api: Api):
    LOGGER.info("Running discover")
    catalog = discover_catalog(api)
    LOGGER.info("Completed discover")
    return catalog


def tsv_to_list(tsv):
    lines = tsv.split('\n')
    header = [s.lower().replace(' ', '_').replace('-', '_') for s in lines[0].split('\t')]
    data = []
    for line in lines[1:]:
        if len(line) == 0:
            continue
        line_obj = {}
        line_cols = line.split('\t')
        for i, column in enumerate(header):
            if i < len(line_cols):
                line_obj[column] = line_cols[i].strip()
        data.append(line_obj)

    return data


def get_api_request_fields(report_date, stream_name, report_type: ReportType) -> Dict[str, any]:
    """Get fields to be used in appstore API request """
    report_filters = {
        'reportDate': report_date,
        'vendorNumber': f"{Context.config['vendor']}"
    }
    if report_type == ReportType.SALES:
        api_fields = SALES_API_REQUEST_FIELDS.get(stream_name)
        if api_fields is None:
            raise Exception(f'API request fields not set to stream "{stream_name}"')
        else:
            report_filters.update(SALES_API_REQUEST_FIELDS[stream_name])
    return report_filters


def sync(api: Api):
    # Write all schemas and init count to 0
    for stream_name, catalog_entry in Context.get_selected_streams():
        singer.write_schema(stream_name, catalog_entry['schema'], catalog_entry['key_properties'])
        query_report(api, catalog_entry)


def _attempt_download_report(api: Api, report_filters: Dict[str, any], report_type: ReportType) -> Union[List[Dict], None]:
    # fetch data from appstore api
    try:
        rep_tsv = api.download_sales_and_trends_reports(filters=report_filters) if report_type == ReportType.SALES \
            else api.download_finance_reports(filters=report_filters)
    except APIError as e:
        LOGGER.error(e)
        return None

    # parse api response
    if isinstance(rep_tsv, dict):
        LOGGER.warning(f"Received a JSON response instead of the report: {rep_tsv}")
    else:
        return tsv_to_list(rep_tsv)

def query_report(api: Api, catalog_entry: Dict):
    stream_name = catalog_entry['tap_stream_id']
    stream_schema = catalog_entry['schema']

    # get bookmark from when data will be pulled
    bookmark = datetime.strptime(get_bookmark(stream_name), "%Y-%m-%dT%H:%M:%SZ").astimezone()
    delta = relativedelta(days=1)
    if stream_name == FINANCIAL_REPORT:
        bookmark = bookmark.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        delta = relativedelta(months=1)
    extraction_time = singer.utils.now().astimezone()
    iterator = bookmark
    singer.write_bookmark(
        Context.state,
        stream_name,
        'start_date',
        iterator.strftime(BOOKMARK_DATE_FORMAT)
    )

    with Transformer(singer.UNIX_SECONDS_INTEGER_DATETIME_PARSING) as transformer:
        while iterator + delta <= extraction_time:
            report_date = iterator.strftime("%Y-%m" if stream_name == FINANCIAL_REPORT else "%Y-%m-%d")
            LOGGER.info("Requesting Appstore data for: %s on %s", stream_name, report_date)
            # setting report filters for each stream
            if report_type := get_report_type(stream_name):
                report_filters = get_api_request_fields(report_date, stream_name, report_type)
                rep = _attempt_download_report(api, report_filters, report_type)
            else:
                raise Exception(f'Stream {stream_name} not found!')

            # write records
            for index, line in enumerate(rep, start=1):
                data = {
                    '_line_id': index,
                    '_time_extracted': extraction_time.strftime(TIME_EXTRACTED_FORMAT),
                    '_api_report_date': report_date,
                    **line
                }
                rec = transformer.transform(data, stream_schema)

                singer.write_record(stream_name, rec, time_extracted=extraction_time)

            singer.write_bookmark(
                Context.state,
                stream_name,
                'start_date',
                (iterator + delta).strftime(BOOKMARK_DATE_FORMAT)
            )

            singer.write_state(Context.state)
            iterator += delta

    singer.write_state(Context.state)


def get_bookmark(name):
    bookmark = singer.get_bookmark(Context.state, name, 'start_date')
    return bookmark or Context.config['start_date']


@utils.handle_top_exception(LOGGER)
def main():
    # Parse command line arguments
    args = utils.parse_args(REQUIRED_CONFIG_KEYS)

    Context.config = args.config
    api = Api(
        Context.config['key_id'],
        Context.config['key_file'],
        Context.config['issuer_id']
    )

    # If discover flag was passed, run discovery mode and dump output to stdout
    if args.discover:
        catalog = do_discover(api)
        Context.config = args.config
        print(json.dumps(catalog, indent=2))
    else:
        Context.tap_start = utils.now()
        Context.catalog = args.catalog if args.catalog else do_discover(api)
        Context.state = args.state
        sync(api)


if __name__ == '__main__':
    main()

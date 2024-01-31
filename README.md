# tap-appstore

This is a [Singer](https://singer.io) tap that produces JSON-formatted 
data following the [Singer spec](https://github.com/singer-io/getting-started/blob/master/SPEC.md) 
from App Store Connect API results.

Sample config:
```$json
{
  "key_id": "AAAAAAAAA",
  "key_file": "./AuthKey_AAAAAAAAA.p8",
  "issuer_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "vendor": "3333333",
  "start_date": "2019-02-01T00:00:00Z"
}
```

Optionally `key_file_str` can be used instead of `key_file`.
If `key_file_str` is provided it will be written to a temporary file and used as the key file, then later deleted on exit.
The input of that key must have new line characters `\n` for the line breaks in the key file contents.

An example could look like:

```$json
{
  "key_id": "AAAAAAAAA",
  "key_file_str": ".-----BEGIN PRIVATE KEY-----\nfoo\nbar\nbaz\nother\n-----END PRIVATE KEY-----",
  "issuer_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  "vendor": "3333333",
  "start_date": "2019-02-01T00:00:00Z"
}
```

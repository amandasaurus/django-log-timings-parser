# django-log-timings-parser

This Django app allows you to parse your apache logs, resolve them against your
django urls to match them against your views, and save that processed output to
a file.

You shoudl use this if you want to look at your server logs to see how fast or
slow your django application is, or how often certain views/URLs are/are not
being called.

## Quick Start

### Installation & Set up

It's on PyPI:

    pip install django-log-timings-parser

Add it to your installed apps:

    INSTALLED_APPS = 
        …
        'log_timings_parser',
        …
    )

### Example Usage

    python manage.py parse_apache_logs -o ~/current-logs /var/log/apache2/


This produces a TSV (Tab Separated Values) file ``~/current-logs``, of this sort of format:

    GET	/media/js/jquery.js	django.views.static.serve	{"args": [], "kwargs": {"path": "js/jquery.js", "document_root": "/path/to/project"}}	2013-10-01T13:11:58	752	127.0.0.1

i.e.:

    HTTP_METHOD URL_REQUESTED   DJANGO_VIEW_NAME    JSON_ENCODED_ARGS_KWARGS    ISO_FORMATTED_DATETIME  TIME_TO_SERVE_REQUEST_IN_MICROSEC   REMOTE_IP

It will recursively try to parse all the files in ``/var/log/apache2/``, optionally gunzipping files if it needs to, and produce one line of output for each line it can decode.

## Details

### Custom log format



## TODO

This currently says "apache" all over the place. It should work for other
webservers that use the apache log formats. It should be investigated to
confirm that this works with other servers.

## Copyright

The version numbers follow [Semantic Versioning](http://semver.org/). This
package is © 2013 Rory McCann, released under the terms of the GNU GPL v3 (or
at your option a later version).

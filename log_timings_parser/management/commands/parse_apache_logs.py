from django.core.urlresolvers import resolve
from django.core.management.base import BaseCommand, CommandError
from django.http import Http404
from optparse import make_option
from django.conf import settings

import random
import os.path, os
import gzip, inspect
import json

import apache_log_parser

import mock

def files(base):
    """
    Given a list of either filenames or directories, return (as a
    generator), all the files in that list, or walk the directory yielding
    filenames you see
    """
    for part in base:
        if os.path.isfile(part):
            yield part
        elif os.path.isdir(part):
            for dirpath, dirname, filenames in os.walk(part):
                random.shuffle(filenames)
                for filename in filenames:
                    yield os.path.join(dirpath, filename)

def open_anything(filename):
    """
    yield stripped lines from filename, automatically detects & properly opens a gzip file
    """
    if filename.endswith(".gz"):
        fp = gzip.open(filename)
        for line in fp.readlines():
            line = line.strip()
            yield line
        fp.close()
    else:
        with open(filename) as fp:
            for line in fp.readlines():
                line = line.strip()
                yield line

def parse_url_and_time(base, format):
    """
    Given a list of files/directories, parse each line with apache-log-parser, and
    extract the URL and time data and yield that.
    """
    parser = apache_log_parser.make_parser(format)

    for filename in files(base):

        for line in open_anything(filename):
            try:
                match = parser(line)
            except apache_log_parser.LineDoesntMatchException as ex:
                # Ignore it
                pass

            else:
                # Extract matching data from regex
                results = { 'url': match['request_url'], 'microsec': int(match['time_us']),
                            'method': match['request_method'], 'ipaddr': match['remote_host'],
                            'datetime': match['time_recieved_isoformat'] }

                yield results

class Command(BaseCommand):
    option_list  = BaseCommand.option_list + (
        make_option( '-i', '--input-source', action='append', default=[], help="Input source (file or directory)" ),
        make_option( '-o', '--output', '--output-file', help="Filename to store the (gzipped) results", dest='output_file'),
        make_option( '-f', '--format', help="Apache log format" ),
        make_option( '-p', '--patch-out', action="append", default=[], help="Decorator to patch/mock out" ),
        make_option( '-s', '--setting', action='append', default=getattr(settings, 'LOG_TIMINGS_PARSER_CUSTOM_SETTINGS', []), nargs=2, help="Custom settings value (-s ATTR VALUE) to override"),
        make_option( '-z', '--zip', action='store_true', default=False, help="gzip output file"),
        make_option( '-F', '--output-format', choices=['tsv', 'json'], help="Output format. Valid choices: tsv (default), json", default='tsv'),
    )


    # URLs we've seen already, cache what the resolve to so we speed it up
    cached_urls = {}

    # URLs we've seen already that we know are bad, don't bother trying to match
    # these
    bad404_urls = set()

    # These are URL names that have 'decorator' or 'decorators' in the module path. When we see one
    # we tell the user. Keep track so we only tell them once per decorator
    possible_decorators = set()

    def resolve_url_using_all_known_methods(self, url):
        """Try to parse the URL using all known tricks that can mangle it up"""
        resolved_url = None

        if url.startswith("//"):
            url = url[1:]
        
        resolved_url = self.resolve_url(url)

        if resolved_url is None:
            # it often has problems with GET params, so ignore them
            new_url = url.split("?")[0]
            resolved_url = self.resolve_url(new_url)

        return resolved_url

    def resolve_url(self, url):
        """
        Given a URL, try to resolve it to a django view using the Django url
        resolver

        Also does some caching of results using cached_urls and remembers what URLs
        don't resolve so it's faster
        """

        if url in self.bad404_urls:
            return None

        try:
            # Have we seen this URL before?
            return self.cached_urls[url]
        except KeyError:
            # Nope
            try:
                # Try the Django URL resolver
                resolved_url = resolve(url)
                assert resolved_url.url_name is not None  # Sanity check
                url_name = resolved_url.url_name
                # Later versions of python will have a fully qualified name, which would be nice
                func_name = resolved_url.func.__module__ + "." + resolved_url.func.__name__

                # Is it a decorator? if so tell user
                # FIXME this will sometimes be printed twice, if you have 2 URLs which use one decorator....
                possible_decorator = any(part in ['decorator', 'decorators'] for part in url_name.split(".")) or any(part in ['decorator', 'decorators'] for part in func_name.split("."))
                if possible_decorator:
                    if url_name not in self.possible_decorators or func_name not in self.possible_decorators:
                        filename = inspect.getfile(resolved_url.func)
                        lineno = resolved_url.func.func_code.co_firstlineno
                        self.stdout.write("Possible decorator!\n    named {url_name} for inner function {func_name}\n    (defined in {filename} line {lineno})\n    for URL {url}\n    Either use functools.wraps on your decorator\n    or find the decorator name and patch it out (--patch-out CLI arg or settings.LOG_TIMINGS_PARSER_PATCH_OUT)".format(url_name=url_name, func_name=func_name, url=url, lineno=lineno, filename=filename))
                        self.possible_decorators.add(url_name)
                        self.possible_decorators.add(func_name)

                self.cached_urls[url] = resolved_url
                return resolved_url

            except Http404:
                self.bad404_urls.add(url)
                return None


    def handle(self, *args, **options):
        output_file = options['output_file']
        if output_file is None:
            raise CommandError("Must provide an output file with -o/--output-file")

        apache_log_files_location = list(options['input_source']) + list(args)
        if len(apache_log_files_location) == 0:
            raise CommandError("Must provide a location of log files to parse, as extra arguments to this command")

        apache_format = settings.LOG_TIMINGS_PARSER_LOG_FORMAT
        if options['format']:
            apache_format = options['format']

        if apache_format is None:
            raise CommandError("Must provide what the apache log format is, either with settings.LOG_TIMINGS_PARSER_LOG_FORMAT or -f/--format option")

        if options['zip']:
            function_to_open = gzip.open
        else:
            function_to_open = open

        self.patch_out_decorators(options['patch_out'])
        self.overrride_settings(options['setting'])

        with function_to_open(output_file, 'w') as results:
            # generator
            urls = self.urls(apache_log_files_location, apache_format)

            if options['output_format'] == 'tsv':
                for url in urls:
                    try:
                        url['url_arguments'] = json.dumps(url['url_arguments'])
                    except TypeError:
                        url['url_arguments'] = None

                    results.write("{method}\t{url}\t{url_name}\t{url_arguments}\t{datetime}\t{microsec}\t{ipaddr}\n".format(**url))

            elif options['output_format'] == 'json':

                json.dump({'logs': list(urls)}, results)

            else:
                raise ValueError


    def patch_out_decorators(self, extra_from_cli):
        self.patchers = []
        for decorator_to_patch_out in getattr(settings, 'LOG_TIMINGS_PARSER_PATCH_OUT', []) + extra_from_cli:
            def _passthrough(func):
                return func

            patch = mock.patch(decorator_to_patch_out, new=_passthrough)
            patch.start()
            self.patchers.append(patch)

    def overrride_settings(extra_settings):
        # Manually change settings values for this run. Usually you want it to
        # match what's on the server whose logs you are parsing.
        for key, value in extra_settings:
            setattr(settings, key, value)



    def urls(self, apache_log_files_location, apache_format):

        # Read in log files
        for result in parse_url_and_time(apache_log_files_location, apache_format):

            url = result['url']

            resolved_url = self.resolve_url_using_all_known_methods(url)

            if resolved_url is None:
                # Don't know about this URL, skip it
                continue

            if url == '/server-status':
                # Apache server status call, handled by apache, so it isn't actually handled by our django, so you'll get a useless 404
                continue

            # If this resolved url has an app name, include that. This makes
            # django admin urls say "admin.index" rather than "index"
            result['url_name'] = (resolved_url.app_name+"." if resolved_url.app_name else '') + resolved_url.url_name

            result['url_arguments'] = {'args': resolved_url.args, 'kwargs': resolved_url.kwargs}
            
            yield result


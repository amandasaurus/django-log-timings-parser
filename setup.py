#! /usr/bin/env python

from setuptools import setup, find_packages


setup(name="django-log-timings-parser",
      version="1.0.0",
      author="Rory McCann",
      author_email="rory@technomancy.org",
      packages=['log_timings_parser'],
      license = 'GPLv3',
      description = 'Parses your web server access logs, resolves your URLs against your django project, and tells you what URLs take a long time',
      install_requires=[
        'django',
        'apache-log-parser',
        'mock',
    ],
)

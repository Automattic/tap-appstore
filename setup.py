#!/usr/bin/env python

from setuptools import setup

setup(name='tap-appstore',
      version='0.3.4',
      description='Singer.io tap for extracting data from the App Store Connect API',
      author='JustEdro',
      url='https://github.com/JustEdro',
      classifiers=['Programming Language :: Python :: 3 :: Only'],
      py_modules=['tap-appstore'],
      install_requires=[
          'singer-python==5.13.0',
          'appstoreconnect==0.10.1',
          'pytz==2023.3',
          'python-dateutil>=2.8.2,<3.0.0',
          'tenacity==8.2.3'
      ],
      extras_require={
        "dev": [
            "pytest<8.0.0",
        ]
      },
      entry_points='''
          [console_scripts]
          tap-appstore=tap_appstore:main
      ''',
      packages=['tap_appstore'],
      package_data={
          'tap_appstore/schemas': [
              'summary_sales_report.json'
          ],
      },
      include_package_data=True,
      )

# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

version = '1.0.0'


setup(
    name='senaite.sync',
    version=version,
    description="SENAITE SYNC",
    long_description="Changelog\n" +
                     "=========\n" +
                     open("docs/Changelog.rst").read() + "\n" +
                     "\n\n" +
                     "Authors and maintainers\n" +
                     "-----------------------\n\n" +
                     "- Ramon Bartl (RIDING BYTES) <rb@ridingbytes.com>",
    # Get more strings from
    # http://pypi.python.org/pypi?:action=list_classifiers
    classifiers=[
        "Programming Language :: Python",
        "Framework :: Plone",
        "Framework :: Zope2",
    ],
    keywords='',
    author='SENAITE Foundation',
    author_email='hello@senaite.com',
    url='https://github.com/senaite/senaite.sync',
    license='GPLv3',
    packages=find_packages('src', exclude=['ez_setup']),
    package_dir={'': 'src'},
    namespace_packages=['senaite'],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'setuptools',
        'senaite.api',
        'senaite.jsonapi',
        'requests',
    ],
    extras_require={
        'test': [
            'Products.PloneTestCase',
            'Products.SecureMailHost',
            'plone.app.testing',
            'robotsuite',
            'unittest2',
        ]
    },
    entry_points="""
      # -*- Entry points: -*-
      [z3c.autoinclude.plugin]
      target = plone
      """,
)

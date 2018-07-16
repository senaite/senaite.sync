# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

version = '1.0.1'


setup(
    name='senaite.sync',
    version=version,
    description="SENAITE SYNC",
    long_description=open("README.rst").read() + "\n" +
                     open("CHANGES.rst").read() + "\n" +
                     "\n\n" +
                     "Authors and maintainers\n" +
                     "-----------------------\n\n" +
                     "- Nihad Mammadli\n" +
                     "- Ramon Bartl (RIDING BYTES) <rb@ridingbytes.com>\n" +
                     "- Juan Gallostra (naralabs) <jgallostra@naralabs.com>",
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
        'plone.api',
        'souper',
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

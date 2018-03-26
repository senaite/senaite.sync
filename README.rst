.. figure:: https://raw.githubusercontent.com/senaite/senaite.sync/master/static/logo.png
   :height: 64x
   :alt: senaite.core
   :align: center

— **SENAITE.SYNC**: *Synchronization Solution to migrate data between two SENAITE instances*

Introduction
============

SENAITE.SYNC is a Synchronization Solution to migrate data between two SENAITE instances or from a BIKA instance to a SENAITE instance. Currently it only supports migration and not synchronization. 


Installation
============

In order to get SENAITE.SYNC running properly both `senaite.api` and `senaite.jsonapi` are required in the source and destination instances. However, `senaite.sync` is only required in the destination instance (where the data is to be imported).

To install SENAITE SYNC, you simply have to add `senaite.sync` into the `eggs` section
of your `buildout.cfg`:

    eggs =
      ...
      senaite.sync


Importing data
==============

Once SEANITE SYNC has been installed and the instance is up and running navigate to SENAITE SYNC's view by adding `/sync` after the base url of the instance.

The migration process mainly consists of three steps. 

1. Prepare the two instances involved in the synchronization process
2. Connect to the source instance and fetch its data into the destination instance. By the end of this step the destination instance will know which are the objects from the source instance that have to be created and its relations.
3. Import the data. This is the step that creates, in the destination instance, the objects from the source instance and its relationships in the destination instance. 


Contribute
==========

We want contributing to SENAITE.SYNC to be fun, enjoyable, and educational for
anyone, and everyone. This project adheres to the `Contributor Covenant <https://github.com/senaite/senaite.sync/blob/master/CODE_OF_CONDUCT.md>`_.
By participating, you are expected to uphold this code. Please report
unacceptable behavior.

Contributions go far beyond pull requests and commits. Although we love giving
you the opportunity to put your stamp on SENAITE.SYNC, we also are thrilled to
receive a variety of other contributions. Please, read `Contributing to senaite.sync
document <https://github.com/senaite/senaite.sync/blob/master/CONTRIBUTING.md>`_.


Feedback and support
====================

* `Gitter channel <https://gitter.im/senaite/Lobby>`_
* `Users list <https://sourceforge.net/projects/senaite/lists/senaite-users>`_


License
=======

SENAITE.CORE
Copyright (C) 2018 Senaite Foundation

This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License version 2 as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

SENAITE.SYNC uses third party libraries that are distributed under their own terms (see LICENSE-3RD-PARTY.rst)


Changelog
=========

1.0.1 (unreleased)
------------------

**Added**


**Changed**


**Removed**


**Fixed**

- #62 Use full url for images in README so that they are shown on PyPi's project page

**Security**



1.0.0 (2018-07-16) 
------------------

**Added**

- #58 Include detailed installation instructions in the README
- #58 Include functional documentation in the README
- #56 Allow to specify the certificate to be used when connecting to the source instance
- #46 Advanced Configuration: Local Prefix and Update only Content Types
- #44 Advanced Configuration: 'Read-Only' Portal Types
- #42 New Advanced Configuration Options
- #34 Complement step for migration
- #33 Recover step for failed objects in data import
- #32 Log the estimated date of end
- #32 Log the percentage of completion
- #19 Configurable import
- #16 Content type filtering
- #14 Upgrade step machinery
- #12 Settings import
- #8 Periodic auto sync
- #5 Import review history og objects
- #4 Update object's workflow states
- #3 Registry import

**Changed**

- #49 Make interface more user friendly
- #53 Update API base url
- #43 Querying last modified objects directly from 'uid_catalog'

**Fixed**

- #57 Handle errors in API resonse when fetching data
- #50 Long term infinite loops in Update Step
- #48 Auto Synchronization
- #45 Error while Fetching Missing Parents
- #39 Complement Step does not update all objects
- #35 Bug- Complement Step yields all the items
- #35 Complement Step yields all the items
- #29 User creation when user email is empty
- #28 Created users not being added to user groups
- #27 Worksheet's analysis workflow state not being updated properly
- #26 Clicking checkboxes' labels didn't affect their respective checkboxes
- #25 Import error when folderish content type in source has been removed in destination
- #24 Sync view wasn't properly rendered when not using `senaite.lims` add-on
- #22 Creation flag wasn't being unset for objects under Bika Setup
- #21 Attachments were not imported
- #6 ProxyField setter fails when proxy object has not been set yet


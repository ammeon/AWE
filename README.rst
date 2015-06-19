Overview
========

The Ammeon Workflow Engine (AWE) uses a workflow, a file containing a series of tasks that are grouped into categories (or phases), to define and execute the steps needed to perform operations on the servers in a deployment. AWE is designed to simplify the complex steps involved in managing a solution (for example,
performing upgrades or other maintenance tasks) across multiple servers.

The tasks to be performed on a deployment are broken down into steps and the dependencies between those steps are controlled using a template workflow file. The AWE runs the workflow file against a hosts file, which identifies the hosts used in a particular deployment. It then runs the steps required (on remote servers or locally) to perform the required tasks. Both Linux and Solaris distributions are supported.

For further information on AWE, please see the AWE Overview at http://www.ammeon.com/service/service-upgrade-orchestration-with-ammeon-workflow-engine/ or contact awe-support@ammeon.com.


Dependencies
============
AWE has been tested on Python 2.6, and requires the following libraries. In brackets are the versions that it has been verified against (however it may be compatible with other versions):

1. Fabric (1.10.1)
2. paramiko (1.12.4)
3. pycrypto (2.6.1)
4. lxml (2.2.8)
5. ecdsa (0.11)
6. ctypes (1.1.0)
7. argparse (1.3.0)


Install AWE
===========

1. AWE runs on both Solaris and Linux, however the install scripts provided will only work on Solaris.
2. AWE works from a AWE_HOME directory, so prior to beginning the installation set AWE_HOME environment variable to point to the location that you wish AWE to be installed to.  AWE will create a cfg, xsd, log, license, etc directories for input files and logs. The wfeng package that comprises AWE, will be deployed to the lib/wfeng directory under AWE.
3. If you wish AWE to be run by a different user to root, then set AWE_USER to the user to be run from.
4. Run bash install.sh to install AWE
5. Set an alias wfeng to point to <AWE_HOME>/lib/workfloweng.py if the install hasn't set one up for you
6. Test the install with: wfeng -h
7. The install will contain an example workflow and hosts file.

AWE directory structure
=======================
The following structure under AWE_HOME is created, further details on the files can be found in the AWE User Guide:

1. cfg - in here resides wfeng.cfg (AWE configuration file) and wfeng.ini (default INI file)
2. etc - normal location for workflow template, hosts file and master status file
3. lib - the AWE source
4. license - the AWE license files
5. log - the log from AWE runs
6. xsd - the XSD for the workflow and hosts file

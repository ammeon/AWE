Overview
========

The Ammeon Solutions Workflow Engine (AWE) uses a workflow, a file containing a series of tasks that are grouped into categories (or phases), to define and execute the steps needed to perform operations on the servers in a deployment. AWE is designed to simplify the complex steps involved in managing a solution (for example,
performing upgrades or other maintenance tasks) across multiple servers.

The tasks to be performed on a deployment are broken down into steps and the dependencies between those steps are controlled using a template workflow file. The AWE runs the workflow file against a hosts file, which identifies the hosts used in a particular deployment. It then runs the steps required (on remote servers or locally) to perform the required tasks. Both Linux and Solaris distributions are supported.

For further information on AWE, please see the AWE Overview at https://www.ammeonsolutions.com/workflow-engine or contact consulting@ammeonsolutions.com.

Supported Platforms
============

Some of the distributions AWE has been verified on are listed below:

1. CentOS 8 (with python 2.7)
2. CentOS 7
3. Ubuntu 16.04.6 LTS (Xenial Xerus)
4. Solaris 11
5. Solaris 10
6. Scientific Linux 6.4

Dependencies
============
AWE has been tested on Python 2.6 and Python 2.7, and requires the following libraries. In brackets are some of the versions that AWE has been verified against:

1. Fabric (1.10.1, 1.14.1)
2. paramiko (1.12.4, 2.7.1)
3. pycrypto (2.6.1)
4. lxml (2.2.8, 4.5.1)
5. ecdsa (0.11, 0.15)
6. ctypes (1.1.0). NB. This is bundled with some releases
7. argparse (1.3.0, 1.4.0)
8. setuptools (3.4.4, 0.9.8)


A pip requirements file is included which can be used on deployments where ctypes is bundled with python.

The above dependencies must be installed before running the installation script.

Install AWE
===========
1. AWE runs on both Solaris and Linux with python 2.6 and python 2.7, and the install.sh script provided will work on both.
2. AWE works from a AWE_HOME directory, so prior to beginning the installation set AWE_HOME environment variable to point to the location that you wish AWE to be installed to.  AWE will create a cfg, xsd, log, license, etc directories for input files and logs.  The wfeng package that comprises AWE, will be deployed to the lib/wfeng directory under AWE.  If a different directory structure is required then python setup.py install can be used instead.
3. Default installation steps:

   a. install python 2 (if not installed)
   b. ensure that GCC is installed, e.g. yum install gcc / apt install gcc
   c. ensure that python.h is installed, e.g. install python-devel/python2-devel on EL distributions, python-dev on Ubuntu, etc.
   d. install pip
   e. install python pre-requisites listed above using pip, e.g. pip install -r requirements.txt
   f. verify that ctypes is already installed, by testing "import ctypes" from the python command line
   g. set AWE_HOME to directory which to install AWE to
   h. set AWE_USER to the user that should own the AWE directories.
   i. Run 'install.sh' to install the AWE software. install.sh will install the AWE software, and set a wfeng alias in the user's profile.

      NB. If installed on CentOS8 then the python binary will be called python2.7, so the reference to python in install.sh will need to be replaced with python2.7

4. Set an alias wfeng to point to <AWE_HOME>/lib/workfloweng.py if the install hasn't set one up for you
5. Test the install with: wfeng -h


AWE directory structure
=======================
The following structure under AWE_HOME is created, further details on the files can be found in the AWE User Guide:

1. cfg - in here resides wfeng.cfg (AWE configuration file) and wfeng.ini (default INI file)
2. etc - normal location for workflow template, hosts file and master status file
3. lib - the AWE source
4. license - the AWE license files
5. log - the log from AWE runs
6. xsd - the XSD for the workflow and hosts file

from setuptools import setup
import distutils
import os
import shutil

class UninstallAWECommand(distutils.cmd.Command):
    """A custom command to uninstall AWE"""
    description = "uninstalls AWE"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass
    
    def run(self):
        """Run command"""
        if os.environ.get("AWE_HOME"):
            home = os.environ["AWE_HOME"]
            shutil.rmtree("{0}/lib/wfeng".format(home))
            shutil.rmtree("{0}/.lock".format(home))
            shutil.rmtree("{0}/xsd".format(home))
            os.remove("{0}/lib/workfloweng.py".format(home))
            os.remove("{0}/license/NOTICE.txt".format(home))
            os.remove("{0}/license/LICENSE.txt".format(home))

def get_version():
    version = 'UNKNOWN'
    version_file = open('RELEASE_INFO.txt')
    version = version_file.readline().split()[0]
    return version

myversion = get_version()

setup(name='AWE',
      description='Ammeon workflow engine',
      author='Ammeon',
      author_email='awe-support@ammeon.com',
      version=myversion,
      long_description="The Ammeon Workflow Engine (AWE) uses a workflow, " \
                        "a file containing a series of tasks that are " \
                        "grouped into categories (or phases), to define " \
                        "and execute the steps needed to perform operations " \
                        "on the servers in a deployment. AWE is designed to " \
                        "simplify the complex steps involved in managing a " \
                        "solution (for example, performing upgrades or other " \
                        "maintenance tasks) across multiple servers.",

      license="Apache 2.0",
      packages=['wfeng'],
      scripts=['workfloweng.py'],
      install_requires=['fabric','paramiko','lxml','ctypes','argparse','pycrypto','ecdsa'],
      keywords="workflow engine orchestration",
      data_files=[("cfg",['cfg/wfeng.cfg']),
                  ("cfg",['cfg/wfeng.ini']),
                  ("xsd",['xsd/workflow.xsd']),
                  ("xsd",['xsd/hosts.xsd']),
                  ("bin/wfeng",['uninstall.sh','install_common_functions.lib','solaris_def.lib','generic_def.lib','setup.py','RELEASE_INFO.txt']),
                  ("",['RELEASE_INFO.txt']),
                  ("license",['license/LICENSE.txt']),
                  ("license",['license/NOTICE.txt']),
                  (".lock",['.empty']),
                  ("etc",['.empty']),
                  ("log",['.empty'])],
      cmdclass={'uninstall':UninstallAWECommand}

     )

""" Plugin manager class, allows the ability to configure in the wfeng.cfg
    a configurable function for performing version checks
    An example version check function is provided in the
    plugins/sequenceverplugin.py
    @copyright: Ammeon Ltd
"""
from wfeng import constants
import os
import sys
import logging
import inspect

log = logging.getLogger(__name__)

# constants for software types
OS = "OS"
SW = "SW"


class PluginMgr:

    def __init__(self):
        """ Initialises plugin manager with no version check method"""
        self.custom_osversion_check = None
        self.custom_swversion_check = None

    def load_swplugin(self, pluginmodule):
        """ Loads software version plugin

            Args:
                pluginmodule: Name of module to load (without .py)
            Returns:
                boolean: True if managed to load plugin
        """
        return self.__load_plugin(pluginmodule, SW)

    def load_osplugin(self, pluginmodule):
        """ Loads OS version plugin

            Args:
                pluginmodule: Name of module to load (without .py)
            Returns:
                boolean: True if managed to load plugin
        """
        return self.__load_plugin(pluginmodule, OS)

    def __load_plugin(self, pluginmodule, type):
        """ Loads version plugin

            Args:
                pluginmodule: Name of module to load (without .py)
            Returns:
                boolean: True if managed to load plugin
        """
        if pluginmodule == None or len(pluginmodule) == 0:
            log.debug("No plugin module to load")
            return True
        log.debug("Setting version plugin to " + pluginmodule)
        try:
            mod = __import__(pluginmodule, fromlist=[''])
            # Prove function exists, attributeerror raised if not
            tempfunc = mod.compare_version
            # Prove that expects 2 args
            argspec = inspect.getargspec(mod.compare_version)
            if len(argspec.args) != 2:
                log.error("compare_version function in module " +
                      "%s does not take two arguments" % pluginmodule)
                return False
            if type == SW:
                self.custom_swversion_check = mod.compare_version
            elif type == OS:
                self.custom_osversion_check = mod.compare_version
            else:
                log.error("Invalid version check type: " + type)
                return False
        except AttributeError:
            log.error("plugin does not have a compare_version function" + \
                  pluginmodule)
            return False
        except ImportError:
            log.error("Unable to import module " + \
                  pluginmodule)
            return False
        return True

    def check_swversion(self, version_req, current_version):
        """ Calls custom plugin version checker if provided

            Args:
                version_req: Version that want to be at
                current_version: Current version of node
            Returns:
                True if current_version >= version_req
                False otherwise
            Raises:
                ValueError: if version is in unsupported format"""
        return self.__check_version(version_req, current_version, SW)

    def check_osversion(self, version_req, current_version):
        """ Calls custom plugin version checker if provided

            Args:
                version_req: Version that want to be at
                current_version: Current version of node
            Returns:
                True if current_version >= version_req
                False otherwise
            Raises:
                ValueError: if version is in unsupported format"""
        return self.__check_version(version_req, current_version, OS)

    def __check_version(self, version_req, current_version, type):
        """ Calls custom plugin version checker if provided

            Args:
                version_req: Version that want to be at
                current_version: Current version of node
                type: type of version to check
            Returns:
                True if current_version >= version_req
                False otherwise
            Raises:
                ValueError: if version is in unsupported format"""

        # Default handling of None
        if current_version == None:
            return False
        if version_req == None:
            return True
        # Now call custom or exact match
        if type == SW:
            if self.custom_swversion_check == None:
                return (current_version == version_req)
            else:
                return self.custom_swversion_check(version_req,
                                                   current_version)
        elif type == OS:
            if self.custom_osversion_check == None:
                return (current_version == version_req)
            else:
                return self.custom_osversion_check(version_req,
                                                   current_version)
        else:
            log.error("Invalid version comparision type: " + type)
            raise ValueError("Invalid version comparison type: " + type)

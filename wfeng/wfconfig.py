"""Settings that are set by wfeng.cfg or via menu
@copyright: Ammeon Ltd
"""
import os
import logging
from wfeng import constants


# Special output strings so that scripts can summarise error to display
# Below are the keys to access the cfg dictionary
# Keys to identify lines of interest in stdout
DISPLAY_ERR = "DISPLAY_ERR"
PRECHECK_ERR = "PRECHECK_ERR"
POSTCHECK_ERR = "POSTCHECK_ERR"
EXECUTE_ERR = "EXECUTE_ERR"
DISPLAY_INFO = "DISPLAY_INFO"
PRECHECK_INFO = "PRECHECK_INFO"
POSTCHECK_INFO = "POSTCHECK_INFO"
EXECUTE_INFO = "EXECUTE_INFO"
#Keys to identify values in the DISPLAY_INFO line that indicate version and
#type
SWVER = "SWVER"
OSVER = "OSVER"
TYPE = "TYPE"
# Special keyword to indicate unknown version
UNKNOWN = "UNKNOWN"

#Variable that indicates want to set local variables
SETVAR = "SETVAR"

log = logging.getLogger(__name__)


class WfmgrConfig(object):
    """ Represents config class"""

    def __init__(self):
        # load with initial values
        self.cfg = {}
        self.cfg[DISPLAY_ERR] = "DISPLAY_NOTICE:"
        self.cfg[PRECHECK_ERR] = "PRECHECK_NOTICE:"
        self.cfg[POSTCHECK_ERR] = "POSTCHECK_NOTICE:"
        self.cfg[EXECUTE_ERR] = "EXECUTE_NOTICE:"
        self.cfg[DISPLAY_INFO] = "DISPLAY_INFO:"
        self.cfg[PRECHECK_INFO] = "PRECHECK_INFO:"
        self.cfg[POSTCHECK_INFO] = "POSTCHECK_INFO:"
        self.cfg[EXECUTE_INFO] = "EXECUTE_INFO:"
        self.cfg[SETVAR] = "SETVAR:"
        self.cfg[SWVER] = "SWVERSION"
        self.cfg[OSVER] = "OSVERSION"
        self.cfg[TYPE] = "TYPE"
        self.cfg[UNKNOWN] = "UNKNOWN"
        self.iniparams = {}

    def load(self):
        filename = constants.CFG_FILE
        if os.path.isfile(filename):
            with open(filename) as cfgfile:
                for line in cfgfile:
                    name, var = line.partition("=")[::2]
                    self.cfg[name.strip()] = var.strip()
            log.debug("wfeng.cfg located and loaded: {0}".format(self.cfg))
        else:
            log.debug("No wfeng.cfg to load")

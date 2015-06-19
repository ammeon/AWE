"""Constants to be used within AWE
@copyright: Ammeon Ltd
"""
import os

#Special keyword to indicate run on local server
LOCAL = "LOCAL"

#Special keyword to indicate run on all servers
ALL = "*"

# Level for tracing for logging
TRACE = 5
# Level for debug with no time
DEBUGNOTIME = 11
INFONOTIME = 21
ERRORNOTIME = 41

#locations
WFENG_ROOT = os.path.abspath(os.path.join(__file__, '../../..'))
WORKFLOW_XSD = "{0}/xsd/workflow.xsd".format(WFENG_ROOT)
HOSTS_XSD = "{0}/xsd/hosts.xsd".format(WFENG_ROOT)
VERSION_FILE = "{0}/RELEASE_INFO.txt".format(WFENG_ROOT)
LOCK_DIR = "{0}/.lock".format(WFENG_ROOT)
INI_FILE = "{0}/cfg/wfeng.ini".format(WFENG_ROOT)
CFG_FILE = "{0}/cfg/wfeng.cfg".format(WFENG_ROOT)
LOG_DIR = "{0}/log".format(WFENG_ROOT)

# Phases in workflow.xml
DISPLAY = "display"
PRECHECK = "pre-check"
POSTCHECK = "post-check"
EXECUTE = "execute"

# states of tasks within phases
INITIAL = "INITIAL"
SUCCESS = "SUCCESS"
FAILED = "FAILED"
SKIPPED = "SKIPPED"
REACHED_VERSION = "REACHED_VERSION"
PARAM_NOTMATCH = "PARAM_NOTMATCH"
MANUAL_FIX = "MANUAL_FIX"


SUCCESS_STATUSES = [SUCCESS, REACHED_VERSION, MANUAL_FIX, PARAM_NOTMATCH]

#Running states
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"

# Phases as per command line
OPT_DISPLAY = "display"
OPT_PRECHECK = "precheck"
OPT_EXECUTE = "execute"
OPT_POSTCHECK = "postcheck"

# Spinner characters, TODO allow this to be configurable
SPINNER_CHARS = ["-", "|", "/", "\\ "]

# OUTPUT LEVELS
QUIET = 0
ERROR_ONLY = 1
ERROR_INFO = 2

# Colours

# suffix for --list output file
LISTFILE_SUFFIX = ".list"

# Vars that cannot be set in ini file
INI_RESERVED_VARS = ["SERVERNAME", "SERVERTYPE", "SERVERIP", "SWVERSION", "OSVERSION"]


class Colours:
    """ Class to represent the colours to use"""
    END = '\033[0m'

    status = {SUCCESS: '\033[92m',
              FAILED: '\033[91m',
              INITIAL: '\033[93m',
              REACHED_VERSION: '\033[92m',
              PARAM_NOTMATCH: '\033[92m',
              MANUAL_FIX: '\033[92m',
              SKIPPED: '\033[93m',
              RUNNING: '\033[94m',
              COMPLETED: END}

    host_colours = ['\033[33m', '\033[34m', '\033[35m', '\033[36m',
                    '\033[37m', '\033[95m', '\033[96m', '\033[38m;5;178m',
                    '\033[38m;5;185m']

COLOURS = Colours()

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
WFENG_ROOT = os.environ["AWE_HOME"]
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
MANUAL_RESET = "MANUAL_RESET"


SUCCESS_STATUSES = [SUCCESS, REACHED_VERSION, MANUAL_FIX, PARAM_NOTMATCH]
INIT_STATUSES = [INITIAL, MANUAL_RESET, SKIPPED]

# dynamic pause and escape types
DYNAMIC_ESCAPE = "ESCAPE"
DYNAMIC_PAUSE = "PAUSE"
DYNAMIC_ADD = "add"
DYNAMIC_REMOVE = "remove"
# position (relative to reference task id) for insertion of dynamic pause/esc
DYNAMIC_BEFORE = "before"
DYNAMIC_AFTER = "after"
# dynamic pause and escape fields
DYN_ACTION = "action"
DYN_TYPE = "dyntype"
DYN_POS = "pos"
DYN_REFID = "refid"
DYN_ID = "id"
DYN_MSG = "msg"
DYN_HOSTS = "hosts"
DYN_SERVER = "server"
DYN_DEP = "dep"
DYN_DEPSINGLE = "depsingle"
DYN_SWVER = "swver"
DYN_OSVER = "osver"
DYN_CHECKPARAMS = "checkparams"
# the following two vars flag whether a field is required or optional
FIELD_REQUIRED = True
FIELD_OPTIONAL = False

dynamicDefaults = {
    DYN_HOSTS: '*',
    DYN_SERVER: '*',
    DYN_DEP: None,
    DYN_DEPSINGLE: False,
    DYN_SWVER: None,
    DYN_OSVER: None,
    DYN_CHECKPARAMS: None
}

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
INI_RESERVED_VARS = ["SERVERNAME", "SERVERTYPE", \
                     "SERVERIP", "SWVERSION", "OSVERSION"]

# used in the dict returned by getTaskIndices
TASK_IN_GROUP = "group"
TASK_LIST = "tasklist"

DYNAMIC_ALTERATIONS_BKPDIR = "dynamic_alteration_backups"
MANUAL_RESET_BKPDIR = "manual_reset_backups"

#return codes for manual reset processing in processManualReset
R_OK = 0
R_DEPENDENCY_CONFLICT = 1
R_ERROR = 2


class Colours:
    """ Class to represent the colours to use"""
    END = '\033[0m'

    status = {SUCCESS: '\033[92m',
              FAILED: '\033[91m',
              INITIAL: '\033[93m',
              MANUAL_RESET: '\033[93m',
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

"""Modules represents top level manager class
@copyright: Ammeon Ltd
"""
import argparse
import logging
import os
import sys
import datetime
import traceback
import constants
from time import sleep
import threading
import multiprocessing

from workflow import Workflow
from wfini import WfengIni
from host import Hosts
from workflowsys import WorkflowSystem, WorkflowStatus
from wfconfig import WfmgrConfig
from inputmgr import MenuMgr
from task import FabricTask
import utils

log = logging.getLogger(__name__)


class WorkflowEngine:
    """The main class of the workflow manager."""
    def __init__(self):
        self.term_size = 80
        args = os.popen('stty -a', 'r').read().split(';')
        for x in args:
            x = x.strip().lstrip()
            if x.startswith("columns"):
                # Either split by = or ' '
                splitChar = ' '
                if '=' in x:
                    splitChar = '='
                k, v = x.split(splitChar)
                self.term_size = int(v)

    def deletePidFile(self):
        pid = str(os.getpid())
        if not os.path.exists(constants.LOCK_DIR):
            log.error("Lock directory does not exist")
            return
        filename = os.path.join(constants.LOCK_DIR, pid)
        if os.path.exists(filename):
            os.remove(filename)

    def getRunningPid(self, workfile, hostfile, specific=False):
        """ Gets the pid of wfeng that is still running.
            If specific is true then returns instance running with
            specified workfile and hostfile, else returns pid of
            any running wfeng
            Arguments:
                workfile - ignored unless specific is true
                hostfile - ignored unless specific is true
                specific - if True then return pid of wfeng instance that
                      is with this workfile/hostfile, else return pid
                      of any running wfeng
            Returns:
                list of pids that are running
            """
        pids = []
        files = os.listdir(constants.LOCK_DIR)
        # Find out what locks we have, each filename is name of pid
        # and contents are workfile, hostfile
        for filename in files:
            full_filename = os.path.join(constants.LOCK_DIR, filename)
            f = open(full_filename, "r")
            for line in f:
                args = line.rstrip().split(",")
                pid = None
                if len(args) == 2:
                    # Check well formatted line
                    if specific:
                        if workfile == args[0] and hostfile == args[1]:
                            pid = filename
                    else:
                        pid = filename
                if pid != None:
                    # This is pid of an instance of wfeng we care about
                    try:
                        os.kill(int(pid), 0)
                        # Pid is still running
                        pids.append(pid)
                        # This might be a pid of
                    except OSError:
                        # Pid nolonger running
                        pass
            f.close()
        return pids

    def alreadyRunning(self, workfile, hostfile, allowMultiple=False):
        """ Returns True if another instance is running"""
        absw = os.path.abspath(workfile)
        absh = os.path.abspath(hostfile)
        if len(self.getRunningPid(absw, absh, allowMultiple)) != 0:
            return True

        # Not currently running a clashing wfeng, create lockfile
        pid = str(os.getpid())
        self.writePid(pid, absw, absh)

        # Wait and check pid not altered, to ensure another process wasn't
        # started at same time as us
        # We aren't expecting multiple to be submitted within seconds of each
        # other, so this should suffice
        sleep(1)

        # Has anyone altered the pid for our parameters, invalid whether or
        # not allowMultipe is False
        pids = self.getRunningPid(absw, absh, True)
        if len(pids) != 1 or pids[0] != pid:
            return True

        # If allowMultiple is False, then we need to know the only running
        # instanceis us
        if not allowMultiple:
            pids = self.getRunningPid(absw, absh, False)
            if len(pids) != 1 or pids[0] != pid:
                # Not just our pid returned
                return True
        return False

    def writePid(self, pid, workfile, hostfile):
        """ Writes our pid to pid file"""
        if not os.path.exists(constants.LOCK_DIR):
            log.error("Lock directory does not exist")
            return
        filename = os.path.join(constants.LOCK_DIR, pid)
        file = open(filename, 'w')
        file.write("%s,%s\n" % (workfile, hostfile))
        file.close()

    def start(self):
        # Read in command line options
        o = WorkflowOptions()
        o.parse()
        if o.version:
            if os.path.exists(constants.VERSION_FILE):
                with open(constants.VERSION_FILE, 'r') as fin:
                    print fin.read()
            else:
                print "VERSION information was unavailable"
            return True
        FORMAT = '%(asctime)-15s %(message)s'
        # Find the filename bit of filename
        workfile = utils.get_file_less_ext(o.wfile)
        hostfile = utils.get_file_less_ext(o.hfile)
        starttime = datetime.datetime.now().strftime("%d%m%Y_%H%M%S")
        # Check if already running
        if self.alreadyRunning(o.wfile, o.hfile, o.allow_multiple):
            if o.allow_multiple:
                print "Exiting as instance of wfeng already running " + \
                      "with same hostfile and workfile"
            else:
                print "Exiting as instance of wfeng already running"
            return False
        self.logfilename = "%s/%s_%s_%s.log" %\
                         (constants.LOG_DIR, workfile, hostfile, starttime)
        self.tracefilename = "%s/%s_%s_%s.trc" %\
                         (constants.LOG_DIR, workfile, hostfile, starttime)
        logging.addLevelName(constants.TRACE, "TRACE")
        logging.addLevelName(constants.DEBUGNOTIME, "DEBUGNOTIME")
        logging.basicConfig(filename=self.tracefilename,
                            level=constants.TRACE,
                            format=FORMAT)
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        logging.getLogger('wfeng').addHandler(console)

        # Add debug handler
        debug = logging.FileHandler(self.logfilename)
        debug.setLevel(logging.DEBUG)
        formatter = WfengFormatter('%(asctime)s %(message)s')
        debug.setFormatter(formatter)
        logging.getLogger('wfeng').addHandler(debug)

        # Add handler for subprocesses
        self.logqueue = multiprocessing.Queue()
        subproc = SubProcessLogHandler(self.logqueue)
        subproc.setFormatter(formatter)
        subproc.setLevel(logging.DEBUG)
        logging.getLogger('sub.wfeng').addHandler(subproc)

        # Add thread to read from queue
        self.log_queue_reader = LogQueueReader(self.logqueue)
        self.log_queue_reader.start()

        self.config = WfmgrConfig()
        self.config.load()
        if not os.path.isfile(o.wfile):
            log.error("Workflow file %s does not exist" % o.wfile)
            return False
        if not os.path.isfile(o.hfile):
            log.error("Host file %s does not exist" % o.hfile)
            return False
        ini = WfengIni()
        # Load default
        if not ini.load():
            return False
        if o.inifile is not None:
            if not ini.load(o.inifile):
                return False
        self.config.iniparams = ini.vars
        if o.needMenu():
            o.getMenuOptions(self.term_size, self.config)
        os.system('clear')
        log.info("WORKFLOW ENGINE".center(self.term_size))
        log.info("----------------".center(self.term_size))
        log.info("\nOptions chosen:")
        log.info("    workflow: %s" % o.wfile)
        log.info("    hosts: %s" % o.hfile)
        log.info("    timeout: %s" % o.timeout)
        log.info("    phase: %s" % o.phase)
        log.info("    server types: %s" % o.servertype)
        log.info("    server name: %s" % o.servername)
        log.info("    excluded servers: %s" % o.exclude)
        log.info("    task id: %s" % o.task)
        log.info("    tag id: %s" % o.tag)
        log.info("    output level: %d" % o.output_level)
        if o.force:
            log.info("    force: True")
        if o.yes:
            log.info("    yes: True")
        if o.automate:
            log.info("    automate: True")
        if o.list:
            log.info("    list: True")
            # for listing then if phase and task are not specified we will run all phases
            if o.phase == None and o.task == None:
                log.info("All phases will be listed")
                o.phase="postcheck"
        if o.fix:
            log.info("    fix: True")
        hosts = Hosts()
        if not hosts.parse(o.hfile):
            return False
        # check here that any server in the exclusion list is found in the hosts file

        if o.exclude != None:
           excludes = []
           # Now strip of spaces
           excludes = [x.strip() for x in o.exclude.split(',')]
           for excludedServer in excludes:
                if not hosts.host_exists(excludedServer):
                    log.error(
                          "Excluded server %s is not in the hosts file %s" % \
                                 (excludedServer,o.hfile))
                    return False
        wf = Workflow(self.config)
        if not wf.parse(o.wfile):
            return False
        try:
            wfsys = wf.genWorkflowSystem(hosts)
        except Exception as err:
            log.error("Failed to generate workflow list: %s" % str(err))
            log.debug("Exception: %s" % (traceback.format_exc()))
            return False
        # validate servertype
        if o.servertype != constants.ALL and (not o.servertype in hosts.hosts):
            log.error("Server type %s selected is not in hosts file" % \
                                         o.servertype)
            return False
        # validate servername
        if o.servername != constants.ALL:
            if not hosts.host_exists(o.servername):
                log.error("Server name %s selected is not in hosts file" % \
                                           o.servername)
                return False
        # validate task is valid
        if o.task != None:
            if not wfsys.isValidTask(o.task):
                log.error("Task id %s selected is not in workflow file" % \
                                           o.task)
                return False
        # validate tag is valid
        if o.tag != None:
            if not wfsys.isValidTag(o.tag):
                log.error("Tag %s selected is not in workflow file" % \
                                           o.tag)
                return False
        # Validate fix task is FabricTask
        if o.fix:
            taskobj = wfsys.getTask(o.task)
            if not isinstance(taskobj, FabricTask):
                log.error("Fix is not supported on task %s" % \
                                   o.task)
                return False

        # Global status is in same directory as workfile, but appended with
        # hostname file and status.xml
        prefix = o.wfile.split('.xml')
        dirs = o.hfile.split("/")
        hostfile = dirs[len(dirs) - 1].split(".")[0]
        sysfilename = o.getSysStatusName()
        #flag for whether we are simply merging wflow and hosts and exiting at start of a --list run
        listExitEarly=False
        # Check if already got work file system
        if os.path.isfile(sysfilename):
            log.info("    previous run: %s" % sysfilename)
            loadsys = WorkflowSystem("", self.config)
            loadsys.load(sysfilename, hosts)
            if wfsys.isEquivalent(loadsys):
                log.debug("Previous run is equivalent to current files")
                wfsys = loadsys
            else:
                log.error("Workflow and/or hosts file has changed since previous run, please investigate")
                return False
        else:
            # if --list and there is no pre-existing workflow file then we generate a listing file and exit straight away
            if o.list:
                log.info("There is no pre-existing status file")
                listExitEarly=True
            else:
                log.info("    previous run: N/A")
                wfsys.write(sysfilename)
        # if --list then ascertain whether all eligible tasks are in a complete state
        if o.list and wfsys.eligibleDisplayTasks(o.servertype, o.servername, o.exclude,
                         o.force, o.exact_match):
            log.info("Display phase has not been completed and therefore later phases cannot be predicted")
            listExitEarly=True
        if listExitEarly:
            fnamesuffix=constants.LISTFILE_SUFFIX
            log.info("\nWorkflow file and hosts file have been merged to create list file %s%s, equivalent to a master status file" % (sysfilename, constants.LISTFILE_SUFFIX))
            wfsys.write("%s%s" % (sysfilename, constants.LISTFILE_SUFFIX))
            sys.exit(0)

        runner = CmdLineWorkflowRunner(wfsys, self.term_size, o)
        if o.list:
            log.info("\nListing has been run from the pre-existing master status file onwards, with predictive output written to file %s%s" % (sysfilename, constants.LISTFILE_SUFFIX))
        return runner.run()


class CmdLineWorkflowRunner:
    """ Runs a workflow, getting input as to whether to continue from
        command line"""
    def __init__(self, wfsys, term_size, options):
        self.wfsys = wfsys
        self.options = options
        self.term_size = term_size

    def run(self):
        finished = False
        success = False
        sysfilename = self.options.getSysStatusName()
        try:
            while not finished:
                status = self.wfsys.process(self.term_size, self.options)
                if self.options.list:
                    log.debug("Writing results of listing to %s%s" % (sysfilename, constants.LISTFILE_SUFFIX))
                    self.wfsys.write("%s%s" %(sysfilename, constants.LISTFILE_SUFFIX))
                else:
                    self.wfsys.write(sysfilename)

                if status.status == WorkflowStatus.USER_INPUT:
                    log.debug("Asking: %s" % status.user_msg)
                    if not self.wfsys.input.askContinue(status):
                        log.debug("Response indicates to stop")
                        finished = True
                        log.info("Stopping workflow as requested")
                    else:
                        log.debug("Response indicates to continue")
                elif status.status == WorkflowStatus.COMPLETE:
                    log.info(status.user_msg)
                    finished = True
                    success = True
                elif status.status == WorkflowStatus.FAILED:
                    log.error(status.user_msg)
                    finished = True
                else:
                    log.debug("Invalid status %s" % status.status)
        finally:
            # Write out resulting status
            if self.options.list:
                log.debug("Writing results of listing to %s%s" % (sysfilename, constants.LISTFILE_SUFFIX))
                self.wfsys.write("%s%s" %(sysfilename, constants.LISTFILE_SUFFIX))
            else:
                log.debug("Writing results of run to %s" % sysfilename)
                self.wfsys.write(sysfilename)

        return success


class WorkflowOptions:
    """Class for finding options needed"""
    def parse(self):
        "Parses command line for options"
        parser = argparse.ArgumentParser(description="Workflow engine")
        parser.add_argument("-w", "--workfile",
                            default="./workflow.xml",
                            help="Full path to workflow XML file")
        parser.add_argument("-H", "--hostfile",
                            default="./hosts.xml",
                            help="Full path to hosts XML file")
        parser.add_argument("-i", "--inifile",
                            help="Full path to INI file")
        parser.add_argument("-T", "--timeout",
                            default="10", type=int,
                            help="Network connection timeout in seconds")
        parser.add_argument("-p", "--phase",
               help="Phase to run: display, precheck, execute, postcheck")
        parser.add_argument("-s", "--servertype", default=constants.ALL,
                            help="Server type to run on")
        parser.add_argument("-n", "--servername", default=constants.ALL,
                            help="Name of server to run on")
        parser.add_argument("-g", "--tag",
                            help="Only run tasks in this tagged set")
        parser.add_argument("-e", "--exclude",
                    help="Comma separated names of server not to run on")
        parser.add_argument("-t", "--task",
                            help="ID of task to run")
        parser.add_argument("-f", "--force", action='store_true',
                    help=argparse.SUPPRESS)
        parser.add_argument("-c", "--compare_versions", action='store_true',
                    help=argparse.SUPPRESS)
        parser.add_argument("-l", "--list", action='store_true', default=False,
                    help=argparse.SUPPRESS)
        parser.add_argument("-F", "--fix", action='store_true', default=False,
                    help="Mark individual task as fixed")
        parser.add_argument("-v", "--version", action='store_true',
                    default=False,
                    help="Display version information")
        parser.add_argument("-N", "--nospinner", action='store_true',
                    default=False,
                    help=argparse.SUPPRESS)
        parser.add_argument("-m", "--allow-multiple", action='store_true',
                            default=False,
                    help=argparse.SUPPRESS)
        parser.add_argument("-o", "--output",
               help="Output Level, 0 - no tags, 1 - error tags, " + \
                    "2 - error and info tags")
        parser.add_argument("-y", "--yes", action='store_true',
                            help="Silently answer yes to all questions except pauses")
        parser.add_argument("-a", "--automate", action='store_true',
                            default=False,
                            help="Silently answer yes to all questions including pauses")
        args = parser.parse_args()
        self.version = args.version
        if args.version:
            return
        # Only specify one of servername or servertype
        if args.servername != constants.ALL and \
           args.servertype != constants.ALL:
            parser.error("Specify only one of servername or servertype")
        # check phase is valid
        if args.phase != None and args.phase != constants.OPT_DISPLAY and \
                args.phase != constants.OPT_PRECHECK and \
                args.phase != constants.OPT_EXECUTE and \
                args.phase != constants.OPT_POSTCHECK:
            parser.error("Invalid value for phase supplied")
        if args.task != None and args.phase != None:
            parser.error("At most one of phase and task may be supplied")
        if args.tag != None and args.task != None:
            parser.error("At most one of tag and task may be supplied")
        if args.list and args.fix:
            parser.error("At most one of list and fix may be supplied")
        if args.fix and args.task == None:
            parser.error("Task must be specified to use fix")
        if args.fix and args.servername == constants.ALL:
            parser.error("Servername must be specified to use fix")
        if args.output == None:
            self.output_level = 0
        else:
            try:
                self.output_level = int(args.output)
            except:
                parser.error("Output level must be numeric")
        if args.task != None and args.phase != None:
            parser.error("At most of one of phase and task may be supplied")
        self.wfile = args.workfile
        self.inifile = args.inifile
        self.hfile = args.hostfile
        self.timeout = args.timeout
        self.phase = args.phase
        self.servertype = args.servertype
        self.servername = args.servername
        self.exclude = args.exclude
        self.task = args.task
        self.force = args.force
        self.list = args.list
        self.fix = args.fix
        self.nospinner = args.nospinner
        self.allow_multiple = args.allow_multiple
        self.yes = args.yes
        self.automate = args.automate
        self.exact_match = True
        if args.compare_versions:
            self.exact_match = False
        self.tag = args.tag
        if self.task != None:
            self.phase = constants.OPT_POSTCHECK

    def needMenu(self):
        if self.phase == None and self.task == None and self.list != True:
            return True
        else:
            return False

    def getMenuOptions(self, term_size, config):
        menumgr = MenuMgr(term_size, config)
        if not menumgr.getOptions(self):
            sys.exit(0)

    def getSysStatusName(self):
        """ Calculates system filename for the status"""
        prefix = self.wfile.split('.xml')
        dirs = self.hfile.split("/")
        hostfile = dirs[len(dirs) - 1].split(".")[0]
        sysfilename = "%s_%s_status.xml" % (prefix[0], hostfile)
        return sysfilename


class SubProcessLogHandler(logging.Handler):
    """handler used by subprocesses
    It simply puts items on a Queue for the main process to log.
    """

    def __init__(self, queue):
        logging.Handler.__init__(self)
        self.queue = queue

    def emit(self, record):
        self.queue.put(record)


class LogQueueReader(threading.Thread):
    """thread to write subprocesses log records to main process log

    This thread reads the records written by subprocesses and writes them to
    the handlers defined in the main process's handlers.

    """

    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        self.daemon = True

    def run(self):
        """read from the queue and write to the log handlers

        """
        while True:
            try:
                record = self.queue.get()
                log.callHandlers(record)
            except (KeyboardInterrupt, SystemExit):
                raise
            except EOFError:
                break
            except:
                traceback.print_exc(file=sys.stderr)


class WfengFormatter(logging.Formatter):

    def __init__(self, fmt=None, datefmt=None):
        logging.Formatter.__init__(self, fmt, datefmt)

    def formatTime(self, record, datefmt=None):
        if record.levelno == constants.DEBUGNOTIME or \
           record.levelno == constants.INFONOTIME or \
           record.levelno == constants.ERRORNOTIME:
            return ""
        else:
            return logging.Formatter.formatTime(self, record, datefmt)

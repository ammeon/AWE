"""Modules represents top level manager class
@copyright: Ammeon Ltd """
import argparse
import logging
import os
import sys
import datetime
import traceback
from wfeng import constants
from time import sleep
import threading
import multiprocessing
import signal

from wfeng.workflow import Workflow
from wfeng.wfini import WfengIni
from wfeng.host import Hosts
from wfeng.workflowsys import WorkflowSystem
from wfeng.status import WorkflowStatus
from wfeng.wfconfig import WfmgrConfig, SWVERSIONPLUGIN, OSVERSIONPLUGIN
from wfeng.wfconfig import EXTRA_LOGPARAMLIST, EXTRA_LOGPARAM
from wfeng.inputmgr import MenuMgr, DynamicMenuMgr
from wfeng.task import FabricTask
from wfeng import utils
from wfeng.engformatter import WfengFormatter
from wfeng.msgtask import EscapeTask, PauseTask, DynamicTaskValidator, MsgTask
from wfeng.pluginmgr import PluginMgr

log = logging.getLogger(__name__)


class WorkflowEngine:
    """The main class of the workflow manager."""
    def __init__(self):

        self.dynamicTaskValidator = DynamicTaskValidator()
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

            Args:
                workfile: ignored unless specific is true
                hostfile: ignored unless specific is true
                specific: whether to return pid for a particular wfeng instance
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

    def _calculate_log_prefix(self, workfile, hostfile, starttime, options):
        # Return the prefix to use for logfile, or None if cfg invalid
        prefix = "%s_%s" % (workfile, hostfile)
        logoptions = self.config.cfg.get(EXTRA_LOGPARAMLIST, [])
        # Now add on any options to the filename if they are in cfg file
        # and requested
        for logoption in logoptions:
            extraval = None
            if logoption.lower() == "task":
                extraval = options.unparsed_task
            elif logoption.lower() == "tag":
                extraval = options.tag
            elif logoption.lower() == "phase":
                # NB Phase gets set to postcheck if task is specified
                # even though no phase is given at command line
                if options.unparsed_task == None:
                    extraval = options.phase
            elif logoption.lower() == "servername":
                if options.unparsed_servernames != constants.ALL:
                    extraval = options.unparsed_servernames
            elif logoption.lower() == "servertype":
                if options.unparsed_servertypes != constants.ALL:
                    extraval = options.unparsed_servertypes
            elif logoption.lower() == "exclude":
                if options.exclude != None:
                    extraval = "exclude" + options.exclude
            elif logoption.lower() == "fix":
                if options.fix:
                    extraval = "fix"
            # Use after merge
            elif logoption.lower() == "reset":
                if options.reset:
                    extraval = "reset"
            elif logoption.lower() == "list":
                if options.list:
                    extraval = "list"
            elif len(logoption) > 0:
                print "Unsupported value %s for %s" % (logoption,
                                                  EXTRA_LOGPARAM)
                return None
            if extraval != None:
                prefix = "%s_%s" % (prefix, extraval)
        # Replace any / or space with _
        prefix = prefix.replace("/", "_")
        prefix = prefix.replace(" ", "_")
        if len(prefix) + len(starttime) > 250:
            # Truncate log file as too long
            prefix = prefix[0:248 - len(starttime)] + ".."
        prefix = "%s/%s_%s" % (constants.LOG_DIR, prefix, starttime)
        return prefix

    def _add_debug_handler(self, workfile, hostfile, starttime, o, old_prefix):
        """ Add debug handler"""
        prefix = self._calculate_log_prefix(workfile, hostfile, starttime, o)
        debuglog = logging.getLogger('wfeng')
        if prefix == None:
            # Failed to calculate prefix
            return False
        if old_prefix == prefix:
            # Prefix hasn't changed so don't need to do anything
            return True
        elif old_prefix != None:
            log.debug("Changing log filename to %s after menu selections" % \
                   prefix)
            # remove all old handlers
            for hdlr in list(debuglog.handlers):
                if isinstance(hdlr, logging.FileHandler):
                    hdlr.close()
                    debuglog.removeHandler(hdlr)
        # Add debug handler
        self.logfilename = "%s.log" % prefix
        debug = logging.FileHandler(self.logfilename)
        debug.setLevel(logging.DEBUG)
        formatter = WfengFormatter('%(asctime)s %(message)s')
        debug.setFormatter(formatter)
        debuglog.addHandler(debug)
        return True

    def _add_trace_handler(self, workfile, hostfile, starttime, o, old_prefix):
        """ Add trace handler"""
        prefix = self._calculate_log_prefix(workfile, hostfile, starttime, o)
        rootlog = logging.getLogger()
        if prefix == None:
            # Failed to calculate prefix
            return False
        if old_prefix == prefix:
            # Prefix hasn't changed so don't need to do anything
            return True
        elif old_prefix != None:
            log.debug("Changing trc filename to %s after menu selections" % \
                   prefix)
            # remove all old handlers
            for hdlr in list(rootlog.handlers):
                if isinstance(hdlr, logging.FileHandler):
                    hdlr.close()
                    rootlog.removeHandler(hdlr)
        # Add trace handler
        self.tracefilename = "%s.trc" % prefix
        root = logging.FileHandler(self.tracefilename)
        root.setLevel(constants.TRACE)
        formatter = WfengFormatter('%(asctime)s %(message)s')
        root.setFormatter(formatter)
        rootlog.addHandler(root)
        return True

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
        # Check if already running - note that this is protecting us
        # from having two processes updating the same
        # master status file
        if self.alreadyRunning(o.wfile, o.hfile, o.allow_multiple):
            if o.allow_multiple:
                print "Exiting as instance of wfeng already running " + \
                      "with same hostfile and workfile"
            else:
                print "Exiting as instance of wfeng already running"
            return False

        self.config = WfmgrConfig()
        if not self.config.load():
            print "Failed to load wfeng.cfg"
            return False

        prefix = self._calculate_log_prefix(workfile, hostfile, starttime, o)
        if prefix == None:
            # Failed to calculate prefix
            return False
        self.tracefilename = "%s.trc" % prefix
        logging.addLevelName(constants.TRACE, "TRACE")
        logging.addLevelName(constants.DEBUGNOTIME, "DEBUGNOTIME")
        logging.basicConfig(filename=self.tracefilename,
                            level=constants.TRACE,
                            format=FORMAT)
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        logging.getLogger('wfeng').addHandler(console)

        if not self._add_debug_handler(workfile, hostfile, starttime, o, None):
            return False

        # Create queue for subprocesses
        self.logqueue = multiprocessing.Queue()

        if not o.version_checker.load_swplugin(
                     self.config.cfg.get(SWVERSIONPLUGIN, None)):
            log.error("Failed to load software version plugin")
            return False
        if not o.version_checker.load_osplugin(
                     self.config.cfg.get(OSVERSIONPLUGIN, None)):
            log.error("Failed to load OS version plugin")
            return False
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

        hosts = Hosts()
        if not hosts.parse(o.hfile):
            return False
        if o.needMenu():
            o.getMenuOptions(self.term_size, self.config)
            # Change filenames as used menu
            if not self._add_debug_handler(workfile, hostfile, starttime,
                                           o, prefix):
                return False
            if not self._add_trace_handler(workfile, hostfile, starttime,
                                           o, prefix):
                return False
        # if we are adding/removing dynamic pause/esc then
        # process interactively and exit
        if o.alter_pause_escape:
            try:
                dynAltOk = self.dynamicAlterations(o, hosts, ini)
                if not dynAltOk:
                    log.info("Error in dynamic alterations menu interaction")
                    return False
                return True
            except KeyboardInterrupt:
                log.info("\nUnexpected interrupt (CTRL/C) received - " \
                         "please check status file is as expected\n")
                return False
        os.system('clear')
        log.info("WORKFLOW ENGINE".center(self.term_size))
        log.info("----------------".center(self.term_size))
        log.info("\nOptions chosen:")
        log.info("    workflow: %s" % o.wfile)
        log.info("    hosts: %s" % o.hfile)
        log.info("    ini: %s" % o.inifile)
        log.info("    timeout: %s" % o.timeout)
        log.info("    phase: %s" % o.phase)
        log.info("    server types: %s" % o.unparsed_servertypes)
        log.info("    server name: %s" % o.unparsed_servernames)
        log.info("    excluded servers: %s" % o.exclude)
        log.info("    task id: %s" % o.unparsed_task)
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
            # for listing then if phase and task are not specified we will
            # run all phases
            if o.phase == None and o.task == None:
                log.info("All phases will be listed")
                o.phase = "postcheck"
        if o.fix:
            log.info("    fix: True")
        if o.reset:
            log.info("    reset: True")

        # check here that any server in the exclusion list is found in the
        # hosts file

        if o.exclude != None:
            excludes = []
            # Now strip of spaces
            excludes = [x.strip() for x in o.exclude.split(',')]
            for excludedServer in excludes:
                if not hosts.host_exists(excludedServer):
                    log.error(
                          "Excluded server %s is not in the hosts file %s" % \
                                 (excludedServer, o.hfile))
                    return False

        # validate servertype
        o.servertypes = [x.strip() for x in o.unparsed_servertypes.split(',')]
        if o.unparsed_servertypes != constants.ALL:
            for servertype in o.servertypes:
                if not servertype in hosts.hosts:
                    log.error(
                       "Server type %s selected is not in hosts file" % \
                                         servertype)
                    return False

        # validate servername
        o.servernames = [x.strip() for x in o.unparsed_servernames.split(',')]
        if o.unparsed_servernames != constants.ALL:
            for servername in o.servernames:
                if not hosts.host_exists(servername):
                    log.error(
                       "Server name %s selected is not in hosts file" % \
                                           servername)
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

        # Global status is in same directory as workfile, but appended with
        # hostname file and status.xml
        prefix = o.wfile.split('.xml')
        dirs = o.hfile.split("/")
        hostfile = dirs[len(dirs) - 1].split(".")[0]
        sysfilename = o.getSysStatusName()
        # flag for whether we are simply merging wflow and hosts and exiting
        # at start of a --list run
        listExitEarly = False
        writeNewSysfile = False
        notfoundmsg = "workflow file"
        # Check if already got work file system
        if os.path.isfile(sysfilename):
            notfoundmsg = notfoundmsg = "master status file %s" % sysfilename
            log.info("    previous run: %s" % sysfilename)
            loadsys = WorkflowSystem("", self.config)
            loadsys.load(sysfilename, hosts)
            if wfsys.isEquivalent(loadsys):
                log.debug("Previous run is equivalent to current files")
                wfsys = loadsys
            else:
                log.error("Workflow and/or hosts file has changed since "\
                          "previous run, please investigate")
                return False
        else:
            # if --reset and there is no pre-existing status file then
            # this must be an error as we have no tasks for reset
            if o.reset:
                log.error("There is no pre-existing status file %s" % \
                                                              sysfilename)
                sys.exit(1)
            # if --list and there is no pre-existing status file then we
            # generate a listing file and exit straight away
            elif o.list:
                log.info("There is no pre-existing status file %s" % \
                                                            sysfilename)
                listExitEarly = True
            else:
                log.info("    previous run: N/A")
                writeNewSysfile = True

        # validate task is valid and parse comma separated list into list
        if o.unparsed_task != None:
            o.task = utils.split_commas(o.unparsed_task)
            log.debug("Task list unparsed is %s" % o.unparsed_task)
            log.debug("Task list is %s" % o.task)
            for t in o.task:
                if not wfsys.taskInWorkflow(t):
                    log.error("Task id %s selected is not in %s" % \
                                    (t, notfoundmsg))
                    return False
                # for reset the task must be in execute phase
                if o.reset:
                    if wfsys.execute.getTask(t) == None:
                        log.error("Reset task id %s is not in " \
                                                 "execute phase" % t)
                        return False
                    elif wfsys.execute.getTask(t).isParallel():
                        log.error("Reset task id %s is not " \
                                  "supported (parallel)" % t)
                        return False

        # validate tag is valid
        if o.tag != None:
            if not wfsys.tagInWorkflow(o.tag):
                log.error("Tag %s selected is not in workflow file" % \
                                           o.tag)
                return False
        # Validate fix task is FabricTask
        if o.fix:
            for t in o.task:
                taskobj = wfsys.getTask(t)
                if not isinstance(taskobj, FabricTask) and \
                                     not isinstance(taskobj, MsgTask):
                    log.error("Fix is not supported on task %s" % \
                                   t)
                    return False

        if writeNewSysfile:
            # write new status file if neccessary now that we know there are
            # no validation issues on task or tag
            wfsys.write(sysfilename)

        # if --list then ascertain whether all eligible tasks are in a
        # complete state
        if o.list and not o.reset and \
                      wfsys.eligibleDisplayTasks(o.servertypes, o.servernames,
                         o.exclude,
                         o.force, o.version_checker):
            log.info("Display phase has not been completed and therefore "
                      "later phases cannot be predicted")
            listExitEarly = True
        if listExitEarly:
            fnamesuffix = constants.LISTFILE_SUFFIX
            log.info("\nWorkflow file and hosts file have been merged to " \
               "create list file %s%s, equivalent to a master status file" % \
               (sysfilename, constants.LISTFILE_SUFFIX))
            wfsys.write("%s%s" % (sysfilename, constants.LISTFILE_SUFFIX))
            sys.exit(0)

        if o.reset:
            log.info("\nProcessing reset...\n")
            # make sure we have a backup status file
            try:
                bkpwfsys = wf.genWorkflowSystem(hosts)
                log.debug("generating status backup")
                if os.path.isfile(sysfilename):
                    bkploadsys = WorkflowSystem("", self.config)
                    bkploadsys.load(sysfilename, hosts)
                    log.debug("taking stattus backup from %s" % sysfilename)
                    bkpwfsys = bkploadsys
            except Exception as err:
                log.error("Failed to generate backup: %s" % str(err))
                log.debug("Exception: %s" % (traceback.format_exc()))
                return False
            try:
                resetOk = wfsys.processManualReset(o)
                if resetOk == constants.R_OK:
                    log.info("\nManual reset completed successfully")
                elif resetOk == constants.R_DEPENDENCY_CONFLICT:
                    log.info("\nManual reset cancelled due to " \
                             "conflicting dependencies")
                    return False
                else:
                    log.info("\nManual reset not actioned due to errors " \
                             "encountered")
                    return False

                # all ok - so backup and save altered status file
                errmsgs = []
                if not self.writeUpdate(wf, wfsys, sysfilename, hosts,
                             constants.MANUAL_RESET_BKPDIR, errmsgs, bkpwfsys):
                    errs = ""
                    if len(errmsgs) != 0:
                        errs = "Error: ".join(errmsgs)
                    log.error("Manual reset statusfile update failed %s" % \
                                                                          errs)
                    return False
                return True
            except KeyboardInterrupt:
                log.info("\nUnexpected interrupt (CTRL/C) received " \
                         "during manual reset - " \
                         "please check status file is as expected\n")
                return False
        wfsys.logqueue = self.logqueue
        # Add an interrupt handler for main process to handle Ctrl-C
        # Any children will inherit this signal handler
        signal.signal(signal.SIGINT, wfsys.interrupt_handler)
        runner = CmdLineWorkflowRunner(wfsys, self.term_size, o)
        if o.list:
            log.info("\nListing has been run from the pre-existing master "\
                     "status file onwards, with predictive output written "
                     "to file %s%s" % (sysfilename,
                                       constants.LISTFILE_SUFFIX))
        ret = runner.run()
        return ret

    def dynamicAlterations(self, o, hosts, ini):
        """ does the processing for a dynamic alterations run

            Args:
                o: the WorkflowOptions object
                hosts: hosts object
                ini: the ini file params object
            Returns:
                boolean - True if completed ok
        """
        wf = Workflow(self.config)
        sysfilename = o.getSysStatusName()
        menuMsgs = []

        if not wf.parse(o.wfile):
            log.info("Error encountered when parsing workflow file")
            return False
        try:
            wfsys = wf.genWorkflowSystem(hosts)
            bkpwfsys = wf.genWorkflowSystem(hosts)
        except Exception as err:
            log.error("Failed to generate workflow : %s" % str(err))
            log.debug("Exception: %s" % (traceback.format_exc()))
            return False

        dynamicMenu = DynamicMenuMgr(self.term_size, self.config, hosts,
                                      self.dynamicTaskValidator)

        while True:
            log.debug("Starting loop with menuMsgs length %d" % \
                                len(menuMsgs))
            # Check if already got work file system
            if os.path.isfile(sysfilename):
                loadsys = WorkflowSystem("", self.config)
                loadsys.load(sysfilename, hosts)
                if wfsys.isEquivalent(loadsys):
                    log.debug("Previous run is equivalent to current "
                                  "files - operating on status file")
                    wfsys = loadsys
                    bkploadsys = WorkflowSystem("", self.config)
                    bkploadsys.load(sysfilename, hosts)
                    log.debug("taking status backup from %s" % sysfilename)
                    bkpwfsys = bkploadsys
                else:
                    log.error("Workflow and/or hosts file has "
                        "changed since previous run, please investigate")
                    return False
            else:
                log.debug("A new master status file will be created")

            dyntask = dynamicMenu.getDynamicAlteration(wfsys, menuMsgs)
            if dyntask == None:
                log.info("Quitting dynamic alterations")
                return True
            elif dyntask == {}:
                log.debug("Dynamic alteration empty")
                menuMsgs = []
            else:
                log.debug("Dynamic task input: %s" % dyntask)
                menuMsgs = []
                if not self.processDynamicAlteration(dyntask, wf, wfsys,
                               bkpwfsys, sysfilename, hosts, menuMsgs):
                    if len(menuMsgs) == 0:
                        menuMsgs.append("Unspecified error during " \
                                      "processing %s, dynamic alteration " \
                                      "abandoned, please check logs" % \
                             dyntask[constants.DYN_ID])
                log.debug("Finished processDynamicAlteration with "
                              "menuMsg %s" % menuMsgs)

    def processDynamicAlteration(self, dyntask, wf, wfsys, bkpwfsys,
                                  sysfilename, hosts, menuMsgs):
        """ processes a dynamic alteration (add/remove) for pause/esc

            Args:
                dyntask: a dictionary containing the details for the alteration
                wf: the original workflow (for validation in writeUpdate)
                wfsys: the workflowsys
                bkpwfsys: the original workflowsys for backup
                sysfilename: the name of the master status file
                hosts: host object containing details of the hosts in this run
                menuMsgs: list to hold messages for display during interaction
            Returns:
                boolean: True if alteration successful,
                         False if alteration failed
        """
        dyntaskid = dyntask[constants.DYN_ID]
        if dyntaskid == "" or dyntaskid == None:
            menuMsgs.append("Dynamic task id is empty")
            return False

        dyntype = dyntask[constants.DYN_TYPE]
        if not dyntype == constants.DYNAMIC_ESCAPE and \
                 not dyntype == constants.DYNAMIC_PAUSE:
            menuMsgs.append("Dynamic task type for dynamic task %s must be "
                      "%s or %s - but found %s" % \
                (dyntaskid, constants.DYNAMIC_ESCAPE,
                 constants.DYNAMIC_PAUSE, dyntype))
            return False
        if dyntask[constants.DYN_ACTION] == constants.DYNAMIC_ADD:
            if wfsys.taskInWorkflow(dyntaskid):
                menuMsgs.append(
                  "Dynamic task id %s duplicates one already in the workflow" \
                              % dyntaskid)
                return False
            if not self.dynamicAlterationAdd(dyntask, wf, wfsys,
                              bkpwfsys, sysfilename, hosts, menuMsgs):
                menuMsgs.append("Unable to add dynamic task %s" % \
                               dyntask[constants.DYN_ID])
                return False
        elif dyntask[constants.DYN_ACTION] == constants.DYNAMIC_REMOVE:
            # look for dynamic task id in workflow execute phase
            if wfsys.execute.getTask(dyntaskid) is None:
                menuMsgs.append("Dynamic %s task id %s not found in workflow "
                        "execute phase" % (dyntype, dyntaskid))
                return False
            if not self.dynamicAlterationRemove(dyntask, wf, wfsys,
                                       bkpwfsys, sysfilename, hosts, menuMsgs):
                menuMsgs.append("Unable to remove dynamic task %s" % \
                                                dyntask[constants.DYN_ID])
                return False
        else:
            menuMsgs.append("Unable to determine action %s" % \
                                dyntask[constants.DYN_ACTION])
            return False

        return True

    def dynamicAlterationAdd(self, dyntask, wf, wfsys, bkpwfsys, sysfilename,
                                                     hosts, menuMsgs):
        """performs dynamic addition for pause/esc

           Args:
                dyntask: a dictionary containing the details for the alteration
                wf: the original workflow (for validation in writeUpdate)
                wfsys: the workflowsys
                bkpwfsys: the original workflowsys for backup
                sysfilename: the name of the master status file
                hosts: host object containing details of the hosts in this run
                menuMsgs: list to hold messages for display during interaction
           Returns:
                boolean: True if alteration successful,
                         False if alteration failed
        """
        # get the execute phase for the workflow
        executephase = wfsys.getExecutePhase()
        refid = dyntask[constants.DYN_REFID]
        taskdict = executephase.getTaskIndices(refid)
        indRefs = taskdict[constants.TASK_LIST]
        groupid = taskdict[constants.TASK_IN_GROUP]
        if len(indRefs) == 0:
            menuMsgs.append("Unable to find valid reference task %s "
                            "in workflow execute phase" % refid)
            return False
        firstRefInd = indRefs[0]
        lastRefInd = indRefs[len(indRefs) - 1]
        pos = dyntask[constants.DYN_POS]
        dyntaskid = dyntask[constants.DYN_ID]
        dyntype = dyntask[constants.DYN_TYPE]

        if pos == constants.DYNAMIC_BEFORE:
            insertionPoint = firstRefInd
        elif pos == constants.DYNAMIC_AFTER:
            insertionPoint = lastRefInd + 1
        else:
            menuMsgs.append("Position for dynamic task %s must be %s "
                      "or %s - but found %s" % \
                (dyntaskid, constants.DYNAMIC_BEFORE,
                    constants.DYNAMIC_AFTER, pos))
            return False
        log.debug("inserting task %s into execute phase at "
                      "index %s" % (dyntaskid, insertionPoint))
        checkparams = {}
        if dyntask[constants.DYN_CHECKPARAMS] is None:
            checkParams = None
        else:
            chks = dyntask[constants.DYN_CHECKPARAMS].split(',')
            for chk in chks:
                chckName, chckVar = chk.split('=')
                checkparams[chckName] = chckVar

        # note that for dynamic tasks dynamic and optional will always be true
        dynamic = True
        optional = True
        if dyntype == constants.DYNAMIC_ESCAPE:
            taskforinsert = EscapeTask(dyntaskid, self.config,
            dyntask[constants.DYN_MSG],
            dyntask[constants.DYN_HOSTS],
            dyntask[constants.DYN_SERVER],
            dyntask[constants.DYN_SWVER],
            dyntask[constants.DYN_OSVER],
            dyntask[constants.DYN_DEP],
            optional,
            utils.get_stringtoboolean(dyntask[constants.DYN_DEPSINGLE]),
            checkparams,
            groupid,
            dynamic)
        else:
            taskforinsert = PauseTask(dyntaskid, self.config,
            dyntask[constants.DYN_MSG],
            dyntask[constants.DYN_HOSTS],
            dyntask[constants.DYN_SERVER],
            dyntask[constants.DYN_SWVER],
            dyntask[constants.DYN_OSVER],
            dyntask[constants.DYN_DEP],
            optional,
            utils.get_stringtoboolean(dyntask[constants.DYN_DEPSINGLE]),
            checkparams,
            groupid,
            dynamic)
        if groupid == None:
            if not executephase.insertDynamic(taskforinsert,
                                        hosts, insertionPoint, menuMsgs):
                menuMsgs.append("Failed to insert dynamic task %s "
                                "into execute phase" % \
                        taskforinsert.name)
                return False
        else:
            if not executephase.insertDynamicIntoGroup(taskforinsert,
                                        hosts, indRefs, pos, menuMsgs):
                menuMsgs.append("Failed to insert dynamic task %s "
                                 "into group %s execute phase" % \
                        (taskforinsert.name, groupid))
                return False
        if not self.writeUpdate(wf, wfsys, sysfilename, hosts,
                             constants.DYNAMIC_ALTERATIONS_BKPDIR,
                               menuMsgs, bkpwfsys):
            menuMsgs.append("Dynamic addition update for task %s "
                             "failed - please check logs" % \
                        taskforinsert.name)
            return False
        menuMsgs.append("New master status file %s created with "
                        "dynamic entry %s added" % (sysfilename, dyntaskid))
        return True

    def dynamicAlterationRemove(self, dyntask, wf, wfsys, bkpwfsys,
                                      sysfilename, hosts, menuMsgs):
        """performs dynamic addition for pause/esc

           Args:
                dyntask: a dictionary containing the details for the alteration
                wf: the original workflow (for validation in writeUpdate)
                wfsys: the workflowsys
                bkpwfsys: the original workflowsys for backup
                sysfilename: the name of the master status file
                hosts: host object containing details of the hosts in this run
                menuMsgs: list to hold messages for display during interaction
           Returns:
                boolean: True if alteration successful,
                         False if alteration failed
        """
        # get the execute phase for the workflow
        executephase = wfsys.getExecutePhase()
        dyntaskid = dyntask[constants.DYN_ID]
        dyntype = dyntask[constants.DYN_TYPE]

        if self.dynamicTaskValidator.hasDependents(dyntaskid, wfsys, menuMsgs):
            menuMsgs.append("Dynamic removal failed validation")
            return False

        if not executephase.removeDynamic(dyntaskid, dyntype, menuMsgs):
            menuMsgs.append("Failed to remove dynamic task %s "
                            "from execute phase, please check logs" % \
                        dyntaskid)
            return False
        if not self.writeUpdate(wf, wfsys, sysfilename, hosts,
                        constants.DYNAMIC_ALTERATIONS_BKPDIR,
                                  menuMsgs, bkpwfsys):
            menuMsgs.append("Dynamic removal update for task %s failed "
                            "- please check logs" % \
                        dyntaskid)
            return False
        menuMsgs.append("New master status file %s created with dynamic "
                        "entry %s removed" % (sysfilename, dyntaskid))
        return True

    def writeUpdate(self, wf, wfsys, sysfilename, hosts, backupdir, errmsgs,
                                     bkpwfsys=None):
        """ updates the master status file
            firstly as a tmp file, then reads in and validates the tmp
            file and if ok renames to master status file

            Args:
                wf: the original workflow (for validation)
                wfsys: the workflowsys
                sysfilename: name of the master status file
                hosts: the hosts object
                backupdir: the dir in which backup is to reside
                errmsgs: list to hold messages from this method
                bkpwfsys: the backup wfsys generated at start
            Returns:
                True if master valid master status file was produced,
                False if errors were encountered
        """
        # now update the workflow file as tmp file
        tmpsysfile = "%s_tmp" % sysfilename
        wfsys.write(tmpsysfile)
        log.debug("New tmp status file %s written" % tmpsysfile)
        # now attempt to reload the tmp file - which will validate against xsd
        loadtmp = WorkflowSystem("", self.config)
        if not loadtmp.load(tmpsysfile, hosts):
            errmsgs.append("Failed to reload new master status file. " \
                       "Investigate the problem, then remove invalid " \
                       "temporary status file %s," \
                       " and rerun the dynamic alteration" % tmpsysfile)
            return False
        # now perform equivalency test against original workflow
        wfcheck = wf.genWorkflowSystem(hosts)
        if not wfcheck.isEquivalent(loadtmp):
            errmsgs.append("New master status file does not match original" \
                            " workflow. " \
                       "Investigate the problem, then remove invalid " \
                       "temporary status file %s," \
                       " and rerun the dynamic alteration" % tmpsysfile)
            return False

        # write backup file before updating the status file
        tstamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if '/' in sysfilename:
            sysfilesplit = sysfilename.rsplit('/', 1)
            basedir = sysfilesplit[0]
            basename = sysfilesplit[1]
        else:
            basedir = "./"
            basename = sysfilename
        timestampedBackup = "%s/%s/%s.%s" % \
                            (basedir, backupdir, basename, tstamp)
        # retrieve full path of backup dir
        backupdir = timestampedBackup.rsplit('/', 1)[0]
        if not os.path.exists(backupdir):
            log.debug("creating backup directory %s" % backupdir)
            os.mkdir(backupdir)
        if bkpwfsys is not None:
            bkpwfsys.write(timestampedBackup)
            log.debug("Timestamped backup %s created" % timestampedBackup)
        else:
            log.error("Unable to create backup, no backup wfsys")
            return False
        log.debug("Renaming temp status file %s as master status file %s" % \
                   (tmpsysfile, sysfilename))

        # if validated ok and backup created then rename the tmp file
        # as the new master statusfile
        try:
            os.rename(tmpsysfile, sysfilename)
        except:
            errmsgs.append("Error renaming temporary file %s to master "
                            "status file %s" % (tmpsysfile, sysfilename))
            return False

        return True


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
                    log.debug("Writing results of listing to %s%s" % \
                             (sysfilename, constants.LISTFILE_SUFFIX))
                    self.wfsys.write("%s%s" % (sysfilename,
                                             constants.LISTFILE_SUFFIX))
                else:
                    self.wfsys.write(sysfilename)
                if status.status == WorkflowStatus.USER_INPUT:
                    log.debug("Asking: %s" % status.user_msg)
                    if not self.wfsys.input.askContinue(status):
                        log.debug("Response indicates to stop")
                        finished = True
                        if self.wfsys.trapped:
                            log.info("STOPPING due to interrupt")
                        else:
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
                log.debug("Writing results of listing to %s%s" % (sysfilename,
                                                constants.LISTFILE_SUFFIX))
                self.wfsys.write("%s%s" % (sysfilename,
                                                 constants.LISTFILE_SUFFIX))
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
                            help="Comma separated types of server to run on")
        parser.add_argument("-n", "--servername", default=constants.ALL,
                            help="Comma separated names of server to run on")
        parser.add_argument("-g", "--tag",
                            help="Only run tasks in this tagged set")
        parser.add_argument("-e", "--exclude",
                    help="Comma separated names of server not to run on")
        parser.add_argument("-t", "--task",
                            help="Comma separated list of IDs of tasks to run")
        parser.add_argument("-f", "--force", action='store_true',
                    help=argparse.SUPPRESS)
        parser.add_argument("-l", "--list", action='store_true', default=False,
                    help=argparse.SUPPRESS)
        parser.add_argument("-F", "--fix", action='store_true', default=False,
                    help="Mark matching tasks as fixed")
        parser.add_argument("-R", "--reset", action='store_true',
                    default=False, help="Mark matching tasks as reset")
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
                            help="Silently answer yes to all questions " \
                                 "except pauses")
        parser.add_argument("-a", "--automate", action='store_true',
                            default=False,
                            help="Silently answer yes to all questions " \
                                 "including pauses")
        parser.add_argument("-d", "--alter_pause_escape", action='store_true',
                            default=False,
                            help="Invoke interactive add/delete of dynamic " \
                                  "pause and dynamic escape into master " \
                                  "status file")
        # When running in parallel mode then connections will be made to
        # each parallel server at same time.
        # If these are to the same server, then a delay may be required
        # between connection attempts such that the SSH server is not
        # overloaded with requests
        parser.add_argument("--parallel-delay",
                            default="1", type=int,
                            help=argparse.SUPPRESS)
        args = parser.parse_args()
        self.version = args.version
        if args.version:
            return
        if args.task == "":
            parser.error("Task must not be an empty string")

        if args.alter_pause_escape:
            # verify that only other args are workflow, hosts, custom ini file
            # - note that workflow and hosts have defaults - so will always
            # be present, and that default ini file is always read
            if args.phase != None or \
                    args.servername != constants.ALL or \
                    args.servertype != constants.ALL or \
                    args.tag != None or \
                    args.exclude != None or \
                    args.task != None or \
                    args.force != False or \
                    args.list != False or \
                    args.fix != False or \
                    args.reset != False or \
                    args.version != False or \
                    args.nospinner != False or \
                    args.allow_multiple != False or \
                    args.output != None or \
                    args.yes != False or \
                    args.automate != False:
                parser.error("For alter_pause_escape option the only " \
                             "additional (non-default) parameters must be "\
                                "--workfile (-w) and --hostfile (-H)")

        if args.fix:
            # verify that inappropriate params are not supplied
            if args.reset:
                parser.error("param reset not permitted for fix")
            if args.tag != None:
                parser.error("param tag not permitted for fix")
            if args.parallel_delay != 1:
                parser.error("parallel-delay not permitted for fix")
            if args.list:
                parser.error(
                    "The --list parameter cannot be used with manual fix")

        if args.reset:
            # verify that inappropriate params are not supplied
            if args.phase != None or \
                    args.timeout != 10 or \
                    args.version != False or \
                    args.nospinner != False or \
                    args.output != None or \
                    args.yes != False or \
                    args.automate != False or \
                    args.alter_pause_escape != False or \
                    args.parallel_delay != 1:
                parser.error("For manual reset option the only compatible "\
                             "parameters are : workflow, hostfile, " \
                             "servertype, servername, tag, exclude, task, " \
                              "force, allow-multiple")

            if args.list:
                parser.error(
                    "The --list parameter cannot be used with manual reset")

            if args.task == None and args.tag == None:
                parser.error(
                    "For manual reset one of task or tag must be supplied")
            if args.tag == "":
                parser.error(
                    "For manual reset the tag parameter cannot be " \
                         "empty string")

            if args.exclude != None and args.servername != constants.ALL:
                parser.error("For reset option the exclude parameter cannot " \
                             "be used with servername")
            if args.servername == constants.LOCAL:
                parser.error("For manual fix or reset option the servername " \
                             "parameter cannot be constants.LOCAL")
            if args.servertype == constants.LOCAL:
                parser.error("For manual fix or reset option the servertype " \
                             "parameter cannot be constants.LOCAL")
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
        #if args.fix and args.servername == constants.ALL:
        #    parser.error("Servername must be specified to use fix")
        if args.output == None:
            self.output_level = 0
        else:
            try:
                self.output_level = int(args.output)
            except:
                parser.error("Output level must be numeric")
        self.wfile = args.workfile
        self.inifile = args.inifile
        self.hfile = args.hostfile
        self.timeout = args.timeout
        self.phase = args.phase
        self.unparsed_servertypes = args.servertype
        self.unparsed_servernames = args.servername
        self.exclude = args.exclude
        self.unparsed_task = args.task
        self.task = None
        self.force = args.force
        self.list = args.list
        self.fix = args.fix
        self.reset = args.reset
        self.nospinner = args.nospinner
        self.allow_multiple = args.allow_multiple
        self.alter_pause_escape = args.alter_pause_escape
        self.yes = args.yes
        self.automate = args.automate
        self.parallel_delay = args.parallel_delay
        self.version_checker = PluginMgr()
        self.tag = args.tag
        if self.unparsed_task != None:
            if self.reset:
                self.phase = constants.OPT_EXECUTE
            else:
                self.phase = constants.OPT_POSTCHECK

    def needMenu(self):
        if self.phase == None and self.unparsed_task == None and \
           self.reset != True and self.list != True and \
           self.alter_pause_escape != True:
            return True
        else:
            return False

    def getMenuOptions(self, term_size, config):
        menumgr = MenuMgr(term_size, config)
        if not menumgr.getOptions(self):
            sys.exit(0)

    def getSysStatusName(self):
        """ Calculates system filename for the status
            Returns: filename
        """
        prefix = self.wfile.split('.xml')
        dirs = self.hfile.split("/")
        hostfile = dirs[len(dirs) - 1].split(".")[0]
        sysfilename = "%s_%s_status.xml" % (prefix[0], hostfile)
        return sysfilename

    def getSysStatusBackupName(self, backupdir="", backupsuffix=".bkp"):
        """ Constructs system filename for the status backup file used
            for dynamic alterations
            Returns: filename
        """
        if '/' in self.hfile:
            dirs = self.hfile.split("/")
            hostfile = dirs[len(dirs) - 1].split(".")[0]
        else:
            hostfile = self.hfile.split(".")[0]
        srcfname = self.wfile.rsplit('.xml')[0]
        if '/' in srcfname:
            fnamesplit = srcfname.rsplit("/", 1)
            dirs = fnamesplit[0]
            dirs = dirs + '/'
            fname = fnamesplit[1]
        else:
            dirs = ""
            fname = srcfname

        sysfilebkpname = "%s%s/%s_%s_status.xml%s" % (dirs,
                           backupdir, fname, hostfile, backupsuffix)
        log.debug("backup status file name is %s" % sysfilebkpname)
        return sysfilebkpname

import utils
import logging
from wfeng import constants
from wfeng import wfconfig
log = logging.getLogger(__name__)

INV_PARAM = "Skip as value for {0} is {1} for host {2} and task {3}"
REACHED_VERSION = \
  "Skipping task {0} on {1} as swver {2} and osver {3} indicates " \
  "task not required"
NO_PARAM = "Skip as no value for {0} for host {1} and task {2}"


class WTask:
    def __init__(self, name, config):
        """Initialises task object"""
        self.name = name
        self.config = config
        self.optional = False  # default to False
        self.run_local = False
        self.gid = None
        self.depsinglehost = False
        self.checkparams = {}
        # Will be initialised when task created
        self.pluginmgr = None

    def hasVersion(self):
        return False

    def equals(self, task):
        """ Compares this Task with that described by task, and
            returns if they are the same.

            Args:
                task: Task to compare against
            Returns:
                boolean: True if same, False if different
        """
        if self.name != task.name:
            return False
        if self.optional != task.optional:
            log.debug("Optional differ {0}/{1} for {2}".format(
                      self.optional, task.optional, self.name))
            return False
        if self.run_local != task.run_local:
            log.debug("Run local differ {0}/{1} for {2}".format(
                      self.run_local, task.run_local, self.name))
            return False
        if self.depsinglehost != task.depsinglehost:
            log.debug("Dependency_single_host differs %s/%s" % \
                    (self.depsinglehost,
                     task.depsinglehost))
            return False

        return True

    def getStatusTasks(self, host):
        """ Returns a list of StatusTask objects in order to be processed.

            Args:
                host: Host to run on, will be ignored
                status: current status
            Returns:
                list of StatusTask classes
        """
        return []

    def getTasks(self):
        """ Returns list of tasks that this represents. For base class this is
            just itself"""
        log.log(constants.TRACE, "Base getTasks called")
        return [self]

    def needsHost(self):
        """ Returns if this task applies only to particular hosts"""
        return False

    def isTag(self):
        """ Indicates if this is a tag task"""
        return False

    def isParallel(self):
        """ Indicates if this is a parallel task"""
        return False

    def isDynamic(self):
        """ Indicates if this is a dynamic task - ie dynamic pause or
            dynamic escape """
        return False


class StatusTask:
    def __init__(self, task, status):
        self.task = task
        self.status = status
        self.actualDuration = None
        self.actualDurationInt = -1L
        self.host = None

    def containsTask(self, taskname):
        """ Returns if this task contains taskname """
        return self.task.name == taskname

    def isParallelStatusTask(self):
        """ Indicates if this is a parallel status task"""
        return False

    def setStatus(self, status):
        self.status = status

    def logDetails(self):
        """ Does nothing, but on tasks that might skip can output details of
            task"""
        pass

    def isEquivalent(self, stask):
        """ Compares this StatusTask with that described by stask, and
            if they are the same ignoring status then they are equivalent

            Args:
                stask: StatusTask to compare against
            Returns:
                boolean: True if same ignoring status, False if different
        """
        if not self.task.equals(stask.task):
            log.debug("Task %s didn't match %s" % (self.task.name,
                                    stask.task.name))
            return False
        return True

    def run(self, output_func, phasename, wfsys, tasklist,
                  alwaysRun, options):
        """ Base method for running_task, expected to be always overridden"""
        output_func("INVALID TASK %s" % self.task.name, True)
        return False

    def hasHost(self):
        """ Returns if this status task applies only to particular hosts"""
        return (self.host != None)

    def askSkip(self):
        """ Returns whether valid to ask whether to skip this task """
        return False

    def hasDependency(self):
        """ Returns if this StatusTask is dependant on another"""
        return False

    def shouldRunOnHost(self, servertypes, servernames, excluded, inputmgr,
                              force, version_checker):
        """ Determines whether to run, returns True if hasHost is False,
            else expects task to have host parameter to check on,
            and swversion """
        run_on_server = True
        if self.hasHost():
            if self.task.servertype != constants.LOCAL:
                # Always run on locals unless specified a task id
                found_server = False
                for servertype in servertypes:
                    # Check if server type is correct
                    # Input validation will have prevented user entering
                    # *,TYPE1 - so if * is in list, it will be the only entry
                    # So no special code needed here to cope with it
                    if servertype == constants.ALL or \
                        self.host.servertype == servertype:
                            found_server = True
                if not found_server:
                    log.debug(
                         "Skipping task %s on %s as server not type %s" \
                         % (self.task.name, self.host.hostname,
                         servertypes))
                    run_on_server = False

                found_server = False
                for name in servernames:
                    # Input validation will have prevented user entering
                    # *,name1 - so if * is in list, it will be the only entry
                    # So no special code needed here to cope with it
                    if name == constants.ALL or \
                     self.host.hostname == name:
                        found_server = True

                if not found_server:
                    log.debug("Skipping task %s on %s as host not %s" \
                              % (self.task.name, self.host.hostname,
                                 servernames))
                    run_on_server = False

                for exclude in excluded:
                    if self.host.hostname == exclude:
                        log.debug(
                          "Skipping task %s on %s as host excluded" % \
                                 (self.task.name, self.host.hostname))
                        run_on_server = False

                # Now check for swversion if we need it
                swMatch = False
                swversion = None
                testSwMatch = False
                if run_on_server and \
                     self.task.hasVersion() and self.task.swversion != None:
                    # if version starts with $ then we are looking for
                    # a matching param
                    taskversion = utils.extractIniParam(
                            self.task.config.iniparams, self.task.swversion)
                    if taskversion != self.task.swversion:
                        log.debug(
                         "Taken task swversion %s from ini file parameter %s" \
                            % (taskversion, self.task.swversion))
                    if taskversion != None:
                        testSwMatch = True
                        swversion = self.getSWVersion()
                        if swversion == None and not force:
                            swversion = inputmgr.getVersion("software",
                                                  self.host.hostname)
                            if swversion != None:
                                self.setSWVersion(swversion)
                        try:
                            if version_checker.check_swversion(taskversion,
                                                         swversion):
                                swMatch = True
                        except ValueError:
                            log.error("Failed to compare sw versions %s/%s" \
                                % (taskversion, swversion))
                # Now check for osversion if we need it
                osMatch = False
                osversion = None
                testOsMatch = False
                if run_on_server and \
                     self.task.hasVersion() and self.task.osversion != None:
                    taskversion = utils.extractIniParam(
                           self.task.config.iniparams, self.task.osversion)
                    if taskversion != self.task.osversion:
                        log.debug(
                         "Taken task osversion %s from ini file parameter %s" \
                            % (taskversion, self.task.osversion))
                    if taskversion != None:
                        testOsMatch = True
                        osversion = self.getOSVersion()
                        if osversion == None and not force:
                            osversion = inputmgr.getVersion("OS",
                                                  self.host.hostname)
                            if osversion != None:
                                self.setOSVersion(osversion)
                        try:
                            if version_checker.check_osversion(taskversion,
                                                         osversion):
                                osMatch = True
                        except ValueError:
                            log.error("Failed to compare os versions %s/%s" \
                                % (taskversion, osversion))
                if run_on_server:
                    # Work out results of version check
                    if (testOsMatch and not osMatch) or \
                       (testSwMatch and not swMatch) or \
                       (not testOsMatch and not testSwMatch):
                        log.debug("Passed version check so run task")
                    else:
                        # already at correct osversion/swversion
                        log.debug(REACHED_VERSION.format(self.task.name,
                                                  self.host.hostname,
                                                  swversion,
                                                  osversion))
                        self.status = constants.REACHED_VERSION
                        run_on_server = False
                if run_on_server:
                    for key, val in self.task.checkparams.iteritems():
                        if not key in self.host.params:
                            log.debug(NO_PARAM.format(key, self.host.hostname,
                                          self.task.name))
                            self.status = constants.PARAM_NOTMATCH
                            run_on_server = False
                        else:
                            vals = val.split("|")
                            found = False
                            for eachval in vals:
                                if self.host.params[key] == eachval:
                                    found = True
                            if not found:
                                log.debug(INV_PARAM.format(key,
                                     self.host.params[key],
                                     self.host.hostname,
                                    self.task.name))
                                self.status = constants.PARAM_NOTMATCH
                                run_on_server = False
        return run_on_server

    def setSWVersion(self, swversion):
        """ Sets the swversion parameter on host"""
        swkey = self.task.config.cfg[wfconfig.SWVER]
        self.host.params[swkey] = swversion

    def setOSVersion(self, osversion):
        """ Sets the osversion parameter on host"""
        oskey = self.task.config.cfg[wfconfig.OSVER]
        self.host.params[oskey] = osversion

    def getSWVersion(self):
        """ Returns the swversion associated with this task, or None if unknown
            Returns:
                String representing the swver or None if swversion unknown
        """
        swkey = self.task.config.cfg[wfconfig.SWVER]
        if not swkey in self.host.params:
            return None
        if self.host.params[swkey] == wfconfig.UNKNOWN:
            return None
        return self.host.params[swkey]

    def getOSVersion(self):
        """ Returns the osversion associated with this task, or None if unknown
            Returns:
                String representing the osver or None if osversion unknown
        """
        oskey = self.task.config.cfg[wfconfig.OSVER]
        if not oskey in self.host.params:
            return None
        if self.host.params[oskey] == wfconfig.UNKNOWN:
            return None
        return self.host.params[oskey]

    def getTaskStatusList(self, taskid):
        # returns task status object, related to this task
        if self.task.name == taskid:
            return [self]
        return []

    def getCounts(self):
        """ Returns tuple of numSuccess, numFailed, numSkipped related to
            how many tasks succeeded, failed, skipped. As single task
            only 1 value will be non-zero """
        return utils.getStatusCount(self.status, self.task.name, log)

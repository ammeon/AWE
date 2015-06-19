"""Represents the different task objects
@copyright: Ammeon Ltd
"""
from fabric.api import run
from fabric.tasks import Task
from fabric.context_managers import settings, hide, show
# from fabric.operations import local
from fabric.tasks import execute
from fabric.state import env
from fabric.network import disconnect_all
import constants
import os
import logging
import datetime
import traceback
import sys
import wfconfig
# import re
import subprocess
# import threading
import multiprocessing
from lxml import etree
import time
import utils
import Queue
# from io import IOBase

# Output for screen
STOPPING_ERR = "STOPPING as task failed and continue on failure is not set"
REACHED_VERSION = \
  "Skipping task {0} on {1} as swver {2} and osver {3} indicates " \
  "task not required"
INV_PARAM = "Skip as value for {0} is {1} for host {2} and task {3}"
NO_PARAM = "Skip as no value for {0} for host {1} and task {2}"
STATUS_FORMAT = "STATUS %s: %s%s%s, START: %s%s\n"
PARALLEL_STATUS_FORMAT = "STATUS %s: %s%s%s, START: %s%s\n"
STATUS_DATEFMT = "%H:%M:%S"

log = logging.getLogger(__name__)


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

    def hasVersion(self):
        return False

    def equals(self, task):
        """ Compares this Task with that described by task, and
            returns if they are the same.
            Arguments:
                task: Task to compare against
            Returns:
                True: if same
                False: if different
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
            Arguments:
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


class FabricTask(WTask):
    """Represents a generic task"""
    def __init__(self, name, config, cmd, hosts, server, continueOnFail,
                           optional, duration, dependency, swversion,
                           osversion,
                           run_local, depsinglehost, checkparams, gid):
        """Initialises task object"""
        WTask.__init__(self, name, config)
        self.cmd = cmd
        self.hosts = hosts
        self.servertype = server
        self.continueOnFail = continueOnFail
        self.optional = optional
        self.duration = duration
        self.dependency = dependency
        self.checkparams = checkparams
        self.depsinglehost = depsinglehost
        self.gid = gid
        self.swversion = swversion
        self.osversion = osversion
        self.run_local = run_local
        # fullcmd - holds result of cmd and evaluating $param as
        # environment variables
        # NB. By default fabric evaluates the $param you pass as environment
        # variables without us needing to do anything
        self.fullcmd = self.cmd

    def hasVersion(self):
        return True

    def equals(self, task):
        """ Compares this Task with that described by task, and
            returns if they are the same. It ignores the hosts parameter
            as when this is part of a StatusTask the hosts is irrelevant, as
            it will have been expanded to a Host object
            Arguments:
                task: Task to compare against
            Returns:
                True: if same
                False: if different
        """
        if not WTask.equals(self, task):
            return False
        if not isinstance(task, FabricTask):
            log.debug("Task is not a FabricTask {0}".format(task.name))
            return False
        if self.cmd != task.cmd:
            log.debug("Cmd differ {0}/{1} for {2}".format(
                       self.cmd, task.cmd, self.name))
            return False
        if self.servertype != task.servertype:
            log.debug("Server type differ {0}/{1} for {2}".format(
                       self.servertype, task.servertype, self.name))
            return False
        if self.continueOnFail != task.continueOnFail:
            log.debug("ContinueOnFail differ {0}/{1} for {2}".format(
                      self.continueOnFail, task.continueOnFail, self.name))
            return False
        if self.duration != task.duration:
            log.debug("Duration differ {0}/{1} for {2}".format(
                      self.duration, task.duration, self.name))
            return False
        if self.dependency != task.dependency:
            log.debug("Dependency differ {0}/{1} for {2}".format(
                      self.dependency, task.dependency, self.name))
            return False
        if self.checkparams != task.checkparams:
            log.debug("Checkparams differ {0}/{1} for {2}".format(
                      self.checkparams, task.checkparams, self.name))
            return False
        if self.gid != task.gid:
            log.debug("Group id differ {0}/{1} for {2}".format(
                      self.gid, task.gid, self.name))
            return False
        if self.swversion != task.swversion:
            log.debug("Version differ {0}/{1} for {2}".format(
                      self.swversion, task.swversion, self.name))
            return False
        if self.osversion != task.osversion:
            log.debug("Version differ {0}/{1} for {2}".format(
                      self.osversion, task.osversion, self.name))
            return False
        return True

    def getStatusTasks(self, host):
        """ Returns a list of StatusTask objects in order to be processed.
            Arguments:
                host: Host to run on
            Returns:
                list of StatusTask classes
        """
        tasks = [FabricStatusTask(self, host, constants.INITIAL)]
        return tasks

    def execute(self, host, infoprefixes, errprefixes, output_level,
                            host_colour, ps_logger):
        """ Runs fabric task (local or remote):
            ps_logger is a process safe logger
            Arguments: host Host object to run on
            Returns result object
        """
        os.environ['SERVERNAME'] = host.hostname
        os.environ['SERVERTYPE'] = self.servertype
        os.environ['SERVERIP'] = host.ipaddr
        with settings(
            hide('everything', 'aborts', 'status')

        ):
            result = self._do_execute(host, infoprefixes, errprefixes,
                                            output_level, host_colour, ps_logger)
        return result

    def getFullCmd(self, host):
        # Replace SERVERNAME and SERVERTYPE in cmd, and also anything
        # declared in the INI file
        vars = {}
        vars['SERVERNAME'] = host.hostname
        vars['SERVERTYPE'] = self.servertype
        vars['SERVERIP'] = host.ipaddr
        vars.update(self.config.iniparams)
        expanded_cmd = utils.replace_vars(self.cmd, vars)
        return expanded_cmd

    def getLogStr(self, host):
        return "Running %s" % self.getCmdHostLogStr(host)

    def _do_execute(self, host, infoprefixes, errprefixes, output_level, ps_logger):
        raise Exception("Base do_execute of FabricTask should never be run")

    def __str__(self):
        return
        "ID=%s,CMD=%s,HOSTS=%s,TYPE=%s,CONTINUE=%s,OPTIONAL=%s,RUNLOCAL=%s" %\
             (self.name, self.cmd, self.hosts, self.servertype,
                         self.continueOnFail, self.optional, self.run_local)

    def process_result(self, result, status, host, has_status, stype,
                             err_prefixes, info_prefixes):
        """ Processes a Fabric Result object and populates a generic
            RunStatus.
            Arguments: result: retruned from task's process_result
                       status: RunStatus object to populate
                       host: Host to populate with any parameters
                       has_status: If status could be present
                       stype: expected server type
                       err_prefixes: Error line prefix for display
                       info_prefixes: Info line prefix
        """
        status.returncode = -1
        if hasattr(result, "return_code"):
            status.returncode = result.return_code
            status.stdout = result.stdout
            self._parseResp(host, result, has_status, stype,
                               status, err_prefixes, info_prefixes)
        else:
            log.debug("Not got a return code so will be an error")
            status.status = constants.FAILED
            status.err_msg = str(result)
            status.stdout = None

    def _parseResp(self, host, result, has_status, stype, status,
                                errprefixes, infoprefixes):
        """Parses result from a remote task that succeeded
           Arguments:
               host: Host object to populate with parameters
               result: Result returned from Fabric
               has_status: bool whether status could be present or not
               stype: expected server type
               status: RunStatus object to populate
               errprefixes: Prefix that indicates this line should be
                              displayed as error
               infoprefixes: Used if has_status is true, and could have
                           status (info) line
        """
        status.err_msg = None
        errLines = []
        foundStatus = False
        log.debug("Parsing STDOUT for {0}_{1}:".format(self.name,
                                                       host.hostname))
        lines = result.stdout.split("\n")
        setvarprefix = self.config.cfg[wfconfig.SETVAR]
        for line in lines:
            for errprefix in errprefixes:
                if errprefix in line:
                    errLines.append(line.split(errprefix,
                                          1)[1].lstrip().strip())
            if setvarprefix in line and host.hostname == \
                               constants.LOCAL:
                varLine = line.split(setvarprefix,
                                        1)[1].lstrip().strip()
                lvars = varLine.split(' ')
                varname = lvars[0]
                varvalue = varLine[len(varname) + 1:].lstrip()
                log.debug("Extracted parameter %s" % varname)
                os.environ[varname] = varvalue
            else:
                for infoprefix in infoprefixes:
                    if infoprefix in line:
                        # Strip out any x=y contained in line
                        if "=" in line:
                            foundStatus = True
                            log.debug("Found info status line {0}".\
                                           format(line))
                            statusline = line.split(infoprefix,
                                           1)[1].lstrip().strip()
                            status.err_msg = self._parseStatusLine(\
                                              host,
                                              statusline, stype,
                                              infoprefix)
                            if status.err_msg == None:
                                # status.logdata = line
                                status.logdata = statusline
        if result.succeeded and status.err_msg == None and \
                                len(errLines) == 0:
            status.status = constants.SUCCESS
        else:
            status.status = constants.FAILED
            if status.err_msg == None and not result.succeeded:
                status.err_msg = "Non-zero return code {0}".format(
                                                status.returncode)
            elif status.err_msg == None:
                # Must have had success code but errLines set
                status.err_msg = "{0} messages detected".format(
                                                errprefixes)

    def _parseStatusLine(self, host, statusline, stype, infoprefix):
        """Parses display status line
           Arguments:
               host: Host object to update
               statusline: Contents of statusline after STATUS prefix
               stype: expected server type
               infoprefix: status prefix
           Returns:
               None: if successfully parsed, else error description
        """
        err_msg = None
        # We may get more than one info line. If the line matches format of
        # <tag>:x=y,d=e then we should attempt to parse the data in it
        values = statusline.split(",")
        for value in values:
            tagvalue = value.split("=")
            if len(tagvalue) == 2:
                k, v = value.split("=")
                log.log(constants.TRACE, "Adding key {0}".format(k))
                if not host.add_param(k, v):
                    err_msg = "Parameter %s has changed since previous run" % k
                    return err_msg
        foundVersion = False
        for keyparam in [wfconfig.SWVER, wfconfig.OSVER]:
            ver_key = self.config.cfg[keyparam]
            if ver_key in host.params:
                foundVersion = True
        if foundVersion:
            type_key = self.config.cfg[wfconfig.TYPE]
            if type_key in host.params:
                # Check type is of correct type
                if host.params[type_key] != stype:
                    err_msg = "Expected type {0} but got {1}".format(
                        stype,
                         host.params[type_key])
            else:
                log.log(constants.TRACE,
                      "Missing {0} from {1} line".format(type_key,
                                                            infoprefix))
        return err_msg

    def needsHost(self):
        """ Returns if this task applies only to particular hosts"""
        return True


class RemoteFabricTask(FabricTask):
    def __init__(self, id, config, cmd, hosts, server, continueOnFail,
                    optional, duration, dependency, swversion, osversion,
                    run_local,
                    depsinglehost, checkparams, gid):
        """Initialises task object"""
        FabricTask.__init__(self, id, config, cmd, hosts, server,
                                  continueOnFail, optional,
                                  duration, dependency, swversion, osversion,
                                  run_local, depsinglehost, checkparams, gid)
        self.id = id
        self.runtask = FabricRunTask(id, self.fullcmd)

    def copy(self, server):
        """ Returns copy of task but with different servertype """
        return RemoteFabricTask(self.name, self.config, self.cmd, self.hosts,
                               server, self.continueOnFail, self.optional,
                               self.duration, self.dependency, self.swversion,
                               self.osversion, self.run_local,
                               self.depsinglehost, self.checkparams, self.gid)

    def _do_execute(self, host, infoprefixes, errprefixes, output_level,
                          host_colour, ps_logger):
        """ Runs remote fabric task:
            Arguments: host Host object to run on
            ps_logger is a process-safe logger
            Returns result object
        """
        hoststr = "%s@%s" % (host.username, host.ipaddr)
        myout = utils.StreamToLogger("%s_%s" % \
                               (self.id, host.hostname),
                               host.username, host.ipaddr,
                               infoprefixes, errprefixes, output_level,
                               host_colour, ps_logger)
        results = execute(self.runtask, hosts=[hoststr], mylogger=myout)
        result = results[hoststr]
        return result

    def getCmdHostLogStr(self, host):
        expanded_cmd = self.getFullCmd(host)
        return "%s on %s" % (expanded_cmd, host.ipaddr)


class LocalFabricTask(FabricTask):
    def __init__(self, name, config, cmd, hosts, server, continueOnFail,
                       optional, duration, dependency, swversion,
                       osversion,
                       run_local, depsinglehost, checkparams, gid):
        """Initialises task object"""
        FabricTask.__init__(self, name, config, cmd, hosts, server,
                            continueOnFail, optional, duration,
                            dependency, swversion, osversion, run_local,
                            depsinglehost, checkparams, gid)

    def copy(self, server):
        """ Returns copy of task but with different servertype """
        return LocalFabricTask(self.name, self.config, self.cmd, self.hosts,
                               server, self.continueOnFail, self.optional,
                               self.duration, self.dependency, self.swversion,
                               self.osversion, self.run_local,
                               self.depsinglehost, self.checkparams, self.gid)

    def _do_execute(self, host, infoprefixes, errprefixes, output_level,
                                host_colour, ps_logger):
        """ Runs local fabric task:
            Arguments: host Host object to run on, ignored
            ps_logger is a process safe logger
            Returns result object
        """
        # Fabric can either write to terminal or capture
        # We want to capture it but also log in real-time so
        # we will use our own stream and redirect stdout/stderr and use
        # Subprocess directly, instead of
        # local(self.fullcmd, capture=True)
        cmd = utils.replace_vars(self.fullcmd, os.environ)

        p = subprocess.Popen(cmd, shell=True,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
        result = DummyResult()
        if self.servertype == constants.LOCAL:
            prefix = "{0}_LOCAL".format(self.name)
        else:
            prefix = "{0}_{1}".format(self.name, host.hostname)
        while 1:
            out = p.stdout.readline()
            err = p.stderr.readline()
            if not out and not err:
                break
            else:
                if out:
                    if not utils.processLineForTags(out, infoprefixes,
                                       errprefixes,
                                       ps_logger, prefix, output_level, host_colour):
                        ps_logger.log(constants.DEBUGNOTIME, "  -->{0}: {1}"\
                                .format(prefix, out))
                    result.stdout = "%s%s\n" % (result.stdout, out)
                if err:
                    if not utils.processLineForTags(out, infoprefixes,
                             errprefixes,
                             ps_logger, prefix, output_level, host_colour):
                        ps_logger.log(constants.DEBUGNOTIME, "  -->{0}: {1}"\
                                 .format(prefix, err))
                    result.stderr = "%s%s\n" % (result.stderr, err)
        p.wait()
        if p.returncode != 0:
            result.failed = True
            result.succeeded = False
        else:
            result.failed = False
            result.succeeded = True
        result.return_code = p.returncode
        return result

    def getCmdHostLogStr(self, host):
        expanded_cmd = self.getFullCmd(host)
        return "%s on LOCAL" % (expanded_cmd)


class FabricRunTask(Task):
    def __init__(self, name, cmd):
        """Initialises task object"""
        self.cmd = cmd
        self.name = name

    def run(self, mylogger):
        cmd = ""
        # Evaluate any $XXX on command line with those in os
        cmd = utils.replace_vars(self.cmd, os.environ)
        with show('stdout'):
            result = run("%s" % cmd, stdout=mylogger)
        return result


class GroupTask(WTask):
    def __init__(self, name, config):
        """Initialises group object"""
        WTask.__init__(self, name, config)
        self.tasks = []

    def append(self, task):
        """ Adds a WTask to list of tasks in this group.
            Validates that all tasks are of same type and returns if
            added ok"""
        # Add its group id
        task.gid = self.name
        if len(self.tasks) == 0:
            # If first task just add it and make note of hosts and servertype
            self.tasks.append(task)
            self.hosts = task.hosts
            self.servertype = task.servertype
            self.optional = task.optional
            return True
        else:
            if task.hosts == self.hosts and \
                             task.servertype == self.servertype:
                self.tasks.append(task)
                if self.optional and not task.optional:
                     # Group is only optional if every task in it is optional
                    self.optional = False
                return True
            else:
                log.error("Task %s is not compatible with others in group" %
                               task.name)
                return False

    def equals(self, task):
        """ Compares this Task with that described by task, and
            returns if they are the same.
            Arguments:
                task: Task to compare against
            Returns:
                True: if same
                False: if different
        """
        if not WTask.equals(self, task):
            return False
        if not isinstance(task, GroupTask):
            log.debug("Task is not a GroupTask {0}".format(task.name))
            return False
        if len(self.tasks) != len(task.tasks):
            log.debug("Length of tasks in group differ %s/%s" % \
                        (len(self.tasks), len(task.tasks)))
            return False
        for i in range(len(self.tasks)):
            if not self.tasks[i].equals(task.tasks[i]):
                return False
        return True

    def getStatusTasks(self, host):
        """ Returns a list of StatusTask objects in order to be processed.
            As this is a group, go through each underlying task
            Arguments:
                host: Host to run on
            Returns:
                list of StatusTask classes
        """
        stasks = []
        for task in self.tasks:
            stasks.append(FabricStatusTask(task, host, constants.INITIAL))
        return stasks

    def getTasks(self):
        """ Returns list of tasks that this represents.
            Include myself so can get id"""
        return self.tasks + [self]

    def __str__(self):
        return "GROUP %s numTasks=%d" % (self.name, len(self.tasks))

    def needsHost(self):
        """ Returns if this task applies only to particular hosts"""
        return True


class RunStatus:
    def __init__(self):
        self.returncode = -1
        self.err_msg = None
        self.status = constants.INITIAL
        self.logdata = None


class FabricTaskManager:
    """ Manager for creating correct type of FabricTask objects"""
    def createTask(self, id, config,
                         cmd, hosts, server, continueOnFail, optional,
                         duration, dependency, swversion, osversion,
                         run_local,
                         depsinglehost, checkparams, gid=None):
        """ Returns a FabricTask object of correct type depending on server"""
        if server == constants.LOCAL or run_local == True:
            return LocalFabricTask(id, config, cmd, hosts, server,
                                       continueOnFail, optional,
                                       duration, dependency, swversion,
                                       osversion,
                                       run_local, depsinglehost,
                                       checkparams, gid)
        else:
            return RemoteFabricTask(id, config, cmd, hosts, server,
                                       continueOnFail, optional,
                                       duration, dependency, swversion,
                                       osversion,
                                       run_local, depsinglehost,
                                       checkparams, gid)


class StatusTask:
    def __init__(self, task, status):
        self.task = task
        self.status = status
        self.actualDuration = None
        self.actualDurationInt = -1L

    def containsTask(self, taskname):
        """ Returns if this task contains taskname """
        return self.task.name == taskname

    def isParallelStatusTask(self):
        """ Indicates if this is a parallel status task"""
        return False


    def setStatus(self, status):
        self.status = status

    def logCommand(self):
        """ Does nothing, but on tasks that might skip can output details of
            task"""
        pass

    def isEquivalent(self, stask):
        """ Compares this StatusTask with that described by stask, and
            if they are the same ignoring status then they are equivalent
            Arguments:
                stask: StatusTask to compare against
            Returns:
                True: if same ignoring status
                False: if different
        """
        if not self.task.equals(stask.task):
            log.debug("Task %s didn't match" % self.task.name)
            return False
        return True

    def run(self, output_func, phasename, wfsys, task,
                  alwaysRun, options):
        """ Base method for running_task, expected to be always overridden"""
        output_func("INVALID TASK %s" % self.task.name, True)
        return False

    def hasHost(self):
        """ Returns if this status task applies only to particular hosts"""
        return False

    def askSkip(self):
        """ Returns whether valid to ask whether to skip this task """
        return False

    def hasDependency(self):
        """ Returns if this StatusTask is dependant on another"""
        return False

    def shouldRunOnHost(self, servertype, servername, excluded, inputmgr,
                              force, exact_match):
        """ Determines whether to run, returns True if hasHost is False,
            else expects task to have host parameter to check on,
            and swversion """
        run_on_server = True
        if self.hasHost():
            if self.task.servertype != constants.LOCAL:
                # Always run on locals unless specified a task id
                if servertype != constants.ALL:
                    # Check if server type is correct
                    if self.host.servertype != servertype:
                        log.debug(
                             "Skipping task %s on %s as server not type %s" \
                                % (self.task.name, self.host.hostname,
                                   servertype))
                        run_on_server = False

                if servername != constants.ALL:
                    if self.host.hostname != servername:
                        log.debug("Skipping task %s on %s as host not %s" \
                              % (self.task.name, self.host.hostname,
                                 servername))
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
                    # if version starts with $ then we are looking for a matching param
                    taskversion=utils.extractIniParam(self.task.config.iniparams, self.task.swversion)
                    if taskversion != self.task.swversion:
                        log.debug("Taken task swversion %s from ini file parameter %s" \
                            % (taskversion, self.task.swversion))
                    if taskversion != None:
                        testSwMatch = True
                        swversion = self.getSWVersion()
                        if swversion == None and not force:
                            swversion = inputmgr.getVersion("software",
                                                  self.host.hostname)
                            if swversion != None:
                                self.setSWVersion(swversion)
                        if utils.check_version(taskversion, swversion,
                                           exact_match):
                            swMatch = True

                # Now check for osversion if we need it
                osMatch = False
                osversion = None
                testOsMatch = False
                if run_on_server and \
                     self.task.hasVersion() and self.task.osversion != None:
                    taskversion=utils.extractIniParam(self.task.config.iniparams, self.task.osversion)
                    if taskversion != self.task.osversion:
                        log.debug("Taken task osversion %s from ini file parameter %s" \
                            % (taskversion, self.task.osversion))
                    if taskversion != None:
                        testOsMatch = True
                        osversion = self.getOSVersion()
                        if osversion == None and not force:
                            osversion = inputmgr.getVersion("OS",
                                                  self.host.hostname)
                            if osversion != None:
                                self.setOSVersion(osversion)
                        if utils.check_version(taskversion, osversion,
                                           exact_match):
                             osMatch = True
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


class FabricStatusTask(StatusTask):
    """ Represents a workflow task with status """
    def __init__(self, task, host, status):
        """ Initialises StatusTask
            Arguments:
                task: FabricTask object
                host: Host object
                status: String with status
        """
        StatusTask.__init__(self, task, status)
        self.host = host
        self.logged = False

    def logCommand(self):
        log.info("TASK %s: %s ..." % \
                     (self.getId(), self.task.getLogStr(self.host)))
        self.logged = True

    def isEquivalent(self, stask):
        """ Compares this StatusTask with that described by stask, and
            if they are the same ignoring status then they are equivalent
            Arguments:
                stask: StatusTask to compare against
            Returns:
                True: if same ignoring status
                False: if different
        """
        if not self.task.equals(stask.task):
            log.debug("Task %s didn't match" % self.task.name)
            return False
        if not self.host.equals(stask.host):
            log.debug("Host %s didn't match" % self.host.hostname)
            return False
        return True

    def run(self, output_func, phasename, wfsys, task,
                  alwaysRun, options,
                  parallelRun=False,
                  logger=log, host_colour='\033[0m'):
        """ Runs a task remotely or locally using Fabric
            Arguments:
                output_func: Method for writing status to, which takes
                             arguments, line to write and boolean indicating
                             if end of line
            Returns:
                True if should continue
                False if should stop
        """
        if options.fix:
            genid = self.getId()
            self.status = constants.MANUAL_FIX
            status_colour = constants.COLOURS.status[self.status]
            logger.info("%s%s%s TASK %s: %s\n" % \
                                   (status_colour, self.status,
                                    constants.COLOURS.END, genid,
                                    self.task.getCmdHostLogStr(self.host)))
            return WorkflowStatus(WorkflowStatus.COMPLETE, "")
        spinnerThread = None
        env.parallel = False
        env.linewise = True
        env.skip_bad_hosts = True
        logger.debug("Run %s on %s/%s (runLocal=%s), state %s" % \
                    (self.task.cmd, self.host.hostname,
                           self.host.ipaddr, self.task.run_local, self.status))
        if self.task.continueOnFail:
            env.warn_only = True
        else:
            # If we set warn only to False then all that changes is fabric
            # raises an exception and handling is not as nice
            # As we currently aren't grouping tasks into one fabric call
            # then we don't get any benefit from using warn_only = False
            # Only use warn_only as false if we end up doing a fabric call
            # with multiple sequential tasks in
            #env.warn_only = False
            env.warn_only = True
        details = ""
        genid = self.getId()
        if parallelRun:
            formatStr = PARALLEL_STATUS_FORMAT
            # write to stdout using logger so that keep order
            useStdout = False
        else:
            formatStr = STATUS_FORMAT
            useStdout = True
        if options.output_level > constants.QUIET:
            formatStr = formatStr + "\n"
        try:
            starttime = datetime.datetime.now()
            startStr = starttime.strftime(STATUS_DATEFMT)
            self.task.returncode = -1
            if not self.logged:
                logger.info("TASK %s: %s ..." % \
                     (genid, self.task.getLogStr(self.host)))
            cur_status = constants.RUNNING
            duration = ""
            if self.task.duration != None:
                estduration=utils.extractIniParam(self.task.config.iniparams, self.task.duration)
                if estduration != self.task.duration:
                    log.debug("Taken task est duration %s from ini file parameter %s" \
                            % (estduration, self.task.duration))
                if estduration == "" or estduration == None:
                    duration = ""
                else:
                    duration = " ESTIMATED DUR: %s" % estduration
            status_colour = constants.COLOURS.status[cur_status]
            logger.log(constants.TRACE, "Log status with %s" % useStdout)
            output_func(formatStr % \
                    (genid, status_colour, cur_status, constants.COLOURS.END,
                     startStr, duration), logger=logger, usestdout=useStdout)
            if not parallelRun and not options.nospinner:
                spinnerThread = utils.SpinnerThread(output_func, False)
                spinnerThread.start()
            has_status = False
            err_prefixstr = self.task.config.cfg[wfconfig.EXECUTE_ERR]
            info_prefixstr = self.task.config.cfg[wfconfig.EXECUTE_INFO]
            if phasename == constants.DISPLAY:
                # Indicate there could be optional status
                has_status = True
                err_prefixstr = self.task.config.cfg[wfconfig.DISPLAY_ERR]
                info_prefixstr = self.task.config.cfg[wfconfig.DISPLAY_INFO]
            elif phasename == constants.PRECHECK:
                err_prefixstr = self.task.config.cfg[wfconfig.PRECHECK_ERR]
                info_prefixstr = self.task.config.cfg[wfconfig.PRECHECK_INFO]
            elif phasename == constants.POSTCHECK:
                err_prefixstr = self.task.config.cfg[wfconfig.POSTCHECK_ERR]
                info_prefixstr = self.task.config.cfg[wfconfig.POSTCHECK_INFO]
            err_prefixes = err_prefixstr.split(",")
            info_prefixes = info_prefixstr.split(",")
            result = self.task.execute(self.host, info_prefixes, err_prefixes,
                                       options.output_level, host_colour, logger)
            endtime = datetime.datetime.now()
            status = RunStatus()
            self.task.process_result(result, status, self.host,
                                          has_status, self.task.servertype,
                                          err_prefixes, info_prefixes)
            logger.debug("%s: Parameters extracted:%s" % \
                                             (genid, repr(self.host.params)))
            self.status = status.status
            if self.status == constants.FAILED:
                details = ", ERROR: %s" % (status.err_msg)
            # Nolonger log out data taken from info lines, as going to have
            # on separate lines
            #elif status.logdata != None:
            #    details = ", %s" % status.logdata
        except WorkflowException as e:
            # This is raised because we handled an abort exception
            endtime = datetime.datetime.now()
            self.status = constants.FAILED
            logger.debug("Updating result to be failed")
            logger.debug("WorkflowException: %s" % (traceback.format_exc()))
            details = ", ERROR: %s" % (e.err_msg)
        except:
            endtime = datetime.datetime.now()
            self.status = constants.FAILED
            logger.debug("Updating result to be failed")
            logger.debug("Exception: %s" % (traceback.format_exc()))
            (etype, value, _) = sys.exc_info()
            logger.debug("Exception type %s: value %s" % (etype, value))
            # except error details to be stderr in this case...
            details = ", ERROR: Exception: %s/%s" % (etype, value)
        finally:
            if spinnerThread != None:
                spinnerThread.stop()
                spinnerThread.join()
                spinnerThread = None
        cur_status = constants.COMPLETED
        status_colour = constants.COLOURS.status[cur_status]
        endStr = ", END: %s" % endtime.strftime(STATUS_DATEFMT)

        output_func(formatStr % \
                    (genid, status_colour, cur_status,
                     constants.COLOURS.END,
                     startStr,
                     endStr), False, True, logger, useStdout)
        status_colour = constants.COLOURS.status[self.status]
        # Ignore microseconds on duration, as can only store
        # seconds in the shared memory when doing parallel
        td1 = (endtime - starttime)
        td = (td1 - datetime.timedelta(microseconds=td1.microseconds))
        self.actualDuration = "{0}".format(td)
        self.actualDurationInt = td.seconds + (td.days * 24 * 3600)
        logger.info("RESULT %s: %s%s%s%s, DURATION: %s\n" % \
                                   (genid, status_colour, self.status,
                                    constants.COLOURS.END, details,
                                    td))
        if self.status not in constants.SUCCESS_STATUSES and \
                  not self.task.continueOnFail:
            logger.error(STOPPING_ERR)
            return WorkflowStatus(WorkflowStatus.FAILED, "")
        else:
            return WorkflowStatus(WorkflowStatus.COMPLETE, "")

    def hasHost(self):
        """ Returns if this status task applies only to particular hosts"""
        return True

    def askSkip(self):
        """ Returns whether valid to ask whether to skip this task """
        return True

    def getHosts(self):
        """ Returns the hosts this applies to """
        return [self.host]

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

    def setSWVersion(self, swversion):
        """ Sets the swversion parameter on host """
        swkey = self.task.config.cfg[wfconfig.SWVER]
        self.host.params[swkey] = swversion

    def setOSVersion(self, osversion):
        """ Sets the osversion parameter on host """
        oskey = self.task.config.cfg[wfconfig.OSVER]
        self.host.params[oskey] = osversion

    def hasDependency(self):
        """ Returns if this StatusTask is dependant on another"""
        return (self.task.dependency != None)

    def populateTree(self, element, writeHostParams):
        """ Populates phase element with tasks """
        status = etree.SubElement(element, "taskstatus")
        status.attrib["cmd"] = self.task.cmd
        status.attrib["host"] = self.host.hostname
        status.attrib["server"] = self.task.servertype
        utils.populate_boolean(status, self.task.continueOnFail,
                                      "continueOnFail")
        utils.populate_boolean(status, self.task.optional,
                                      "optional")
        utils.populate_boolean(status, self.task.depsinglehost,
                                      "depsinglehost")
        utils.populate_boolean(status, self.task.run_local,
                                      "runLocal")
        if writeHostParams:
            utils.populate_dictionary(status, self.host.params, "params")
        utils.populate_dictionary(status, self.task.checkparams, "checkparams")
        status.attrib["id"] = self.task.name
        status.attrib["status"] = self.status
        utils.populate_optional(status, self.task.dependency, \
               "dependency")
        utils.populate_optional(status, self.task.duration, \
               "estimatedDur")
        utils.populate_optional(status, self.actualDuration, \
               "actualDur")
        utils.populate_optional(status, self.task.gid, "gid")
        utils.populate_optional(status, self.task.swversion, \
               "swversion")
        utils.populate_optional(status, self.task.osversion, \
               "osversion")

    def getId(self):
        """ Returns id that represents this task, will be of format
            <taskid>_<hostname>"""
        return "%s_%s" % (self.task.name, self.host.hostname)

    def getCmd(self):
        return self.task.getFullCmd(self.host)


class WorkflowException(Exception):
    # Used for handling fabric aborts
    def __init__(self, value, err_prefix):
        self.value = value


class WorkflowStatus:
    """ Returns status of running workflow"""
    COMPLETE = 0
    FAILED = 1
    USER_INPUT = 2
    STOPPED = 3

    def __init__(self, status, user_msg, success_msg=None):
        self.status = status
        self.user_msg = user_msg
        self.success_msg = success_msg
        self.continueresponse = "y"
        self.stopresponse = "n"

    def isStopResponse(self, answer):
        """ Method that indicates if 'answer' indicates should stop workflow.
        """
        if answer == self.stopresponse:
            return True
        else:
            return False

    def isValidResponse(self, answer):
        """ Method that indicates if 'answer' is valid response
        """
        if answer == self.stopresponse or answer == self.continueresponse:
            return True
        else:
            return False


class TagTask(WTask):
    """ Start tag task, just a marker """
    def __init__(self, name, config, is_start):
        """Initialises start object"""
        WTask.__init__(self, "{0}_{1}".format(name, is_start), config)
        self.is_start = is_start
        self.tag = name

    def getStatusTasks(self, host):
        """ Returns a list of StatusTask objects in order to be processed.
            Arguments:
                host: Host to run on, will be ignored
            Returns:
                list of StatusTask classes
        """
        tasks = [TagStatusTask(self, constants.INITIAL)]
        return tasks

    def equals(self, task):
        """ Compares this Task with that described by task, and
            returns if they are the same.
            Arguments:
                task: Task to compare against
            Returns:
                True: if same
                False: if different
        """
        if not WTask.equals(self, task):
            return False
        if not isinstance(task, TagTask):
            log.debug("Task is not a TagTask {0}".format(task.name))
            return False
        if self.is_start != task.is_start:
            log.debug("Start/end differ {0}".format(task.name))
            return False
        if self.tag != task.tag:
            log.debug("tag differ {0}".format(task.name))
            return False
        return True

    def isTag(self):
        """ Indicates if this is a tag task"""
        return True


class TagStatusTask(StatusTask):
    """ Represents a tag task with status """
    def __init__(self, task, status):
        """ Initialises StatusTask
            Arguments:
                task: TagTask object
                status: String with status
        """
        StatusTask.__init__(self, task, status)

    def populateTree(self, element, writeHostParams):
        """ Populates tag element with task """
        if self.task.is_start:
            elem = "start-tag"
        else:
            elem = "end-tag"
        status = etree.SubElement(element, elem)
        log.log(constants.TRACE, "Populating {0} with {1}".format(element,
                                                     self.task))
        status.attrib["name"] = self.task.tag

    def getId(self):
        """ Returns id that represents this task, which will be task id
        """
        return self.task.name


class ParallelTask(WTask):
    """ Holds a set of sequences, where sequences are run in parallel"""
    def __init__(self, name, config):
        """ Initialises parallel object """
        WTask.__init__(self, name, config)
        self.sequences = []  # This is populated when process workflow.xml, is
                             # array of Sequences
        self.hostSequences = []  # This is populated when process hosts against
                                 # workflow.xml, is tuple of sequence/host

    def isParallel(self):
        """ Indicates if this is a parallel task"""
        return True

    def getTasks(self):
        """ Returns list of tasks that this represents.
            Include myself so can get id"""
        tasks = [self]
        log.log(constants.TRACE,
                 "Num sequences {0}".format(len(self.sequences)))
        for a in self.sequences:
            log.log(constants.TRACE,
                 "Add tasks from seq {0}".format(a.name))
            tasks = tasks + a.getTasks()
        return tasks

    def getStatusTasks(self, host):
        """ Returns a list of StatusTask objects in order to be processed.
            Arguments:
                host: Host to run on, Ignored as use hostSequences to
                      know what hosts to run each sequence within parallel on
            Returns:
                list of StatusTask classes
        """
        pStatusTask = ParallelStatusTask(self, constants.INITIAL)
        for seq, host in self.hostSequences:
            seqTask = SequenceStatusTask(seq, host)
            pStatusTask.sequences.append(seqTask)
            for task in seq.tasks:
                stasks = task.getStatusTasks(host)
                for statustask in stasks:
                    seqTask.addTask(statustask)
        return [pStatusTask]

    def equals(self, task):
        """ Compares this Task with that described by task, and
            returns if they are the same.
            Arguments:
                task: Task to compare against
            Returns:
                True: if same
                False: if different
        """
        if not WTask.equals(self, task):
            return False
        if not isinstance(task, ParallelTask):
            log.debug("Task is not a ParallelTask {0}".format(task.name))
            return False
        if len(self.sequences) != len(task.sequences):
            log.debug("Length of sequences differ {0} {1}/{2}".format(\
                task.name, len(self.sequences), len(task.sequences)))
            return False
        for i in range(len(self.sequences)):
            if not self.sequences[i].equals(task.sequences[i]):
                log.debug("Sequence differs {0}".format(task.name))
                return False
        return True

    def isTag(self):
        """ Indicates if this is a tag task"""
        return False

    def getSequence(self, task):
        sequence = None
        if task.dependency != None:
            # search through the sequences to see if there is one that has
            # same dependency
            for seq in self.sequences:
                if seq.hasTask(task.dependency):
                    sequence = seq
        if sequence == None:
            seqid = "{0}:{1}:{2}:{3}".format(self.name, task.servertype,
                             task.hosts, len(self.sequences))
            log.log(constants.TRACE, "Creating sequence {0}".format(seqid))
            sequence = SequenceTask(seqid, self.config)
            self.sequences.append(sequence)
        else:
            # Need to check that sequence is configured with the same
            # servertype and hosts as us
            if task.hosts != sequence.hosts or \
                task.servertype != sequence.servertype:
                log.log(constants.TRACE,
                       "task {0} has {1}/{2} and seq has {3}/{4}".format(\
                        task.name, task.hosts, task.servertype,
                        sequence.hosts, sequence.servertype))
                log.error("Invalid to have parallel tasks that are " +
                       "dependant on each other but have different " +
                       "server/host values, {0} is invalid".format(task.name))
                return None
        return sequence


class SequenceTask(WTask):
    """ Represents a sequence of tasks that will be run within a thread,
        where will have one thread per host that sequence is to be run on """
    def __init__(self, name, config):
        """ Initialises sequence """
        WTask.__init__(self, name, config)
        # pid may have : in, so cope with that by working back
        fields = self.name.split(":")
        numfields = len(fields)
        self.index = int(fields[numfields - 1])
        self.hosts = fields[numfields - 2]
        self.servertype = fields[numfields - 3]
        self.pid = fields[0]
        for i in range(numfields - 4):
            self.pid = "{0}:{1}".format(self.pid, fields[i + 1])
        self.tasks = []  # populated from workflow.xml but not from
                         # workflowstatus
        self.optional = True  # Only optional if all tasks are optional

    def copy(self, servertype):
        # pid may have : in, so cope with that by working back
        fields = self.name.split(":")
        numfields = len(fields)
        index = int(fields[numfields - 1])
        hosts = fields[numfields - 2]
        newname = "{0}:{1}:{2}:{3}".format(self.pid, servertype,
                  self.hosts, self.index)
        seq = SequenceTask(newname, self.config)
        for task in self.tasks:
            seq.addTask(task.copy(servertype))
        return seq

    def getTasks(self):
        """ Returns list of tasks that this represents.
            Include myself so can get id"""
        tasks = [self]
        for a in self.tasks:
            tasks = tasks + a.getTasks()
        return tasks

    def hasTask(self, taskid):
        found = False
        for a in self.tasks:
            if a.name == taskid:
                found = True
        return found

    def addTask(self, task):
        self.tasks.append(task)
        if task.optional == False:
            self.optional = False


class ParallelStatusTask(StatusTask):
    """ Represents a parallel task with status """
    def __init__(self, task, status):
        """ Initialises StatusTask
            Arguments:
                task: ParallelTask object
                status: String with status
        """
        StatusTask.__init__(self, task, status)
        self.sequences = []  # array of SequenceStatusTasks

    def containsTask(self, taskname):
        """ Returns if this task contains taskname """
        if self.task.name == taskname:
            return True
        else:
            # See if its in one of our tasks
            for seq in self.sequences:
                for task in seq.tasks:
                    if task.task.name == taskname:
                        log.log(constants.TRACE,
                           "Found {0} in parallel task".format(taskname))
                        return True
                    else:
                        log.log(constants.TRACE,
                           "{0} not {1} in parallel task".format(\
                             task.task.name, taskname))
        return False

    def isParallelStatusTask(self):
        """ Indicates if this is a parallel status task"""
        return True

    def setStatus(self, status):
        """ Update all sequences with status, used to inform that are skipping
            whole parallel task"""
        self.status = status
        for seq in self.sequences:
            seq.setStatus(status)

    def logCommand(self):
        hostStr = ""
        hosts = self.getHosts()
        for host in hosts:
            if hostStr != "":
                hostStr = "{0}, ".format(hostStr)
            ipaddr = host.ipaddr
            if host.hostname == constants.LOCAL:
                ipaddr = "LOCAL"
            hostStr = "{0}{1}".format(hostStr, ipaddr)
        log.info("PARALLEL_TASK %s: Running on %s ..." % \
                     (self.getId(), hostStr))
        self.logged = True

    def isEquivalent(self, stask):
        """ Compares this StatusTask with that described by stask, and
            if they are the same ignoring status then they are equivalent
            Arguments:
                stask: StatusTask to compare against
            Returns:
                True: if same ignoring status
                False: if different
        """
        if not isinstance(stask, ParallelStatusTask):
            log.debug("Task is not a ParallelStatusTask {0}".\
                                 format(stask.task.name))
            return False
        if self.task.name != stask.task.name:
            log.debug("Parallel ID differs {0}/{1}".format(\
                        self.task.name, stask.task.name))
            return False
        # to be equivalent then sequences need to be same
        if len(self.sequences) != len(stask.sequences):
            log.debug("Sequence length differs {0}/{1}".format(\
                                  len(self.sequences),
                                  len(stask.sequences)))
            return False
        for i in range(len(self.sequences)):
            if len(self.sequences[i].tasks) != len(stask.sequences[i].tasks):
                log.debug("Task length differs {0}/{1}".format(\
                                  len(self.sequences[i].tasks),
                                  len(stask.sequences[i].tasks)))
                return False
            for j in range(len(self.sequences[i].tasks)):
                if not self.sequences[i].tasks[j].isEquivalent(\
                         stask.sequences[i].tasks[j]):
                    log.debug("Task {0} differs".format(\
                        self.sequences[i].tasks[j].task.name))
                    return False
        return True

    def populateTree(self, element, writeHostParams):
        """ Populates tag element with task """
        status = etree.SubElement(element, "parallelstatus")
        log.log(constants.TRACE, "Populating parallel with {0}".format(\
                self.task.name))
        status.attrib["id"] = self.task.name
        for seq in self.sequences:
            seq.populateTree(status, writeHostParams)

    def getId(self):
        """ Returns id that represents this task, which will be task id
        """
        return self.task.name

    def hasHost(self):
        """ Returns if this status task applies only to particular hosts"""
        return True

    def askSkip(self):
        """ Returns whether valid to ask whether to skip this task """
        return True

    def getHosts(self):
        """ Returns the hosts this applies to """
        hostlist = []
        for seq in self.sequences:
            if seq.host not in hostlist:
                hostlist.append(seq.host)
        return hostlist

    def listTasks(self, servertype, servername, excluded, input,
                       force, exact_match):
        """ Returns a list of tuples of tasks/booleans, where boolean is
            true if should run on server, false if not """
        ret = []
        for seq in self.sequences:
            for task in seq.tasks:
                if task.shouldRunOnHost(servertype, servername, excluded,
                        input, force, exact_match):
                    ret.append((task, True))
                else:
                    ret.append((task, False))
        return ret

    def sequenceNoneToRun(self, servertype, servername, excluded, input,
                       force, exact_match):
        """returns True if the sequence has no tasks runnable for the given parameters, or False if any task in the sequence is eligible to run"""
        ret = True
        for seq in self.sequences:
            for task in seq.tasks:
                # only check status on those tasks that are eligible for the given run parameters
                if task.shouldRunOnHost(servertype, servername, excluded,
                        input, force, exact_match):
                    # if task status is not in SUCCESS_STATUSES then it could be eligible for run
                    if not task.status in constants.SUCCESS_STATUSES :
                        ret = False
        return ret


    def run(self, output_func, phasename, wfsys, task,
                  alwaysRun, options):
        """ Runs a set of tasks in parallel
            Arguments:
                output_func: Method for writing status to, which takes
                             arguments, line to write and boolean indicating
                             if end of line
            Returns:
                WorkflowStatus
        """
        sequenceThreads = []
        stoppedThreads = []
        spinnerThread = None
        statusQueue = multiprocessing.Queue()
        try:
            log.info("PARALLEL_TASK %s: START" % \
                     (self.getId()))
            if not options.nospinner:
                spinnerThread = utils.SpinnerThread(output_func, False)
                spinnerThread.start()

            # Start a thread per sequence that is not already success
            for i in range(len(self.sequences)):
                host_colour = constants.Colours.host_colours[i % \
                                  len(constants.Colours.host_colours)]
                self.sequences[i].makeReadyForProcessing()
                seqTask = task
                if task == self.getId():
                    # If task asked to run is whole parallel task
                    # then no need to send specific task id to
                    # sequence
                    seqTask = None
                sequenceThread = SequenceProcess(self.sequences[i],
                                 output_func, phasename, wfsys,
                                 host_colour, seqTask, alwaysRun,
                                 options, statusQueue)
                if sequenceThread.willRun():
                    log.log(constants.TRACE,
                           "Starting thread for sequence {0}".format(\
                           self.sequences[i].id))
                    sequenceThreads.append(sequenceThread)
                    sequenceThread.start()
                    stoppedThreads.append(False)
                else:
                    log.log(constants.TRACE,
                           "Log only for sequence {0}".format(\
                           self.sequences[i].id))
                    sequenceThreads.append(None)
                    sequenceThread.log_only()
                    stoppedThreads.append(True)

            log.log(constants.TRACE, "Wait for threads to complete")
            allStopped = False
            while not allStopped:
                # Check if got a status update
                try:
                    queueObj = statusQueue.get(False)
                    log.log(constants.TRACE, "Got object from queue")
                    queueObj.process(self.sequences, wfsys, options)
                except Queue.Empty as e:
                    log.log(constants.TRACE, "Queue empty")
                    pass
                someAlive = False
                for i in range(len(self.sequences)):
                    if stoppedThreads[i] == False:
                        if sequenceThreads[i].is_alive():
                            log.log(constants.TRACE,
                              "Thread {0} is alive".format(i))
                            someAlive = True
                        else:
                            log.log(constants.TRACE,
                               "Thread {0} is stopped".format(i))
                            stoppedThreads[i] = True
                if not someAlive:
                    allStopped = True
                else:
                    time.sleep(2)

            log.log(constants.TRACE, "Processes are stopped so now join")
            for i in range(len(self.sequences)):
                if sequenceThreads[i] != None:
                    sequenceThreads[i].join()
            log.log(constants.TRACE, "Joined with all processes")

            readQueue = False
            while not readQueue:
                try:
                    queueObj = statusQueue.get(False)
                    log.log(constants.TRACE,
                            "Got object from queue after stopped")
                    queueObj.process(self.sequences, wfsys, options)
                except Queue.Empty as e:
                    readQueue = True
            statusQueue.close()

        finally:
            if spinnerThread != None:
                spinnerThread.stop()
                spinnerThread.join()
                spinnerThread = None
            log.info("PARALLEL_TASK %s: END\n" % \
                     (self.getId()))
        wfstatus = None
        for i in self.sequences:
            log.log(constants.TRACE, "Found status {0} for seq {1}".\
                      format(i.wfstatus.value, i.id))
            if i.wfstatus.value == 'f':
                wfstatus = WorkflowStatus.FAILED
            elif i.wfstatus.value == 'c' and wfstatus != WorkflowStatus.FAILED:
                wfstatus = WorkflowStatus.COMPLETE
        return WorkflowStatus(wfstatus, "")

    def getCounts(self):
        """ Returns tuple of numSuccess, numFailed, numSkipped related to
            how many tasks succeeded, failed, skipped. Counts values
            from each sequence it ran"""
        numSuccess = 0
        numFailed = 0
        numSkipped = 0
        for a in self.sequences:
            (incSuccess, incFailed, incSkipped) = a.getCounts()
            numSuccess = numSuccess + incSuccess
            numFailed = numFailed + incFailed
            numSkipped = numSkipped + incSkipped

        return (numSuccess, numFailed, numSkipped)

    def shouldRunOnHost(self, servertype, servername, excluded, inputmgr,
                              force, exact_match):
        """ We should run if any of the tasks in our sequences say to run
        """
        run_on_server = False
        for seq in self.sequences:
            for i in range(len(seq.tasks)):
                task = seq.tasks[i]
                if task.shouldRunOnHost(servertype, servername,
                                        excluded, inputmgr, force,
                                        exact_match):
                    run_on_server = True
                    seq.should_run_task[i] = run_on_server

        return run_on_server

    def getTaskStatusList(self, taskid):
        # returns task status object, related to this task
        taskList = []
        for seq in self.sequences:
            for task in seq.tasks:
                if task.task.name == taskid:
                    taskList.append(task)
        return taskList

    def getCmd(self):
        return "PARALLEL"


class SequenceStatusTask(StatusTask):
    """ Represents a sequence of tasks within parallel set with status """
    def __init__(self, task, host):
        """ Initialises StatusTask
            Arguments:
                task: SequenceTask object, only used for its id
                host: Host object
        """
        StatusTask.__init__(self, task, constants.INITIAL)
        self.host = host
        self.tasks = []  # Array of FabricStatusTasks
        # Array of whether to run given server choice
        self.should_run_task = []
        self.id = "{0}:{1}".format(self.task.name, self.host.hostname)

    def setStatus(self, status):
        """ Update all tasks with status, used to inform that are skipping
            whole parallel task"""
        for task in self.tasks:
            if task.status not in constants.SUCCESS_STATUSES:
                task.setStatus(status)

    def populateTree(self, element, writeHostParams):
        """ Populates tag element with task """
        seq = etree.SubElement(element, "sequencestatus")
        log.log(constants.TRACE, "Populating sequence with {0}".format(\
                self.task.name))
        seq.attrib["id"] = self.task.name
        seq.attrib["host"] = self.host.hostname
        seq.attrib["server"] = self.host.servertype
        for task in self.tasks:
            task.populateTree(seq, writeHostParams)

    def hasTask(self, taskid):
        for task in self.tasks:
            if task.task.name == taskid:
                return True
        return False

    def getTaskStatus(self, taskid):
        for task in self.tasks:
            if task.task.name == taskid:
                return task.status
        return constants.INITIAL

    def getId(self):
        """ Returns id that represents this task
        """
        return self.id

    def addTask(self, task):
        """ Adds tasks to tasks and updates status """
        self.tasks.append(task)
        self.should_run_task.append(False)

    def makeReadyForProcessing(self):
        """ Makes ready for processing, by creating a shared array object
            statuses that can access from main and subprocess.
            Also creates wfstatus with overall workflow status"""
        manager = multiprocessing.Manager()
        self.hostparams = manager.dict()
        self.wfstatus = multiprocessing.Value('c',
                            self.getWfValue(self.status))

    def getWfValue(self, wfstatus):
        """ Returns the single char representation of workflow status """
        if wfstatus == WorkflowStatus.COMPLETE:
            return 'c'
        elif wfstatus == WorkflowStatus.FAILED:
            return 'f'
        elif wfstatus == WorkflowStatus.USER_INPUT:
            return 'i'
        else:
            return 'u'

    def getCounts(self):
        """ Returns tuple of numSuccess, numFailed, numSkipped related to
            how many tasks succeeded, failed, skipped. """
        numSuccess = 0
        numFailed = 0
        numSkipped = 0
        for a in self.tasks:
            (incSuccess, incFailed, incSkipped) = \
                            utils.getStatusCount(a.status, a.task.name, log)
            numSuccess = numSuccess + incSuccess
            numFailed = numFailed + incFailed
            numSkipped = numSkipped + incSkipped
        return (numSuccess, numFailed, numSkipped)


class DummyResult:
    """ Pretends to be a fabric result for when we run tasks
        locally"""
    def __init__(self):
        self.succeeded = False
        self.failed = True
        self.stdout = ""
        self.stderr = ""
        self.return_code = -1


class SequenceProcess(multiprocessing.Process):
    def __init__(self, sequence, outputfunc, phasename, wfsys,
                       host_colour, task, alwaysRun, options,
                       queue):
        super(SequenceProcess, self).__init__()
        self.output_func = outputfunc
        self.phasename = phasename
        self.seq = sequence
        self.status = None
        self.logger = logging.getLogger('sub.wfeng')
        self.wfsys = wfsys
        self.host_colour = host_colour
        self.task = task
        self.alwaysRun = alwaysRun
        self.options = options
        self.queue = queue

    def run(self):
        """ Runs each of its tasks sequentially unless task
            is specified"""
        try:
            for i in range(len(self.seq.tasks)):
                hostip = self.seq.tasks[i].host.ipaddr
                if self.seq.tasks[i].task.servertype == constants.LOCAL or \
                    self.seq.tasks[i].task.run_local == True:
                    hostip = constants.LOCAL
                hoststr = " on {0}".format(hostip)

                self.seq.should_run_task[i] = self._task_will_run(i)
                if not self.seq.should_run_task[i]:
                    if self.seq.tasks[i].status not in \
                                     constants.SUCCESS_STATUSES:
                        self.seq.tasks[i].status = constants.SKIPPED
                if self.seq.should_run_task[i] == False:
                    utils.logSkippedTask(self.logger, self.seq.tasks[i],
                        hoststr)
                    self.status = WorkflowStatus(WorkflowStatus.COMPLETE, "")
                else:
                    self.logger.log(constants.TRACE,
                         "Calling task {0}".format(self.seq.tasks[i].getId()))
                    self.status = self.seq.tasks[i].run(self.output_func,
                                                self.phasename, self.wfsys,
                                                self.task,
                                                self.alwaysRun,
                                                self.options,
                                                True,
                                                self.logger,
                                                self.host_colour)

                durVal = None
                if self.seq.tasks[i].actualDurationInt != -1:
                    durVal = self.seq.tasks[i].actualDurationInt
                statusobj = StatusObject(self.seq.id, i,
                                self.seq.tasks[i].status,
                                durVal, self.seq.host.params)
                self.logger.log(constants.TRACE,
                   "Adding {0} to queue with status {1},seq{2},ind{3}".format(\
                   self.seq.tasks[i].getId(),
                   self.seq.tasks[i].status, self.seq.id, i))
                self.queue.put(statusobj, True)
                if self.status.status != WorkflowStatus.COMPLETE:
                    # Stop at first one that doesn't indicate it completed
                    self.logger.log(constants.TRACE,
                       "Sequence {0} stopping as not complete".format(\
                              self.seq.id))
                    self.seq.wfstatus.value = \
                          self.seq.getWfValue(self.status.status)
                    self.logger.log(constants.TRACE,
                      "Set status for seq {0} to {1}".format(self.seq.id,
                            self.seq.wfstatus.value))
                    return

            self.logger.log(constants.TRACE,
                  "Sequence {0} completed".format(self.seq.id))
            self.seq.wfstatus.value = self.seq.getWfValue(self.status.status)
            self.logger.log(constants.TRACE,
                  "Set status for seq {0} to {1}".format(self.seq.id,
                            self.seq.wfstatus.value))
        finally:
            with settings(
                hide('everything', 'aborts', 'status')
            ):
                disconnect_all()
            self.queue.close()
        return

    def willRun(self):
        """ Returns if there will be tasks to run"""
        will_run = False
        for i in range(len(self.seq.tasks)):
            if self._task_will_run(i):
                will_run = True
        return will_run

    def _task_will_run(self, i):
        """ Returns whether this task needs to be run.
            Arguments:
               i, index into tasks array """

        will_run = True
        if not self.alwaysRun and \
            self.seq.tasks[i].status in constants.SUCCESS_STATUSES:
            will_run = False
        elif self.seq.should_run_task[i] == False:
            will_run = False
        elif self.seq.should_run_task[i] == True and \
              self.seq.tasks[i].hasDependency():
            dependencies = self.seq.tasks[i].task.dependency.split(",")
            for dep in dependencies:
                # If dependency in this sequence then get its status
                if self.seq.hasTask(dep):
                    dstatus = self.seq.getTaskStatus(dep)
                else:
                    depTask = self.wfsys.getTask(dep)
                    # Dependant on task on all nodes unless this task is in
                    # this sequence, or depsinglehost was set
                    dstatus = constants.SKIPPED
                    if depTask != None:
                        hostsToCheck = constants.ALL
                        if self.seq.tasks[i].task.depsinglehost:
                            hostsToCheck = self.seq.tasks[i].host.hostname
                        dstatus = self.wfsys.getTaskStatus(dep,
                          hostsToCheck)
                        log.log(constants.TRACE,
                           "Dependency {0} on {1} status {2}".format(\
                            depTask.name, hostsToCheck, dstatus))
                if dstatus not in constants.SUCCESS_STATUSES:
                    log.debug(\
                       "Skipping task %s as dependency %s not passed %s" \
                       % (self.seq.tasks[i].task.name, dep,
                       dstatus))
                    will_run = False
                    break
        if self.seq.should_run_task[i] and self.task != None:
            if self.task != self.seq.tasks[i].task.name:
                will_run = False

        return will_run

    def log_only(self):
        """ Logs each of its task as have determined they all
            will be skipped"""
        for i in range(len(self.seq.tasks)):
            hostip = self.seq.tasks[i].host.ipaddr
            if self.seq.tasks[i].task.servertype == constants.LOCAL or \
                self.seq.tasks[i].task.run_local == True:
                hostip = constants.LOCAL
            hoststr = " on {0}".format(hostip)

            if self.seq.tasks[i].status not in \
                                     constants.SUCCESS_STATUSES:
                self.seq.tasks[i].status = constants.SKIPPED
            utils.logSkippedTask(self.logger, self.seq.tasks[i],
                        hoststr)
            self.status = WorkflowStatus(WorkflowStatus.COMPLETE, "")

        self.logger.log(constants.TRACE,
                  "Sequence {0} completed".format(self.seq.id))
        self.seq.wfstatus.value = self.seq.getWfValue(self.status.status)
        self.logger.log(constants.TRACE,
                  "Set status for seq {0} to {1}".format(self.seq.id,
                            self.seq.wfstatus.value))
        return


class StatusObject(object):

    def __init__(self, seqname, taskindex, status, duration, hostparams):
        self.seqname = seqname
        self.taskindex = taskindex
        self.status = status
        self.duration = duration
        self.hostparams = hostparams

    def process(self, sequences, wfsys, options):
        """ Update sequences with status """
        seq = None
        for a in sequences:
            if a.id == self.seqname:
                seq = a
        if seq == None:
            log.error("Internal error, failed to find seq {0}".format(seqname))
            return
        log.log(constants.TRACE,
               "Removed {0} from queue with status {1},seq{2},ind{3}".format(\
               seq.tasks[self.taskindex].getId(),
               self.status, seq.id, self.taskindex))
        seq.tasks[self.taskindex].status = self.status
        if self.duration != None:
            seq.tasks[self.taskindex].actualDuration = \
                "{0}".format(datetime.timedelta(seconds=self.duration))
            for key, val in self.hostparams.items():
                seq.host.add_param(key, val)
        if options.list:
            log.debug("Writing results of listing to %s%s" % (options.getSysStatusName(), constants.LISTFILE_SUFFIX))
            wfsys.write("%s%s" %(options.getSysStatusName(), constants.LISTFILE_SUFFIX))
        else:
            wfsys.write(options.getSysStatusName())


"""Represents the different task objects
@copyright: Ammeon Ltd
"""
import constants
import logging
import utils
import wfconfig
from lxml import etree

from task import WTask, StatusTask, WorkflowStatus

log = logging.getLogger(__name__)


class MsgTask(WTask):
    """ Msg task - abstract class which holds a name and msg"""
    def __init__(self, name, config, msg, hosts, server,
                 swversion, osversion, dependency, optional,
                 depsinglehost, checkparams):
        """Initialises MsgTask object"""
        WTask.__init__(self, name, config)
        self.msg = msg
        self.hosts = hosts
        self.servertype = server
        self.dependency = dependency
        self.checkparams = checkparams
        self.optional = optional
        self.depsinglehost = depsinglehost
        self.swversion = swversion
        self.osversion = osversion

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
        if not isinstance(task, MsgTask):
            log.debug("Task is not a MsgTask %s" % task.name)
            return False
        if self.msg != task.msg:
            log.debug("Msg differ %s/%s for %s" %
                      (self.msg, task.msg, self.name))
            return False
        if self.servertype != task.servertype:
            log.debug("Server type differs %s/%s" %
                      (self.servertype, task.servertype))
            return False
        if self.dependency != task.dependency:
            log.debug("Dependency differs %s/%s" %
                      (self.dependency, task.dependency))
            return False
        if self.checkparams != task.checkparams:
            log.debug("Checkparams differ %s/%s for %s" %
                      (self.checkparams, task.checkparams, self.name))
            return False
        if self.swversion != task.swversion:
            log.debug("Version differ %s/%s for %s" %
                      (self.swversion, task.swversion, self.name))
            return False
        if self.osversion != task.osversion:
            log.debug("Version differ %s/%s for %s" %
                      (self.osversion, task.osversion, self.name))
            return False
        return True

    def __str__(self):
        return "ID=%s,MSG=%s" % (self.name, self.msg)

    def needsHost(self):
        """ Returns if this task applies only to particular hosts"""
        return True


class EscapeTask(MsgTask):
    """ Escape task - escapes workflow"""
    def __init__(self, name, config, msg, hosts, server,
                 swversion, osversion, dependency, optional,
                 depsinglehost, checkparams):
        """Initialises escape object"""
        MsgTask.__init__(self, name, config, msg, hosts, server,
                         swversion, osversion, dependency, optional,
                         depsinglehost, checkparams)

    def copy(self, server):
        """ Returns copy of task but with different servertype """
        return EscapeTask(self.name, self.config, self.msg, self.hosts,
                          server, self.swversion, self.osversion,
                          self.dependency, self.optional,
                          self.depsinglehost, self.checkparams)

    def getStatusTasks(self, host):
        """ Returns a list of StatusTask objects in order to be processed.
            Arguments:
                host: Host to run on, will be ignored
            Returns:
                list of StatusTask classes
        """
        tasks = [EscapeStatusTask(self, host, constants.INITIAL)]
        return tasks

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
        if not MsgTask.equals(self, task):
            return False
        if not isinstance(task, EscapeTask):
            log.debug("Task is not an EscapeTask %s" % task.name)
            return False
        return True


class MsgStatusTask(StatusTask):
    """ Represents a generic msg task with status """
    def __init__(self, task, host, status):
        """ Initialises StatusTask
            Arguments:
                task: MsgTask object
                status: String with status
        """
        StatusTask.__init__(self, task, status)
        self.host = host

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

    def hasHost(self):
        """ Returns if this status task applies only to particular hosts"""
        return True

    def getHosts(self):
        """ Returns the hosts this applies to """
        return [self.host]

    def hasDependency(self):
        """ Returns if this StatusTask is dependant on another"""
        return self.task.dependency is not None

    def getId(self):
        """ Returns id that represents this task, will be of format
            <taskid>_<hostname>"""
        return "%s_%s" % (self.task.name, self.host.hostname)

    def getSWVersion(self):
        """ Returns the swversion associated with this task, or None if unknown
            Returns:
                String representing the swver or None if swversion unknown
        """
        swkey = self.task.config.cfg[wfconfig.SWVER]
        if swkey not in self.host.params:
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
        if oskey not in self.host.params:
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


class EscapeStatusTask(MsgStatusTask):
    """ Represents a escape task with status """
    def __init__(self, task, host, status):
        """ Initialises StatusTask
            Arguments:
                task: MsgTask object
                status: String with status
        """
        MsgStatusTask.__init__(self, task, host, status)

    def isEquivalent(self, stask):
        """ Compares this StatusTask with that described by stask, and
            if they are the same ignoring status then they are equivalent
            Arguments:
                stask: StatusTask to compare against
            Returns:
                True: if same ignoring status
                False: if different
        """
        if not MsgStatusTask.isEquivalent(self, stask):
            return False
        if not isinstance(stask, EscapeStatusTask):
            log.debug("Task is not a EscapeStatusTask %s" % stask.task.name)
            return False
        return True

    def run(self, output_func, phasename, wfsys, task,
            alwaysRun, options):
        """ Runs a pause task
            Arguments:
                output_func: Method for writing status to, which takes
                             arguments, line to write and boolean indicating
                             if end of line
            Returns:
                WorkflowStatus
        """

        self.status = constants.SUCCESS
        # Assuming here that a terminal is 80 characters wide.
        # This should be changed to match the term_size variable
        # in the workflow engine.
        asterisk = "{0:*^80}"
        taskmsg = utils.extractIniParam(self.task.config.iniparams, self.task.msg)
        if taskmsg != self.task.msg:
            log.debug("Taken taskmsg\n%s\nfrom ini file parameter %s"
                      % (taskmsg, self.task.msg))
        log.info(asterisk.format(''))
        log.info("TASK %s: %s\n" % (self.getId(), taskmsg))
        log.info("RESULT %s: Escaping ...\n" % self.getId())
        log.info(asterisk.format(''))
        return WorkflowStatus(WorkflowStatus.STOPPED, "")

    def populateTree(self, element, writeHostParams):
        """ Populates phase element with task """
        status = etree.SubElement(element, "escapestatus")
        log.log(constants.TRACE, "Populating ESCAPE %s" % self.task)
        status.attrib["id"] = self.task.name
        status.attrib["msg"] = self.task.msg
        status.attrib["status"] = self.status
        status.attrib["host"] = self.host.hostname
        status.attrib["server"] = self.task.servertype
        utils.populate_optional(status, self.task.dependency,
                                "dependency")
        utils.populate_boolean(status, self.task.optional,
                               "optional")
        utils.populate_boolean(status, self.task.depsinglehost,
                               "depsinglehost")
        utils.populate_dictionary(status, self.task.checkparams, "checkparams")
        utils.populate_optional(status, self.task.swversion, "swversion")
        utils.populate_optional(status, self.task.osversion, "osversion")

    def getCmd(self):
        return "ESCAPE"


class PauseTask(MsgTask):
    """ Pause task, asks if user wants to pause or not"""
    def __init__(self, name, config, msg, hosts, server,
                 swversion, osversion, dependency, optional,
                 depsinglehost, checkparams):
        """Initialises pause object"""
        MsgTask.__init__(self, name, config, msg, hosts, server,
                         swversion, osversion, dependency, optional,
                         depsinglehost, checkparams)

    def copy(self, server):
        """ Returns copy of task but with different servertype """
        return PauseTask(self.name, self.config, self.msg, self.hosts,
                         server, self.swversion, self.osversion,
                         self.dependency, self.optional,
                         self.depsinglehost, self.checkparams)

    def getStatusTasks(self, host):
        """ Returns a list of StatusTask objects in order to be processed.
            Arguments:
                host: Host to run on, will be ignored
                status: current status
            Returns:
                list of StatusTask classes
        """
        tasks = [PauseStatusTask(self, host, constants.INITIAL)]
        return tasks

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
        if not MsgTask.equals(self, task):
            return False
        if not isinstance(task, PauseTask):
            log.debug("Task is not a PauseTask %s" % task.name)
            return False
        return True


class PauseStatusTask(MsgStatusTask):
    """ Represents a pause task with status """
    def __init__(self, task, host, status):
        """ Initialises StatusTask
            Arguments:
                task: PauseTask object
                status: String with status
        """
        MsgStatusTask.__init__(self, task, host, status)

    def isEquivalent(self, stask):
        """ Compares this StatusTask with that described by stask, and
            if they are the same ignoring status then they are equivalent
            Arguments:
                stask: StatusTask to compare against
            Returns:
                True: if same ignoring status
                False: if different
        """
        if not MsgStatusTask.isEquivalent(self, stask):
            return False
        if not isinstance(stask, PauseStatusTask):
            log.debug("Task is not a PauseStatusTask %s" % stask.task.name)
            return False
        return True

    def run(self, output_func, phasename, wfsys, task,
            alwaysRun, options):
        """ Asks users whether to pause or not
            Arguments:
                output_func: Method for writing status to, which takes
                             arguments, line to write and boolean indicating
                             if end of line
            Returns:
                True if should continue
                False if should stop
        """
        self.status = constants.SUCCESS
        # Assuming here that a terminal is 80 characters wide.
        # This should be changed to match the term_size variable
        # in the workflow engine.
        asterisk = "{0:*^80}"
        taskmsg = utils.extractIniParam(self.task.config.iniparams, self.task.msg)
        if taskmsg != self.task.msg:
            log.debug("Taken taskmsg\n%s\nfrom ini file parameter %s"
                      % (taskmsg, self.task.msg))
        msg = asterisk.format("") + "\n" + \
            "TASK %s: %s (y/n)\n" % (self.getId(), taskmsg)
        success_msg = "RESULT %s: Continuing" % self.getId() + "\n" +\
                      asterisk.format('')
        return WorkflowStatus(WorkflowStatus.USER_INPUT, msg, success_msg)

    def populateTree(self, element, writeHostParams):
        """ Populates phase element with task """
        status = etree.SubElement(element, "pausestatus")
        log.log(constants.TRACE, "Populating PAUSE %s" % self.task)
        status.attrib["id"] = self.task.name
        status.attrib["msg"] = self.task.msg
        status.attrib["status"] = self.status
        status.attrib["host"] = self.host.hostname
        status.attrib["server"] = self.task.servertype
        utils.populate_optional(status, self.task.dependency, "dependency")
        utils.populate_boolean(status, self.task.optional, "optional")
        utils.populate_boolean(status, self.task.depsinglehost,
                               "depsinglehost")
        utils.populate_dictionary(status, self.task.checkparams, "checkparams")
        utils.populate_optional(status, self.task.swversion, "swversion")
        utils.populate_optional(status, self.task.osversion, "osversion")

    def getCmd(self):
        return "PAUSE"


class NoticeTask(MsgTask):
    """ Notice task, displays a message to the user"""
    def __init__(self, name, config, msg, hosts, server,
                 swversion, osversion, dependency, optional,
                 depsinglehost, checkparams):
        """Initialises pause object"""
        MsgTask.__init__(self, name, config, msg, hosts, server,
                         swversion, osversion, dependency, optional,
                         depsinglehost, checkparams)

    def copy(self, server):
        """ Returns copy of task but with different servertype """
        return NoticeTask(self.name, self.config, self.msg, self.hosts,
                          server, self.swversion, self.osversion,
                          self.dependency, self.optional,
                          self.depsinglehost, self.checkparams)

    def getStatusTasks(self, host):
        """ Returns a list of StatusTask objects in order to be processed.
            Arguments:
                host: Host to run on, will be ignored
                status: current status
            Returns:
                list of StatusTask classes
        """
        tasks = [NoticeStatusTask(self, host, constants.INITIAL)]
        return tasks

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
        if not MsgTask.equals(self, task):
            return False
        if not isinstance(task, NoticeTask):
            log.debug("Task is not a NoticeTask %s" % task.name)
            return False
        return True


class NoticeStatusTask(MsgStatusTask):
    """ Represents a notice task with status """
    def __init__(self, task, host, status):
        """ Initialises StatusTask
            Arguments:
                task: NoticeTask object
                status: String with status
        """
        MsgStatusTask.__init__(self, task, host, status)

    def isEquivalent(self, stask):
        """ Compares this StatusTask with that described by stask, and
            if they are the same ignoring status then they are equivalent
            Arguments:
                stask: StatusTask to compare against
            Returns:
                True: if same ignoring status
                False: if different
        """
        if not MsgStatusTask.isEquivalent(self, stask):
            return False
        if not isinstance(stask, NoticeStatusTask):
            log.debug("Task is not a NoticeStatusTask %s" % stask.task.name)
            return False
        return True

    def run(self, output_func, phasename, wfsys, task,
            alwaysRun, options):
        """ Displays a notice to the user
            Arguments:
                output_func: Method for writing status to, which takes
                             arguments, line to write and boolean indicating
                             if end of line
            Returns:
                True if should continue
                False if should stop
        """

        self.status = constants.SUCCESS
        # Assuming here that a terminal is 80 characters wide.
        # This should be changed to match the term_size variable
        # in the workflow engine.


        asterisk = "{0:*^80}"
        taskmsg = utils.extractIniParam(self.task.config.iniparams, self.task.msg)
        if taskmsg != self.task.msg:
            log.debug("Taken taskmsg\n%s\nfrom ini file parameter %s"
                      % (taskmsg, self.task.msg))
        log.info(asterisk.format(''))
        log.info("TASK %s: Notice\n" % self.getId())
        log.info(taskmsg)
        log.info("\nRESULT %s: Complete" % self.getId())
        log.info(asterisk.format(''))
        return WorkflowStatus(WorkflowStatus.COMPLETE, "")


    def populateTree(self, element, writeHostParams):
        """ Populates phase element with task """
        status = etree.SubElement(element, "noticestatus")
        log.log(constants.TRACE, "Populating NOTICE %s" % self.task)
        status.attrib["id"] = self.task.name
        status.attrib["msg"] = self.task.msg
        status.attrib["status"] = self.status
        status.attrib["host"] = self.host.hostname
        status.attrib["server"] = self.task.servertype
        utils.populate_optional(status, self.task.dependency, "dependency")
        utils.populate_boolean(status, self.task.optional, "optional")
        utils.populate_boolean(status, self.task.depsinglehost,
                               "depsinglehost")
        utils.populate_dictionary(status, self.task.checkparams, "checkparams")
        utils.populate_optional(status, self.task.swversion, "swversion")
        utils.populate_optional(status, self.task.osversion, "osversion")

    def getCmd(self):
        return "NOTICE"

"""Represents the different task objects
@copyright: Ammeon Ltd
"""
from wfeng import constants
import logging
from wfeng import utils
from wfeng import wfconfig
from lxml import etree
import re

from wfeng.taskcommons import WTask, StatusTask
from wfeng.status import WorkflowStatus

log = logging.getLogger(__name__)


class MsgTask(WTask):
    """ Msg task - abstract class which holds a name and msg
    """
    def __init__(self, name, config, msg, hosts, server,
                 swversion, osversion, dependency, optional,
                 depsinglehost, checkparams, gid=None, dynamic=False):
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
        self.dynamic = dynamic
        self.gid = gid

    def hasVersion(self):
        return True

    def isDynamic(self):
        return self.dynamic

    def equals(self, task):
        """ Compares this Task with that described by task, and
            returns if they are the same. It ignores the hosts parameter
            as when this is part of a StatusTask the hosts is irrelevant, as
            it will have been expanded to a Host object

            Args:
                task: Task to compare against
            Returns:
                boolean: True if same, False if different
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
        if self.gid != task.gid:
            log.debug("Group id differ {0}/{1} for {2}".format(
                      self.gid, task.gid, self.name))
            return False
        if self.swversion != task.swversion:
            log.debug("Version differ %s/%s for %s" %
                      (self.swversion, task.swversion, self.name))
            return False
        if self.osversion != task.osversion:
            log.debug("Version differ %s/%s for %s" %
                      (self.osversion, task.osversion, self.name))
            return False
        if self.dynamic != task.dynamic:
            log.debug("Dynamic differ %s/%s for %s" %
                      (self.dynamic, task.dynamic, self.name))
            return False
        return True

    def getLogStr(self, host):
        return "Running %s" % self.getCmdHostLogStr(host)

    def getCmdHostLogStr(self, host):
        return "Message task on %s" % (host.ipaddr)

    def __str__(self):
        return "ID=%s,MSG=%s" % (self.name, self.msg)

    def needsHost(self):
        """ Returns if this task applies only to particular hosts"""
        return True


class EscapeTask(MsgTask):
    """ Escape task - escapes workflow"""
    def __init__(self, name, config, msg, hosts, server,
                 swversion, osversion, dependency, optional,
                 depsinglehost, checkparams, gid=None, dynamic=False):
        """Initialises escape object"""
        MsgTask.__init__(self, name, config, msg, hosts, server,
                         swversion, osversion, dependency, optional,
                         depsinglehost, checkparams, gid, dynamic)

    def copy(self, server):
        """ Returns copy of task but with different servertype """
        return EscapeTask(self.name, self.config, self.msg, self.hosts,
                          server, self.swversion, self.osversion,
                          self.dependency, self.optional,
                          self.depsinglehost, self.checkparams,
                          self.gid, self.dynamic)

    def getStatusTasks(self, host):
        """ Returns a list of StatusTask objects in order to be processed.

            Args:
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

            Args:
                task: Task to compare against
            Returns:
                boolean: True if same, False if different
        """
        if not MsgTask.equals(self, task):
            return False
        if not isinstance(task, EscapeTask):
            log.debug("Task is not an EscapeTask %s" % task.name)
            return False
        return True

    def getCmdHostLogStr(self, host):
        return "Escape on %s" % (host.ipaddr)


class MsgStatusTask(StatusTask):
    """ Represents a generic msg task with status """
    def __init__(self, task, host, status):
        """ Initialises StatusTask

            Args:
                task: MsgTask object
                status: String with status
        """
        StatusTask.__init__(self, task, status)
        self.host = host

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
        if not self.host.equals(stask.host):
            log.debug("Host %s didn't match %s" % (self.host.hostname,
                                                  stask.host.hostname))
            return False
        return True

    def hasHost(self):
        """ Returns if this status task applies only to particular hosts"""
        return True

    def getHosts(self):
        """ Returns the hosts this applies to """
        return [self.host]

    def logDetails(self):
        log.info("TASK %s: %s ..." % \
                     (self.getId(), self.task.getLogStr(self.host)))
        self.logged = True

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

    def manualFix(self):
        """
        sets status to manual fix and then returns completed workflow status
        """
        genid = self.getId()
        log.debug("Manually fixing message task %s" % genid)
        self.status = constants.MANUAL_FIX
        status_colour = constants.COLOURS.status[self.status]
        log.info("%s%s%s TASK %s: %s\n" % \
                                   (status_colour, self.status,
                                    constants.COLOURS.END, genid,
                                    self.task.getCmdHostLogStr(self.host)))
        return WorkflowStatus(WorkflowStatus.COMPLETE, "")


class EscapeStatusTask(MsgStatusTask):
    """ Represents a escape task with status """
    def __init__(self, task, host, status):
        """ Initialises StatusTask

            Args:
                task: MsgTask object
                status: String with status
        """
        MsgStatusTask.__init__(self, task, host, status)

    def isEquivalent(self, stask):
        """ Compares this StatusTask with that described by stask, and
            if they are the same ignoring status then they are equivalent

            Args:
                stask: StatusTask to compare against
            Returns:
                boolean: True if same ignoring status, False if different
        """
        if not MsgStatusTask.isEquivalent(self, stask):
            return False
        if not isinstance(stask, EscapeStatusTask):
            log.debug("Task is not a EscapeStatusTask %s" % stask.task.name)
            return False
        return True

    def run(self, output_func, phasename, wfsys, tasklist,
            alwaysRun, options):
        """ Runs a pause task

            Args:
                output_func: Method for writing status to, which takes
                arguments, line to write and boolean indicating
                if end of line
            Returns:
                WorkflowStatus
        """
        if options is not None and  options.fix:
            return self.manualFix()

        self.status = constants.SUCCESS
        # Assuming here that a terminal is 80 characters wide.
        # This should be changed to match the term_size variable
        # in the workflow engine.
        asterisk = "{0:*^80}"
        taskmsg = utils.extractIniParam(self.task.config.iniparams,
                                                        self.task.msg)
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
        utils.populate_optional(status, self.task.gid, "gid")
        utils.populate_optional(status, self.task.swversion, "swversion")
        utils.populate_optional(status, self.task.osversion, "osversion")
        utils.populate_boolean(status, self.task.dynamic, "dynamic")

    def getCmd(self):
        return "ESCAPE"


class PauseTask(MsgTask):
    """ Pause task, asks if user wants to pause or not"""
    def __init__(self, name, config, msg, hosts, server,
                 swversion, osversion, dependency, optional,
                 depsinglehost, checkparams, gid=None, dynamic=False):
        """Initialises pause object"""
        MsgTask.__init__(self, name, config, msg, hosts, server,
                         swversion, osversion, dependency, optional,
                         depsinglehost, checkparams, gid, dynamic)

    def copy(self, server):
        """ Returns copy of task but with different servertype """
        return PauseTask(self.name, self.config, self.msg, self.hosts,
                         server, self.swversion, self.osversion,
                         self.dependency, self.optional,
                         self.depsinglehost, self.checkparams,
                         self.gid, self.dynamic)

    def getStatusTasks(self, host):
        """ Returns a list of StatusTask objects in order to be processed.

            Args:
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

            Args:
                task: Task to compare against
            Returns:
                boolean: True if same, False if different
        """
        if not MsgTask.equals(self, task):
            return False
        if not isinstance(task, PauseTask):
            log.debug("Task is not a PauseTask %s" % task.name)
            return False
        return True

    def getCmdHostLogStr(self, host):
        return "Pause on %s" % (host.ipaddr)


class PauseStatusTask(MsgStatusTask):
    """ Represents a pause task with status """
    def __init__(self, task, host, status):
        """ Initialises StatusTask

            Args:
                task: PauseTask object
                status: String with status
        """
        MsgStatusTask.__init__(self, task, host, status)

    def isEquivalent(self, stask):
        """ Compares this StatusTask with that described by stask, and
            if they are the same ignoring status then they are equivalent

            Args:
                stask: StatusTask to compare against
            Returns:
                boolean: True if same ignoring status, False if different
        """
        if not MsgStatusTask.isEquivalent(self, stask):
            return False
        if not isinstance(stask, PauseStatusTask):
            log.debug("Task is not a PauseStatusTask %s" % stask.task.name)
            return False
        return True

    def run(self, output_func, phasename, wfsys, tasklist,
            alwaysRun, options):
        """ Asks users whether to pause or not

            Args:
                output_func: Method for writing status to, which takes
                arguments, line to write and boolean indicating
                if end of line
            Returns:
                boolean: True if should continue, False if should stop
        """

        if options is not None and  options.fix:
            return self.manualFix()

        # Assuming here that a terminal is 80 characters wide.
        # This should be changed to match the term_size variable
        # in the workflow engine.
        asterisk = "{0:*^80}"
        taskmsg = utils.extractIniParam(self.task.config.iniparams,
                                        self.task.msg)
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
        utils.populate_optional(status, self.task.gid, "gid")
        utils.populate_optional(status, self.task.swversion, "swversion")
        utils.populate_optional(status, self.task.osversion, "osversion")
        utils.populate_boolean(status, self.task.dynamic, "dynamic")

    def getCmd(self):
        return "PAUSE"


class NoticeTask(MsgTask):
    """ Notice task, displays a message to the user"""
    def __init__(self, name, config, msg, hosts, server,
                 swversion, osversion, dependency, optional,
                 depsinglehost, checkparams, gid=None):
        """Initialises pause object"""
        MsgTask.__init__(self, name, config, msg, hosts, server,
                         swversion, osversion, dependency, optional,
                         depsinglehost, checkparams, gid)

    def copy(self, server):
        """ Returns copy of task but with different servertype """
        return NoticeTask(self.name, self.config, self.msg, self.hosts,
                          server, self.swversion, self.osversion,
                          self.dependency, self.optional,
                          self.depsinglehost, self.checkparams, self.gid)

    def getStatusTasks(self, host):
        """ Returns a list of StatusTask objects in order to be processed.

            Args:
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

            Args:
                task: Task to compare against
            Returns:
                boolean: True if same, False if different
        """
        if not MsgTask.equals(self, task):
            return False
        if not isinstance(task, NoticeTask):
            log.debug("Task is not a NoticeTask %s" % task.name)
            return False
        return True

    def getCmdHostLogStr(self, host):
        return "Notice on %s" % (host.ipaddr)


class NoticeStatusTask(MsgStatusTask):
    """ Represents a notice task with status """
    def __init__(self, task, host, status):
        """ Initialises StatusTask

            Args:
                task: NoticeTask object
                status: String with status
        """
        MsgStatusTask.__init__(self, task, host, status)

    def isEquivalent(self, stask):
        """ Compares this StatusTask with that described by stask, and
            if they are the same ignoring status then they are equivalent

            Args:
                stask: StatusTask to compare against
            Returns:
                boolean: True if same ignoring status, False if different
        """
        if not MsgStatusTask.isEquivalent(self, stask):
            return False
        if not isinstance(stask, NoticeStatusTask):
            log.debug("Task is not a NoticeStatusTask %s" % stask.task.name)
            return False
        return True

    def run(self, output_func, phasename, wfsys, tasklist,
            alwaysRun, options):
        """ Displays a notice to the user

            Args:
                output_func: Method for writing status to, which takes
                arguments, line to write and boolean indicating
                if end of line
            Returns:
                boolean: True if should continue, False if should stop
        """

        if options is not None and  options.fix:
            return self.manualFix()

        self.status = constants.SUCCESS
        # Assuming here that a terminal is 80 characters wide.
        # This should be changed to match the term_size variable
        # in the workflow engine.

        asterisk = "{0:*^80}"
        taskmsg = utils.extractIniParam(self.task.config.iniparams,
                                        self.task.msg)
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
        utils.populate_optional(status, self.task.gid, "gid")
        utils.populate_optional(status, self.task.swversion, "swversion")
        utils.populate_optional(status, self.task.osversion, "osversion")

    def getCmd(self):
        return "NOTICE"


class DynamicTaskValidator():
    """ Validation class for dynamic pause and escape
        Validates string entries for the various dynamic task fields
    """
    def __init__(self):
        """ Initialises DynamicTaskValidator
        """

    def validRefId(self, fieldStr, wfsys, msgs):
        """ validates reference task id

            Args:
                fieldStr: field value
                wfsys: the workflowsystem object containing existing tasks
                msgs: a list to contain messages for user
            Returns:
                boolean: True if valid, else False
        """
        if fieldStr is None:
            fieldStr = ""
        if fieldStr == "":
            msgs.append("Field cannot be empty")
            return False
        found = False
        reftaskinds = \
            wfsys.execute.getTaskIndices(fieldStr)[constants.TASK_LIST]
        if len(reftaskinds) != 0:
            found = True
        if not found:
            msgs.append("Unable to find valid reference task [%s] in "
                         "workflow execute phase" % \
                          fieldStr)
            return False
        return True

    def validHostsFormat(self, fieldStr, msgs):
        """ validates hosts field format against regular expression

            Args:
                fieldStr: field value
                msgs: a list to contain messages for user
            Returns:
                boolean: True if valid, else False
        """
        validity = True
        if fieldStr is not None:
            hostre = re.compile("\*$|[!]?[1-9][0-9]*$|[!]?[$]$")
            if not hostre.match(fieldStr):
                msgs.append("Host [%s] invalid. "
                            "Check format against user guide" % fieldStr)
                validity = False

        return validity

    def validHostsServer(self, hostsStr, serverStr, refId, wfsys, hosts, msgs):
        """ validates that the hosts and server entries are not inconsistent.
            ie that
            Server value is '*', local or within hosts file
            Hosts number if present is within the range of the number of hosts
            as constrained by server type
            if refId is in a group then hostsStr and ServerStr match with
            the entries on the refId task

            Args:
                hostsStr: the hosts value on the new task
                serverStr: the servertype value on the new task
                refId: the reference task
                wfsys: the workflow
                hosts: the hosts for the workflow
                msgs: a list to contain messages for user
            Returns:
                boolean: True if ok, otherwise False
        """
        validity = True
        log.debug("checking validity for hosts %s and servertype %s" % \
                    (hostsStr, serverStr))
        if serverStr == constants.ALL or serverStr == constants.LOCAL or \
                        serverStr in hosts.hosts:
            # if we are referencing a host by number then check it is within
            # range for the servertype specified
            hostvalre = re.compile("[!]?[1-9][0-9]*$")
            if hostvalre.match(hostsStr):
                if serverStr == "*":
                    serverTypeNum = len(hosts.hosts)
                else:
                    serverTypeNum = len(hosts.hosts[serverStr])
                if hostsStr.startswith('!'):
                    hostnum = int(hostsStr[1:])
                else:
                    hostnum = int(hostsStr)
                if hostnum > serverTypeNum:
                    msgs.append("Host [%s] invalid. "
                            "The host number is greater than the number of "
                            "hosts of server type [%s]" % \
                             (hostsStr, serverStr))
                    validity = False
        else:
            msgs.append("Server type [%s] invalid. "
                            "Must be all (*), or LOCAL, "
                             "or must be in hosts file" % \
                                         serverStr)
            msgs.append("Host [%s] cannot be validated as the server value"
                        " [%s] is not valid" % (hostsStr, serverStr))
            # return at this point as we do not have valid data to continue
            return False

        refTask = wfsys.execute.getTask(refId)
        if refTask is None:
            #at this point we must have a vaild reference id - therefore if
            # it is not found then we can be confident that it is a group
            # which means that the new task will be outside of the group
            pass
        # if the reference task is not in a group then
        # host and server cannot be inconsistent
        elif refTask.gid is None:
            pass
        #compare the fields
        else:
            # now we know we are dealing with a group, and so must assess
            # the hosts and server compatibility

            taskdict = wfsys.execute.getTaskIndices(refId)
            indRefs = taskdict[constants.TASK_LIST]

            #check server and hosts against reference task
            if len(indRefs) == 0:
                msgs.append("No reference tasks for insertion")
                validity = False
            else:
                log.debug(\
                    "num reference tasks found for dynamic insert is %s" % \
                    len(indRefs))

            #so now gather tasks host strings and the servertype
            hostslist = []
            refServertypes = []
            # can just take the first servertype as they will all be the same
            # and at this point we know the list of indRefs is > 0
            refServertypes = wfsys.execute.tasks[indRefs[0]].task.servertype
            for indRef in indRefs:
                log.debug("refsHostAndServer details are %s : %s" % \
                       (wfsys.execute.tasks[indRef].task.hosts,
                        wfsys.execute.tasks[indRef].task.servertype))
                hostslist.append(wfsys.execute.tasks[indRef].host.hostname)
                log.debug("adding host [%s] to the list" % \
                          wfsys.execute.tasks[indRef].host.hostname)

            if not serverStr == refServertypes:
                    msgs.append(\
                      "Server [%s] is not compatible with "
                        "group server type [%s]" % \
                        (serverStr,
                         wfsys.execute.tasks[indRef].task.servertype))
                    validity = False
            # now check that the list of hosts for dynamic task is consistent
            # with the list of hosts for our reference id
            if not serverStr == constants.ALL:
                dynhostsall = hosts.hosts[serverStr]
            else:
                dynhostsall = []
                servertypes = hosts.get_types()
                for stype in servertypes:
                    dynhostsall = dynhostsall + hosts.hosts[stype]
            # now that we have the list of hosts for the server type
            #   - need to apply any host limitations
            dynhosts = []
            if hostsStr == constants.ALL:
                for h in dynhostsall:
                    dynhosts.append(h)
            else:
                notNum = False
                serverNum = hostsStr
                if hostsStr.startswith("!"):
                    # get the number we are notting
                    notNum = True
                    serverNum = hostsStr[1:]
                if serverNum == "$":
                    # get last host
                    serverNum = len(dynhostsall)
                else:
                    serverNum = int(serverNum)
                if notNum:
                    for i in range(len(dynhostsall)):
                        if (i + 1) != serverNum:
                            dynhosts.append(dynhostsall[i])
                else:
                    dynhosts.append(dynhostsall[serverNum - 1])

            # now check that the two lists are equivalent
            dynhostnamelist = []
            for dynhost in dynhosts:
                dynhostnamelist.append(dynhost.hostname)
                log.debug("host for dynamic task is: %s" % dynhost.hostname)
                if dynhost.hostname not in hostslist:
                    msgs.append("hosts [%s] contains host [%s] "
                                "which is not compatible with the group "
                                "host list of [%s]" % \
                       (hostsStr, dynhost.hostname, hostslist))
                    validity = False
            log.debug("hosts for ref task are: %s" % hostslist)
            for refhost in hostslist:
                if refhost not in dynhostnamelist:
                    msgs.append("hosts [%s] does not contains host [%s] "
                                "and so is not compatible with the group "
                                "hosts list of [%s]" % \
                       (hostsStr, refhost, hostslist))
                    validity = False

        return validity

    def validPosition(self, fieldStr, msgs):
        """ validates position as before or after

        Args:
                fieldStr: field value
                msgs: a list to contain messages for user
        Returns:
            boolean: True if valid, False if invalid
        """
        if fieldStr == constants.DYNAMIC_BEFORE or \
               fieldStr == constants.DYNAMIC_AFTER:
            return True
        else:
            msgs.append("Entry [%s] invalid."
                        "Position selection must be [%s] or [%s]" % \
                 (fieldStr, constants.DYNAMIC_BEFORE, constants.DYNAMIC_AFTER))
            return False

    def validDependencies(self, fieldStr, wfsys, refid, pos, msgs):
        """ validates dependencies field

            Args:
                fieldStr: field value
                wfsys: the workflowsystem object containing existing tasks
                refid: the id that the dynamic task is to be positioned
                relative to
                pos: whether before or after the refid task
                msgs: a list to contain messages for user
            Returns:
                boolean: True if not empty and all entries valid
                of if empty, else False
        """
        validity = True
        if fieldStr is None:
            fieldStr = ""
        if fieldStr == "":
            return True

        depList = utils.split_commas(fieldStr)
        if len(depList) != 0:
            # first validate reference id and relative position for our task
            reftaskinds = \
                wfsys.execute.getTaskIndices(refid)[constants.TASK_LIST]
            if len(reftaskinds) == 0:
                msgs.append("Unable to find position of "
                                "refid [%s]" % refid)
                return False
            # limit search to before the position for new task
            if pos == constants.DYNAMIC_BEFORE:
                limiter = reftaskinds[0]
            elif pos == constants.DYNAMIC_AFTER:
                limiter = reftaskinds[0] + 1
            else:
                msgs.append("Unable to identify relative position "
                                 " of pos [%s] (must be before/after)" % pos)
                return False

            for dep in depList:
                depFound = False
                if None != wfsys.display.getTask(dep):
                    depFound = True
                elif None != wfsys.precheck.getTask(dep):
                    depFound = True
                else:
                    # get the index of the task (or enclosing parallel)
                    depInd = wfsys.execute.getTaskTopLevelInd(dep)
                    if depInd is not None:
                        if depInd < limiter:
                            depFound = True
                if not depFound:
                    msgs.append("Dependency [%s] invalid" % dep)
                    validity = False

        if validity == False:
            msgs.append("Dependency list [%s] not valid. "
                        "Must be valid task ids preceding this dynamic task "
                        "in the workflow" % \
                                fieldStr)

        return validity

    def validBooleanField(self, fieldStr, req, msgs):
        """ validates optional field to be true, false, or empty

            Args:
                fieldStr: field value
                req: if True then the value may not be empty
                msgs: a list to contain messages for user
            Returns:
                boolean: True if valid, else False
        """
        validity = False
        if fieldStr is None:
            fieldStr = ""
        fieldLower = fieldStr.lower()
        if req and fieldStr == "":
            msgs.append("Boolean field [%s] invalid. "
                           "This field is mandatory and cannot be empty" % \
                            fieldStr)
            return False
        fieldLower = fieldStr.lower()
        if fieldLower == "true" or fieldLower == "false" or fieldLower == "":
            validity = True
        else:
            msgs.append("Boolean field [%s] invalid. "
                            "If present must contain true/false" % fieldStr)
        return validity

    def validFreeTextLine(self, fieldStr, req, msgs):
        """ validates that free text does not include linefeed

            Args:
                fieldStr: field value
                req: boolean whether field is required (ie cannot be empty)
                msgs: a list to contain messages for user
            Returns:
                boolean: True if valid, else False
        """
        if fieldStr is None:
            fieldStr = ""
        if req and fieldStr == "":
            msgs.append("Field cannot be empty")
            return False
        if "\n" in fieldStr:
            msgs.append("Field must not contain linefeed" % fieldStr)
            return False
        return True

    def validCheckparams(self, fieldStr, msgs):
        """ validates checkparams field
            comma-separated list of key=value pairs

            Args:
                fieldStr: field value
                msgs: a list to contain messages for user
            Returns:
                boolean: True if valid, else False
        """
        validity = True
        if fieldStr is None:
            fieldStr = ""
        if fieldStr == "":
            return True
        pairs = fieldStr.split(',')
        for pair in pairs:
            parts = pair.split('=')
            if not len(parts) == 2:
                msgs.append("Checkparams must contain a comma-separated list "
                        "of key=value pairs "
                        "but element [%s] format is invalid" % pair)
                validity = False

        if validity == False:
            msgs.append("Checkparams list [%s] is invalid." % fieldStr)

        return validity

    def validUniqueTaskId(self, fieldStr, wfsys, msgs):
        """ validates taskId field for uniqueness in workflow

            Args:
                fieldStr: field value
                wfsys: the workflowsystem object containing existing tasks
                msgs: a list to contain messages for user
            Returns:
                boolean: True if valid, else False
        """
        if fieldStr is None or fieldStr == "":
            msgs.append("Task id invalid. Field cannot be empty")
            return False
        elif wfsys.taskInWorkflow(fieldStr):
            msgs.append("Task id invalid. [%s] duplicates a task id already "
                        "in the workflow" % fieldStr)
            return False
        else:
            return True

    def validExecuteTaskId(self, fieldStr, dyntype, wfsys, msgs):
        """ validates taskId exists in execute phase and is a dynamic msg task

            Args:
                fieldStr: field value
                dyntype: string representing pause or escape
                wfsys: the workflowsystem object containing existing tasks
                msgs: a list to contain messages for user
            Returns:
                boolean: True if valid, else False
        """
        if fieldStr is None:
            msgs.append("Task id invalid. Field must not be empty")
            return False
        tsk = wfsys.execute.getTask(fieldStr)
        if tsk is None:
            msgs.append("Task id invalid. Dynamic task [%s] not found "
                        "in execute phase" % \
                         fieldStr)
            return False
        else:
            if dyntype == constants.DYNAMIC_ESCAPE and \
                    not isinstance(tsk, EscapeTask):
                msgs.append("Task [%s] for removal was found "
                        "not to be a dynamic escape" % fieldStr)
                return False
            elif dyntype == constants.DYNAMIC_PAUSE and \
                      not isinstance(tsk, PauseTask):
                msgs.append("Task [%s] for removal was found "
                         "not to be a dynamic pause" % fieldStr)
                return False
            if not tsk.isDynamic():
                msgs.append("Task [%s] for removal was found "
                         "not to be dynamic" % fieldStr)
                return False
        return True

    def validIniParam(self, fieldStr, wfsys, msgs):
        """ validates that if the field is a parameter then it is in ini params

           Args:
               fieldStr: field value (can be empty)
               wfsys: the workflowsystem object containing existing tasks
               msgs: a list to contain messages for user
           Returns:
               boolean: True if no params found without entry in ini params,
                            else False
        """
        validity = True
        if fieldStr is None:
            fieldStr = ""

        if fieldStr.startswith('$'):
            # check it is in the iniparams and if not then return True to
            # indicate that param is missing from ini file
            param = fieldStr[1:]
            if not param in constants.INI_RESERVED_VARS and \
                        not param in wfsys.config.iniparams:
                msgs.append("Parameter [%s] invalid. " \
                                   "Parameter not found in ini params" % param)
                validity = False

        return validity

    def hasDependents(self, taskId, wfsys, msgs):
        """ checks whether the given task id appears as a dependency in
            any other task

            Args:
                taskId: the task to check
                wfsys: the workflowsystem object containing existing tasks
                msgs: a list to contain messages for user
            Returns:
                boolean: True if has dependents, else False
        """
        dependents = False

        if wfsys.display.hasDependentsOnTask(taskId):
            msgs.append("Dependent/s found in display phase for task [%s]" % \
                            taskId)
            dependents = True

        if wfsys.precheck.hasDependentsOnTask(taskId):
            msgs.append("Dependent/s found in precheck phase for task [%s]" % \
                            taskId)
            dependents = True

        if wfsys.execute.hasDependentsOnTask(taskId):
            msgs.append("Dependent/s found in execute phase for task [%s]" % \
                            taskId)
            dependents = True

        # nb we don't check postcheck because dynamic tasks can only be in
        # execute and dependents cannot appear after the depended task

        return dependents

    def validGroupDepSingle(self, depsingle, refId, dependencies, wfsys, msgs):
        """ checks that IF the tasks are in the same group, then
            depSingle is not set to False

            Args:
                depsingle: the value of the depsingle field
                dependencies: list of tasks on which this task depends
                refId: the task which the new task is being positioned with
                reference to
                wfsys: the workflowsystem object containing existing tasks
                msgs: a list to contain messages for user
            Returns:
                boolean: False if task and any dependency share a group and
                depsingle is not true
        """
        validity = True

        if dependencies is None:
            return True

        newtaskgroup = None
        inds = wfsys.execute.getTaskIndices(refId)
        grp = inds[constants.TASK_IN_GROUP]
        if grp is not None:
            newtaskgroup = grp

        if newtaskgroup is None:
            return True

        depList = utils.split_commas(dependencies)
        if len(depList) != 0:
            for dep in depList:
                inds = wfsys.execute.getTaskIndices(dep)
                grp = inds[constants.TASK_IN_GROUP]
                if grp is not None:
                    if grp == newtaskgroup:
                        if depsingle is None or depsingle.lower() != "true":
                            msgs.append("Dependency %s is in the same group "
                                        "but new task does not have "
                                        "depsinglehost set to true" % dep)
                            validity = False
        return validity

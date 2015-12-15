""" Module represents the workflow as read from workflow xml file, it does
    not contain host specific information and is the generic workflow
    @copyright: Ammeon Ltd
"""
from wfeng.task import FabricTaskManager, GroupTask
from wfeng.task import TagTask, ParallelTask
from wfeng.msgtask import EscapeTask, PauseTask, NoticeTask
from wfeng.workflowsys import WorkflowSystem
from wfeng import constants
from lxml import etree
from wfeng import utils

import logging

log = logging.getLogger(__name__)


class Workflow:
    """Represents a workflow description, as defined by appropriate
       workflow.xml. So is generic across hosts to be applied to."""

    def __init__(self, config):
        """Initialises workflow.

           Args:
               config: WfmgrConfig object with wfeng config
        """
        self.display = []
        self.precheck = []
        self.execute = []
        self.postcheck = []
        self.config = config
        self.taskmgr = FabricTaskManager()
        self.name = ""
        # we will check params in ini file unless explicitly flagged not
        # to do so
        #self.checkIniParams = True

    def _parsePhase(self, phase, element):
        """Parses a phase of workflow, with task items

           Args:
               phase: list to hold any tasks found
               element: the element holding this phase, e.g. display, pre-check
           Returns:
               True if parsed correctly
               False if failed
        """
        phasename = element.tag
        for child in element.iterchildren(tag=etree.Element):
            if child.tag == "group":
                gid = child.attrib["id"]
                group = GroupTask(gid, self.config)
                phase.append(group)
                for ctask in child.iterchildren(tag=etree.Element):
                    if ctask.tag == "task":
                        task = self._parseTask(ctask, phasename)
                    elif ctask.tag == "escape" or ctask.tag == "pause" or \
                         ctask.tag == "notice":
                        task = self._parseMsgTask(ctask, phasename)
                    else:
                        log.error("Unexpected tag {0} within group set".\
                            format(ctask.tag))
                        return False

                    if task is None:
                        return False
                    if task.servertype == "*":
                        log.error("Servertype of * is not supported " + \
                                  "within group {0}".format(gid))
                        return False
                    if not group.append(task):
                        return False

            elif child.tag == "parallel":
                parallel = ParallelTask(child.attrib["id"], self.config)
                phase.append(parallel)
                for ctask in child.iterchildren(tag=etree.Element):
                    if ctask.tag == "task":
                        task = self._parseTask(ctask, phasename)
                        if task is None:
                            return False
                        else:
                            sequence = parallel.getSequence(task)
                            if sequence is not None:
                                sequence.addTask(task)
                            else:
                                return False
                    else:
                        log.error("Unexpected tag {0} within parallel set".\
                                   format(ctask.tag))
                        return False
            elif child.tag == "task":
                task = self._parseTask(child, phasename)
                if task is None:
                    return False
                phase.append(task)
            else:
                failed = True
                if phasename == constants.EXECUTE:
                    if child.tag == "escape":
                        task = self._createMsgTask(child, "escape")
                        if task is None:
                            return False
                        phase.append(task)
                        failed = False
                    elif child.tag == "pause":
                        task = self._createMsgTask(child, "pause")
                        if task is None:
                            return False
                        phase.append(task)
                        failed = False
                    elif child.tag == "notice":
                        task = self._createMsgTask(child, "notice")
                        if task is None:
                            return False
                        phase.append(task)
                        failed = False
                    elif child.tag == "start-tag":
                        task = TagTask(child.attrib["name"], self.config,
                                       True)
                        phase.append(task)
                        failed = False
                    elif child.tag == "end-tag":
                        task = TagTask(child.attrib["name"], self.config,
                                       False)
                        phase.append(task)
                        failed = False
                if failed:
                    log.error("Unexpected tag %s in phase %s" % \
                                      (child.tag, phasename))
                    return False
        return True

    def _createMsgTask(self, child, task_type):
        """ Creates a MsgTask by getting attributes out of child.

            Args:
                child: Child XML element
                task_type: A string representing the type of the task;
                one of pause, escape or notice
            Returns:
                None if found error in element
                array of PauseTask, EscapeTask or NoticeTask on success
        """
        dependency = child.get("dependency")
        if dependency is not None:
            if not self._checkValidDependency(dependency):
                log.error(
                "Dependency {0} for task {1} is invalid".format(
                                            dependency, child.attrib["id"]))
                return None
        depsinglehost = utils.get_boolean(child, "depsinglehost")
        optional = utils.get_boolean(child, "optional")
        dynamic = utils.get_boolean(child, "dynamic")
        server = child.attrib["server"]
        swversion = child.get("swversion")
        if swversion is not None and self._hasMissingIniParam(swversion):
            log.debug("swversion " \
              "%s contains parameters that are not present in the ini file" % \
              swversion)
            return None
        osversion = child.get("osversion")
        if osversion is not None and self._hasMissingIniParam(osversion):
            log.debug("osversion " \
              "%s contains parameters that are not present in the ini file" % \
              osversion)
            return None
        checkparams = utils.get_dictionary(child, "checkparams")
        gid = child.get("gid")
        msgVal = child.get("msg")
        if msgVal is not None and self._hasMissingIniParam(msgVal):
            log.debug(("%s msg element %s contains parameters that are not " \
                       "present in the ini file") % (task_type, msgVal))
            return None
        if task_type == "escape":
            task = EscapeTask(child.attrib["id"], self.config,
                              child.attrib["msg"],
                              child.attrib["hosts"],
                              server, swversion, osversion,
                              dependency, optional,
                              depsinglehost, checkparams,
                              gid, dynamic)
        elif task_type == "pause":
            task = PauseTask(child.attrib["id"], self.config,
                             child.attrib["msg"],
                             child.attrib["hosts"],
                             server, swversion, osversion,
                             dependency, optional,
                             depsinglehost, checkparams,
                             gid, dynamic)
        elif task_type == "notice":
            task = NoticeTask(child.attrib["id"], self.config,
                              child.attrib["msg"],
                              child.attrib["hosts"],
                              server, swversion, osversion,
                              dependency, optional,
                              depsinglehost, checkparams,
                              gid)
        else:
            log.debug("Task type %s is not a valid task type" % task_type)
        return task

    #def setCheckIniParams(self, check):
    #    self.checkIniParams = check

    def parse(self, filename):
        """Parses workflow filename to produce list of tasks

           Args:
               filename: Name of XML workflow file
           Returns:
               True if parsed correctly
        """
        schema_file = constants.WORKFLOW_XSD
        xmlschema_doc = etree.parse(schema_file)
        xmlschema = etree.XMLSchema(xmlschema_doc)
        try:
            doc = etree.parse(filename)
            xmlschema.assertValid(doc)
            log.debug("Succesfully validated %s" % filename)
            tree = etree.parse(filename)
            root = tree.getroot()
            self.name = root.get('name')
            if root.tag != "workflow":
                err_msg = "Root is not workflow: %s" % root.tag
                log.error(err_msg)
                return False
            for element in root.iterchildren(tag=etree.Element):
                retVal = False
                if element.tag == constants.DISPLAY:
                    retVal = self._parsePhase(self.display, element)
                elif element.tag == constants.PRECHECK:
                    retVal = self._parsePhase(self.precheck, element)
                elif element.tag == constants.POSTCHECK:
                    retVal = self._parsePhase(self.postcheck, element)
                elif element.tag == constants.EXECUTE:
                    retVal = self._parsePhase(self.execute, element)
                else:
                    err_msg = "unexpected phase %s" % element.tag
                    log.error(err_msg)
                if retVal == False:
                    return False
            # Check for uniqueness of task id across all phases
            taskids = set()
            for otask in (self.display + self.precheck +
                      self.execute + self.postcheck):
                # Each of the tasks might be group tasks so ask for
                # list of tasks
                for task in otask.getTasks():
                    if task.name in taskids:
                        log.error("Non-unique id %s found in %s" % \
                                               (task.name, filename))
                        return False
                    taskids.add(task.name)
            return True
        except Exception as err:
            err_msg = "Failed to validate %s against %s: %s" % \
                                        (filename, schema_file, repr(err))
            log.error(err_msg)
            log.debug(err_msg, exc_info=True)
            return False

    def genWorkflowSystem(self, hosts):
        """ Generates a wfsystem object for upgrade which is combination of
            workflow and task file, describing which tasks to run on
            which servers with status as INITIAL

            Args:
                hosts - Hosts object that contains details of hosts
            Returns:
                wfsystem - WorkflowSystem object
        """
        wfsystem = WorkflowSystem(self.name, self.config)
        self._genWorkflowPhase(self.display, wfsystem.display, hosts)
        self._genWorkflowPhase(self.precheck, wfsystem.precheck, hosts)
        self._genWorkflowPhase(self.execute, wfsystem.execute, hosts)
        self._genWorkflowPhase(self.postcheck, wfsystem.postcheck, hosts)
        return wfsystem

    def _genWorkflowPhase(self, phase, wsysphase, hosts):
        """ Populates phase of workflowsystem with the individual
            tasks that need to be run on each host

            Args:
                phase - list of tasks to process
                wsysphase - phase of workflow system to populate
                hosts - list of hosts to run workflow on
        """
        for task in phase:
            # For all WTask objects in phase
            if task.needsHost():
                if task.servertype == "*":
                    tasks = []
                    types = hosts.get_types()
                    for servertype in types:
                        tasks.append(task.copy(servertype))
                else:
                    tasks = [task]
                for eachtask in tasks:
                    hostList = self._getHostsThatApply(eachtask, hosts)
                    for host in hostList:
                        wsysphase.add(eachtask, host)
            elif task.isParallel():
                # This is a parallel set so within in it are sequences, check
                # if this is valid for the hostlist
                sequences = []
                for seq in task.sequences:
                    if seq.servertype == "*":
                        servseq = []
                        types = hosts.get_types()
                        for servertype in types:
                            servseq.append(seq.copy(servertype))
                    else:
                        servseq = [seq]
                    for eachseq in servseq:
                        hostList = self._getHostsThatApply(eachseq, hosts)
                        for host in hostList:
                            sequences.append((eachseq, host))
                if len(sequences) > 0:
                    # Update with the tuples of sequence/host
                    task.hostSequences = sequences
                    wsysphase.add(task, None)
            else:
                # type of task such as escape that only runs once not
                # per host
                wsysphase.add(task, None)

    def _checkValidDependency(self, dependency):
        """ Checks if dependency is a valid task we have already defined"""
        # Check dependency is a task we have added
        # Split dependency by ,
        found = []
        dependencies = utils.split_commas(dependency)
        for i in range(len(dependencies)):
            found.append(False)
            for otask in (self.display + self.precheck +
                  self.execute + self.postcheck):
                # Each of the tasks might be group tasks so ask for
                # list of tasks
                for task in otask.getTasks():
                    if dependencies[i] == task.name:
                        found[i] = True
                        break
        # Return false if found none
        for f in found:
            if not f:
                return False
        return True

    def _hasMissingIniParam(self, strng):
        """ validates that any parameters in the supplied string are found
            in the ini file parameters

            Args:
                strng: supplied string which may contain $-prefixed parameters
            Returns:
                False if there are no unmatched params, True if there are
                params in the string which are not found in the ini file params
        """
        if "$" in strng:
            # check it is in the iniparams and if not then return True to
            # indicate that param is missing from ini file
            for word in strng.split():
                if word.startswith("$"):
                    param = word[1:]
                    if not param in constants.INI_RESERVED_VARS and \
                       not param in self.config.iniparams:
                        log.error(("ini parameter %s is used in workflow " \
                                   "but is not found in ini file") % word)
                        return True
        return False

    def _parseTask(self, child, phasename):
        """ Parses a child element that is a task.

            Args:
                child: Child element
                phasename: Name of phase parsing
            Returns:
                FabricTask instance
        """
        cmd = child.get("cmd")
        #if cmd is present then we need to check that any parameters are valid
        if cmd is not None and self._hasMissingIniParam(cmd):
                log.debug(("cmd %s contains parameters that are not " \
                          "present in the ini file") % cmd)
                return None

        id = child.get("id")
        hosts = child.get("hosts")
        server = child.get("server")
        optional = utils.get_boolean(child, "optional")
        duration = child.get("estimatedDur")
        if duration is not None and self._hasMissingIniParam(duration):
                log.debug(("duration %s contains parameters that are not " \
                          "present in the ini file") % duration)
                return None
        dependency = child.get("dependency")
        depsinglehost = utils.get_boolean(child, "depsinglehost")
        run_local = utils.get_boolean(child, "runLocal")

        if dependency != None:
            if not self._checkValidDependency(dependency):
                log.error("Dependency {0} for task {1} is invalid".\
                        format(dependency, id))
                return None
        swversion = child.get("swversion")
        if swversion is not None and self._hasMissingIniParam(swversion):
            log.debug(("swversion %s contains parameters that are not " \
                      "present in the ini file") % swversion)
            return None
        osversion = child.get("osversion")
        if osversion is not None and self._hasMissingIniParam(osversion):
            log.debug(("osversion %s contains parameters that are not " \
                      "present in the ini file") % osversion)
            return None
        checkparams = utils.get_dictionary(child, "checkparams")
        if phasename == constants.EXECUTE:
            continueOnFail = utils.get_boolean(child, "continueOnFail")
        else:
            continueOnFail = True
        task = self.taskmgr.createTask(id, self.config, cmd, hosts, server,
                                           continueOnFail, optional,
                                           duration, dependency, swversion,
                                           osversion,
                                           run_local, depsinglehost,
                                           checkparams)
        return task

    def _parseMsgTask(self, child, phasename):
        """ Parses a child element that is a message task.

            Args:
                child: Child element
                phasename: Name of phase parsing
            Returns:
                MsgTask instance
        """

        id = child.get("id")
        msg = child.get("msg")
        hosts = child.get("hosts")
        server = child.get("server")
        optional = utils.get_boolean(child, "optional")
        dependency = child.get("dependency")
        depsinglehost = utils.get_boolean(child, "depsinglehost")
        if dependency != None:
            if not self._checkValidDependency(dependency):
                log.error("Dependency {0} for task {1} is invalid".\
                        format(dependency, id))
                return None
        swversion = child.get("swversion")
        if swversion is not None and self._hasMissingIniParam(swversion):
            log.debug("swversion %s contains parameters that are not "
                      "present in the ini file" % swversion)
            return None
        osversion = child.get("osversion")
        gid = child.get("gid")
        if osversion is not None and self._hasMissingIniParam(osversion):
            log.debug("osversion %s contains parameters that are not "
                      "present in the ini file" % osversion)
            return None
        checkparams = utils.get_dictionary(child, "checkparams")
        if child.tag == "escape":
            msgtask = EscapeTask(id, self.config, msg, hosts, server,
                                           swversion, osversion,
                                           dependency, optional,
                                           depsinglehost, checkparams, gid)
        elif child.tag == "pause":
            msgtask = PauseTask(id, self.config, msg, hosts, server,
                                           swversion, osversion,
                                           dependency, optional,
                                           depsinglehost, checkparams, gid)
        elif child.tag == "notice":
            msgtask = NoticeTask(id, self.config, msg, hosts, server,
                                           swversion, osversion,
                                           dependency, optional,
                                           depsinglehost, checkparams, gid)
        else:
            log.error("Task tag type {0} for task {1} is invalid".\
                        format(child.tag, id))
            return None

        return msgtask

    def _getHostsThatApply(self, task, hosts):
        """ Returns list of hosts that this task applies to from those
            available """
        hostList = []
        if task.servertype not in hosts.hosts:
            # If its optional - just skip it, else raise error
            if task.optional:
                log.debug("Skipping %s as no server of type %s" %
                              (task.name, task.servertype))
                return hostList
            else:
                raise ValueError(
                           'Missing mandatory server %s in hosts file' % \
                           task.servertype)
        taskhosts = hosts.hosts[task.servertype]
        if task.hosts == constants.ALL:
            for y in taskhosts:
                hostList.append(y)
        else:
            notNum = False
            serverNum = task.hosts
            if task.hosts.startswith("!"):
                # hosts is format !1 to indicate all but first etc
                notNum = True
                serverNum = task.hosts[1:]
            if serverNum == "$":
                # $ indicates last host, so work out last host
                # Want all but last
                serverNum = len(taskhosts)
            else:
                serverNum = int(serverNum)
            if notNum:
                for i in range(len(taskhosts)):
                    if (i + 1) != serverNum:
                        hostList.append(taskhosts[i])
            else:
                hostList.append(taskhosts[serverNum - 1])
        return hostList

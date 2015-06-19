""" Module represents the classes representing a workflow applied to a set
    of hosts
@copyright: Ammeon Ltd
"""
from task import FabricTaskManager, FabricStatusTask
from task import WorkflowStatus
from task import TagTask, ParallelTask, ParallelStatusTask, SequenceTask
from task import SequenceStatusTask
from msgtask import EscapeTask, EscapeStatusTask
from msgtask import PauseStatusTask, PauseTask
from msgtask import NoticeStatusTask, NoticeTask
from fabric.network import disconnect_all
from fabric.state import env
from fabric.context_managers import settings, hide
from lxml import etree
from inputmgr import InputMgr
import constants
import utils
import logging
import sys

# Phases in statusworkflow.xml
DISPLAYSYS = "displaysys"
PRECHECKSYS = "pre-checksys"
POSTCHECKSYS = "post-checksys"
EXECUTESYS = "executesys"

# Misc strings
CONTINUE_PROMPT = "\nDo you want to continue to next phase (y/n)?: "
WORKFLOW_FINISHED_LINE = "Workflow completed"

log = logging.getLogger(__name__)


class WorkflowSystem:
    """
    Represents a workflow for a particular set of hosts, so is the
    representation of amalgamating the workflow xml (Workflow class) with
    the particular hosts to run on (Hosts class).
    """

    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.input = InputMgr()
        self.currentPhase = 0
        self.display = WorkflowPhase(constants.DISPLAY, self)
        self.precheck = WorkflowPhase(constants.PRECHECK, self)
        self.postcheck = WorkflowPhase(constants.POSTCHECK, self)
        self.execute = WorkflowPhase(constants.EXECUTE, self, False, True)
        self.taskmgr = FabricTaskManager()
        self.phasesToRun = {}
        self.phasesToRun[constants.OPT_DISPLAY] = [self.display]
        self.phasesToRun[constants.OPT_PRECHECK] = [self.display,
                                                    self.precheck]
        self.phasesToRun[constants.OPT_EXECUTE] = [self.display,
                                                   self.precheck,
                                                   self.execute]
        self.phasesToRun[constants.OPT_POSTCHECK] = [self.display,
                                                     self.precheck,
                                                     self.execute,
                                                     self.postcheck]
        self.failed = False

    def isEquivalent(self, wsys):
        """ Compares this workflow system with that described by sys, and
            if they are the same ignoring status then they are equivalent
            Arguments:
                wsys: WorkflowSystem to compare against
            Returns:
                True: if same ignoring status
                False: if different
        """
        if self.name != wsys.name:
            log.debug("Names on Workflows differ: %s/%s" %
                  (self.name, wsys.name))
            return False
        if not self.display.isEquivalent(wsys.display):
            return False
        if not self.precheck.isEquivalent(wsys.precheck):
            return False
        if not self.execute.isEquivalent(wsys.execute):
            return False
        if not self.postcheck.isEquivalent(wsys.postcheck):
            return False
        return True

    def write(self, filename):
        """ Generates an output file describing status"""
        root = etree.Element("workflowsys")
        root.attrib['name'] = self.name
        display = etree.SubElement(root, DISPLAYSYS)
        self.display.populateTree(display, True)
        precheck = etree.SubElement(root, PRECHECKSYS)
        self.precheck.populateTree(precheck)
        execute = etree.SubElement(root, EXECUTESYS)
        self.execute.populateTree(execute)
        postcheck = etree.SubElement(root, POSTCHECKSYS)
        self.postcheck.populateTree(postcheck)
        output = etree.tostring(root, pretty_print=True)
        f = open(filename, 'w')
        f.write(output)
        f.close()
        log.log(constants.TRACE, "Generated %s containing:\n %s" % \
                             (filename, output))

    def load(self, filename, hosts):
        """ Reads filename to get running status
            Arguments:
                filename: workflowstatus file from previous run
                hosts: hosts list
            Returns: True if loaded ok, False otherwise
        """
        schema_file = constants.WORKFLOW_XSD
        xmlschema_doc = etree.parse(schema_file)
        xmlschema = etree.XMLSchema(xmlschema_doc)
        doc = etree.parse(filename)
        try:
            xmlschema.assertValid(doc)
            log.debug("Succesfully validated %s" % filename)
            tree = etree.parse(filename)
            root = tree.getroot()
            if root.tag != "workflowsys":
                err_msg = "Root is not workflowsys: %s" % root.tag
                log.error(err_msg)
                return False
            self.name = root.attrib['name']
            for element in root.iterchildren():
                retVal = False
                if element.tag == DISPLAYSYS:
                    retVal = self._parsePhase(self.display, element, hosts)
                elif element.tag == PRECHECKSYS:
                    retVal = self._parsePhase(self.precheck, element, hosts)
                elif element.tag == POSTCHECKSYS:
                    retVal = self._parsePhase(self.postcheck, element, hosts)
                elif element.tag == EXECUTESYS:
                    retVal = self._parsePhase(self.execute, element, hosts)
                else:
                    err_msg = "unexpected phase %s" % element.tag
                    log.error(err_msg)
                if retVal == False:
                    return False
            log.debug("Read status file containing: \n%s" % \
                etree.tostring(root))
            return True
        except Exception as err:
            err_msg = "Failed to validate %s against %s: %s" % \
                                           (filename, schema_file, repr(err))
            log.error(err_msg)
            log.debug(err_msg, exc_info=True)
            return False

    def _parsePhase(self, phase, element, hosts):
        """Parses a phase of workflowsys, with taskstatus items
           Arguments:
               phase: list to hold any tasks found
               element: the element holding this phase, e.g. display
               hosts: hosts file read in
           Returns:
               True if parsed correctly
               False if failed
        """
        phasename = element.tag
        log.log(constants.TRACE, "Loading phase %s" % phasename)
        for child in element.iterchildren():
            if child.tag == "taskstatus":
                statustask = self._parseTaskStatus(child, phasename, hosts)
                phase.tasks.append(statustask)
            elif child.tag == "parallelstatus":
                id = child.get("id")
                status = child.get("status")
                task = ParallelTask(id, self.config)
                parallelTask = ParallelStatusTask(task, status)
                for parallelchild in child.iterchildren():
                    if parallelchild.tag == "sequencestatus":
                        seqid = parallelchild.get("id")
                        host = parallelchild.get("host")
                        server = parallelchild.get("server")
                        hostobj = hosts.get(host, server)
                        seqTask = SequenceTask(seqid, self.config)
                        seqStatusTask = SequenceStatusTask(seqTask, hostobj)
                        parallelTask.sequences.append(seqStatusTask)
                        for seqchild in parallelchild.iterchildren():
                            if seqchild.tag == "taskstatus":
                                statustask = self._parseTaskStatus(seqchild,
                                                      phasename, hosts)
                                seqStatusTask.addTask(statustask)
                            else:
                                log.error("Unexpected tag %s in " +
                                  "sequencestatus within phase %s" % \
                                           (seqchild.tag, phasename))
                    else:
                        log.error("Unexpected tag %s in parallelstatus " +
                                  "within phase %s" % \
                                           (parallelchild.tag, phasename))
                        return False
                phase.tasks.append(parallelTask)
            else:
                failed = True
                if phasename == EXECUTESYS:
                    if child.tag == "pausestatus":
                        host = child.get("host")
                        server = child.get("server")
                        optional = utils.get_boolean(child, "optional")
                        depsinglehost = utils.get_boolean(child,
                                                          "depsinglehost")
                        swversion = child.get("swversion")
                        osversion = child.get("osversion")
                        checkparams = utils.get_dictionary(child, "checkparams")
                        task = PauseTask(child.get("id"), self.config,
                                         child.get("msg"), host, server,
                                         swversion, osversion,
                                         child.get("dependency"), optional,
                                         depsinglehost, checkparams)
                        status = child.get("status")
                        hostobj = hosts.get(host, server)
                        phase.tasks.append(PauseStatusTask(task, hostobj,
                                                           status))
                        failed = False
                    elif child.tag == "escapestatus":
                        host = child.get("host")
                        server = child.get("server")
                        optional = utils.get_boolean(child, "optional")
                        depsinglehost = utils.get_boolean(child,
                                                          "depsinglehost")
                        swversion = child.get("swversion")
                        osversion = child.get("osversion")
                        checkparams = utils.get_dictionary(child, "checkparams")
                        task = EscapeTask(child.get("id"), self.config,
                                          child.get("msg"), host, server,
                                          swversion, osversion,
                                          child.get("dependency"), optional,
                                          depsinglehost, checkparams)
                        status = child.get("status")
                        hostobj = hosts.get(host, server)
                        phase.tasks.append(EscapeStatusTask(task, hostobj,
                                                            status))
                        failed = False
                    elif child.tag == "noticestatus":
                        host = child.get("host")
                        server = child.get("server")
                        optional = utils.get_boolean(child, "optional")
                        depsinglehost = utils.get_boolean(child,
                                                          "depsinglehost")
                        swversion = child.get("swversion")
                        osversion = child.get("osversion")
                        checkparams = utils.get_dictionary(child, "checkparams")
                        task = NoticeTask(child.get("id"), self.config,
                                          child.get("msg"), host, server,
                                          swversion, osversion,
                                          child.get("dependency"), optional,
                                          depsinglehost, checkparams)
                        status = child.get("status")
                        hostobj = hosts.get(host, server)
                        phase.tasks.append(NoticeStatusTask(task, hostobj,
                                                            status))
                        failed = False
                    elif child.tag == "start-tag":
                        task = TagTask(child.get("name"), self.config, True)
                        phase.add(task, "")
                        failed = False
                    elif child.tag == "end-tag":
                        task = TagTask(child.get("name"), self.config, False)
                        phase.add(task, "")
                        failed = False
                if failed:
                    log.error("Unexpected tag %s in phase %s" % \
                              (child.tag, phasename))
                    return False

    def _parseTaskStatus(self, child, phasename, hosts):
        """ Extracts details from taskstatus element and returns a
            FabricStatusTask element.
            Arguments:
                child: TaskStatus element
            Returns:
                FabricStatusTask
        """
        cmd = child.get("cmd")
        id = child.get("id")
        host = child.get("host")
        server = child.get("server")
        duration = child.get("estimatedDur")
        actualDuration = child.get("actualDur")
        dependency = child.get("dependency")
        depsinglehost = utils.get_boolean(child, "depsinglehost")
        swversion = child.get("swversion")
        osversion = child.get("osversion")
        gid = child.get("gid")
        run_local = utils.get_boolean(child, "runLocal")
        optional = utils.get_boolean(child, "optional")
        status = child.get("status")
        if phasename == EXECUTESYS:
            continueOnFail = utils.get_boolean(child, "continueOnFail")
        else:
            continueOnFail = True
        checkparams = utils.get_dictionary(child, "checkparams")
        task = self.taskmgr.createTask(id, self.config, cmd, "",
                                          server, continueOnFail,
                                          optional, duration,
                                          dependency, swversion, osversion,
                                          run_local,
                                          depsinglehost, checkparams, gid)
        hostobj = hosts.get(host, server)
        params = utils.get_dictionary(child, "params")
        hostobj.add_params(params)
        fabrictask = FabricStatusTask(task, hostobj, status)
        if actualDuration is not None:
            fabrictask.actualDuration = actualDuration
        return fabrictask

    def isValidTask(self, taskid):
        """ Returns whether taskid is in workflow
            Arguments:
                taskid: ID of task to lookup
            Returns:
                True if found, else False
        """
        for phase in self.phasesToRun[constants.OPT_POSTCHECK]:
            if phase.getTask(taskid) is not None:
                return True
        return False

    def isValidTag(self, tag):
        """ Returns whether tag is in workflow
            Arguments:
                tag: ID of tag to lookup
            Returns:
                True if found, else False
        """
        if self.execute.getTag(tag) is not None:
            return True
        return False

    def eligibleDisplayTasks(self, servertype, servername, excluded, force, exact_match):
        """ returns True if there are non-completed eligible tasks in this phase, or False if there are none"""
        # split the excluded string into a list
        excludes = []
        if excluded != None:
            excludes = [x.strip() for x in excluded.split(',')]
        for dtask in self.display.tasks:
            if dtask.isParallelStatusTask():
                if not dtask.sequenceNoneToRun(servertype, servername, excludes,
                            input, force, exact_match):
                    return True
            else:
                if dtask.shouldRunOnHost(servertype, servername, excludes,
                            input, force, exact_match):
                    # if task status is not in SUCCESS_STATUSES then it could be eligible for run
                    if not dtask.status in constants.SUCCESS_STATUSES :
                        return True
        return False

    def getTask(self, taskid):
        """ Returns task
            Arguments:
                taskid: ID of task to lookup
            Returns:
                WTask object or None if not found
        """
        for phase in self.phasesToRun[constants.OPT_POSTCHECK]:
            task = phase.getTask(taskid)
            if task is not None:
                return task
        return None

    def getTaskStatus(self, taskid, hosts):
        """ Returns task status of taskid on hosts specified.
            taskid will only be in one phase, so return status from
            first phase find it in
        """
        for phase in self.phasesToRun[constants.OPT_POSTCHECK]:
            status = phase.getTaskStatus(taskid, hosts)
            if status is not None:
                return status
        return None

    def process(self, term_size, options):
        """ Process workflow defined here
            Arguments:
                term_size: Terminal size
                options: WorkflowOptions object
            Returns:
                WorkflowStatus instance
        """
        #env.password = 'passw0rd'
        env.timeout = options.timeout
        try:
            exclude = []
            if options.exclude is not None:
                # Now strip of spaces
                exclude = [x.strip() for x in options.exclude.split(',')]
            if options.phase == constants.OPT_DISPLAY:
                # Only always run display if explicitly ask for display
                self.display.alwaysRun = True
            if options.phase == constants.OPT_PRECHECK:
                # Only always run precheck if explicitly ask for precheck
                self.precheck.alwaysRun = True
            if options.phase in self.phasesToRun:
                numPhases = len(self.phasesToRun[options.phase])
                for i in range(self.currentPhase, numPhases):
                    log.debug("Running phase %d of %d, failed %s" % ((i + 1), numPhases, self.failed))
                    sysfilename = options.getSysStatusName()

                    phase = self.phasesToRun[options.phase][i]
                    (numSuccess, numFailed, numSkipped, carry_on) = \
                          phase.process(term_size,
                                 exclude,
                                 sysfilename,
                                 options)

                    if numFailed > 0:
                        self.failed = True
                    # If this is single-task and phase contained our task
                    if options.task is not None and \
                              phase.getTask(options.task) is not None:
                        log.debug("STOPPING workflow as ran chosen task")
                        if self.failed and not options.list:
                            return WorkflowStatus(WorkflowStatus.FAILED,
                                WORKFLOW_FINISHED_LINE)
                        else:
                            return WorkflowStatus(WorkflowStatus.COMPLETE,
                                 WORKFLOW_FINISHED_LINE)

                    # Determine if exited phase in middle, and not for
                    # user input
                    if not options.list and not carry_on:
                        if self.failed:
                            # Finished phase early with failure
                            log.debug("Finished early with one or more failure")
                            return WorkflowStatus(WorkflowStatus.FAILED,
                               "STOPPING as requested")
                        else:
                            # Finished phase early without failure, eg escape
                            log.debug("Finished early with no failures")
                            return WorkflowStatus(WorkflowStatus.COMPLETE,
                               "STOPPING as requested")


                    # Completed phase so increment currentPhase
                    self.currentPhase = self.currentPhase + 1

                    # If not last phase then ask whether to continue
                    if i != (numPhases - 1):
                        # Can only go onto next phase if this phase succeeded
                        # OR force is true
                        if numFailed > 0 and not options.list:
                            if options.force:
                                log.debug(
                                 "Workflow can continue as force has been set")
                            else:
                                return WorkflowStatus(WorkflowStatus.FAILED,
                                    "STOPPING workflow as phase has failed")
                        if (not options.yes and not options.list and not options.automate):
                            # If haven't said always answer yes AND
                            # we haven't just said to list tasks, then ask
                            # whether to continue to next phase
                            return WorkflowStatus(WorkflowStatus.USER_INPUT,
                                CONTINUE_PROMPT)
        finally:
            #with settings(
            #    hide('everything', 'aborts', 'status')
            #):
            #    disconnect_all()
            pass
        if self.failed and not options.list:
            return WorkflowStatus(WorkflowStatus.FAILED,
                            WORKFLOW_FINISHED_LINE)
        else:
            return WorkflowStatus(WorkflowStatus.COMPLETE,
                            WORKFLOW_FINISHED_LINE)


class WorkflowPhase:
    """
    Represents a workflow for a particular phase
    """

    def __init__(self, name, wfsys, alwaysRun=False, askSkip=False):
        """ Initialises the workflow phase.
            Arguments:
                name: name of phase
                wfsys: WorkflowSystem instance that phase is part of
                alwaysRun: if true, then will always run tasks in phase, even
                           if they previously succeeded. Otherwise will
                           only run non-successful tasks.
                           This allows for resuming an upgrade, so display
                           tasks will always be run, but other phases will
                           only run non-success tasks"""
        self.tasks = []
        self.tags = {}
        self.name = name
        self.wfsys = wfsys
        self.alwaysRun = alwaysRun
        self.askSkip = askSkip

    def add(self, task, host):
        """ Add task and host to system, with INITIAL state"""
        stasks = task.getStatusTasks(host)
        for statustask in stasks:
            self.tasks.append(statustask)
            if statustask.task.isTag():
                # This is a tag
                if statustask.task.is_start:
                    # Is a start task
                    self.tags[statustask.task.tag] = (len(self.tasks) - 1)
                    log.log(constants.TRACE, "Task {0} starts at {1}".format(
                              statustask.task.tag,
                              self.tags[statustask.task.tag]))
                else:
                    # Is an end task - if tag already in list we found
                    # start tag, so do nothing.
                    # Else if end with no start, then tag starts at first
                    # task in phase
                    if not statustask.task.tag in self.tags:
                        self.tags[statustask.task.tag] = 0

    def isEquivalent(self, phase):
        """ Compares this workflow phase with that described by phase, and
            if they are the same ignoring status then they are equivalent
            Arguments:
                phase: WorkflowPhase to compare against
            Returns:
                True: if same ignoring status
                False: if different
        """
        if self.name != phase.name:
            log.debug("Names on Phase differ: %s/%s" %
                  (self.name, phase.name))
            return False
        if len(self.tasks) != len(phase.tasks):
            log.debug("Number of tasks differ: %d/%d" %
                  (len(self.tasks), len(phase.tasks)))
            return False
        i = 0
        for a in self.tasks:
            if not a.isEquivalent(phase.tasks[i]):
                return False
            i = i + 1
        return True

    def getTask(self, taskid):
        """ Returns WTask object if its in phase
            Arguments:
                taskid: ID of task to lookup
            Returns:
                WTask if found or None if not found
        """
        for task in self.tasks:
            if task.task.name == taskid:
                return task.task
            elif task.task.isParallel():
                tasklist = task.getTaskStatusList(taskid)
                if len(tasklist) > 0:
                    return tasklist[0].task
        return None

    def getTag(self, tag):
        """ Returns index of the start tag corresponding to tag
            Arguments:
                taskid: ID of task to lookup
            Returns:
                index of start point
        """
        if tag in self.tags:
            return self.tags[tag]
        else:
            return None

    def getTaskStatus(self, taskid, hosts):
        """ Returns WTask object status if its present
            Arguments:
                taskid: ID of task to lookup
                hosts: hostname to lookup for or ALL
            Returns:
                status or None if not found
        """
        status = None
        for task in self.tasks:
            stasks = task.getTaskStatusList(taskid)
            for stask in stasks:
                if hosts == constants.ALL:
                    # Found one of our hosts, so amalgamate status
                    # Priority order of statuses are:
                    #   FAILED - if any task FAILED
                    #   SKIPPED - if any task SKIPPED but none FAILED
                    #   INITIAL
                    #   SUCCESS - all ran successfully
                    if status == None:
                        # 1st status - so set it
                        status = stask.status
                    elif stask.status == constants.FAILED:
                        # Set status to FAILED if any failed
                        status = constants.FAILED
                    elif status != constants.FAILED:
                        # Only overwrite if not failed
                        if stask.status == constants.SKIPPED:
                            status = constants.SKIPPED
                        elif status != constants.SKIPPED:
                            if stask.status == constants.INITIAL:
                                status = constants.INITIAL
                            else:
                                status = stask.status
                else:
                    # We only care about one host
                    if stask.host.hostname == hosts:
                        return stask.status
        return status

    def process(self, term_size, excluded,
                      sysfilename, options):
        """ Process workflow defined here
            Arguments:
                term_size: Terminal size
                excluded: List of servers not to run on
                sysfilename: So can write status file after each task
                option: WorkflowOptions instance
            Returns: Tuple of numSuccess, numFailed, numSkipped
        """
        if options.list:
            run_str = "LISTING"
        else:
            run_str = "RUNNING"
        phaseoutput = "{0} PHASE: {1}".format(run_str, self.name)
        lines = "-" * len(phaseoutput)
        phaseoutput = phaseoutput.center(term_size)
        lines = lines.center(term_size)
        log.info("\n%s\n%s\n" % (phaseoutput, lines))
        #fabric.state.output['aborts'] = False
        # If running tagged set then will set skip_now when get to end
        # so initialise to false at start
        skip_now = False
        # Get start index if running tagged set
        startindex = 0
        log.debug("Tag is {0}".format(options.tag))
        if options.tag is not None:
            # Find start index for tag
            startindex = self.getTag(options.tag)
            if startindex == None:
                startindex = 0
                log.debug("Found no index for tag {0}".format(options.tag))
            else:
                log.debug("Starting at {0} task for tag {1}".format(
                            startindex, options.tag))
        # Set carry_on to False if we want to stop running
        carry_on = True
        only_run_escape = False
        for index in range(len(self.tasks)):
            a = self.tasks[index]
            run_on_server = True
            list_skip_reason = constants.SKIPPED
            list_skip_colour = constants.COLOURS.status[constants.SKIPPED]
            if only_run_escape:
                # Only process subsequent escapes
                if not isinstance(a, EscapeStatusTask):
                    log.log(constants.TRACE,
                            "Only carrying on to see if more escapes," +
                            "found {0} so stopping".format(a.task.name))
                    carry_on = False
                    break
                else:
                    log.log(constants.TRACE,
                            "Only carrying on to see if more escapes," +
                            "found {0} so continuing to check".format(a.task.name))
            manual_fix = False
            if a.task.isTag():
                # tag task
                log.debug("Skipping task as is tag task {0}".\
                                        format(a.task.name))
                run_on_server = False
            elif not self.alwaysRun and a.status in constants.SUCCESS_STATUSES:
                log.debug("Skipping task %s as passed on previous run" \
                             % (a.task.name))
                run_on_server = False
                list_skip_reason = "SKIP_SUCCESS"
                list_skip_colour = constants.COLOURS.status[constants.SUCCESS]
            elif options.task is not None:
                if not a.containsTask(options.task):
                    log.debug("Skipping task %s %s as task not %s" % \
                           (a.task.name, self._getHostStr(a), options.task))
                    run_on_server = False
            elif index < startindex:
                log.debug("Skipping task %s %s as not at start tag %s" % \
                           (a.task.name, self._getHostStr(a), options.tag))
                run_on_server = False
            elif skip_now:
                log.debug("Skipping task %s %s as reached end tag %s" % \
                          (a.task.name, self._getHostStr(a), options.tag))
                run_on_server = False
            if run_on_server and a.hasHost():
                # StatusTask has a host parameter so use it to work out
                # whether to run or not
                run_on_server = a.shouldRunOnHost(options.servertype,
                       options.servername, excluded, self.wfsys.input,
                       options.force, options.exact_match)
                if a.status == constants.REACHED_VERSION or a.status == constants.PARAM_NOTMATCH:
                    list_skip_reason = "SKIP_%s" % (a.status)
                    list_skip_colour = constants.COLOURS.status[a.status]
            if run_on_server and a.hasDependency():
                # First check dependencies
                # a.task.dependency is id of task to check
                hostsToCheck = constants.ALL
                # Check passed on all hosts unless both this task and
                # dependency are in the same group
                dependencies = a.task.dependency.split(",")
                for dep in dependencies:
                    depTask = self.wfsys.getTask(dep)
                    # dependency may be None if we've not run the dependency
                    # task on this run, so treat as if its been skipped
                    if depTask is not None:
                        if depTask.isParallel() == False:
                            log.log(constants.TRACE,
                                  "Task gid %s dep gid %s".format(\
                                   a.task.gid, depTask.gid))
                            # Check single host if in same group, or if
                            # depsinglehost specifically set
                            if a.task.gid == depTask.gid and \
                                           a.task.gid is not None:
                                hostsToCheck = a.host.hostname
                            elif a.task.depsinglehost:
                                hostsToCheck = a.host.hostname
                        else:
                            log.log(constants.TRACE,
                               "Parallel task %s so use all hosts" % dep)
                        log.log(constants.TRACE,
                          "Looking up dependency %s for hosts %s" % \
                               (dep, hostsToCheck))
                        # its dependant task are in the same group
                        dstatus = self.wfsys.getTaskStatus(dep,
                                                     hostsToCheck)
                    else:
                        log.log(constants.TRACE,
                             "Failed to find dependency %s" % dep)
                        dstatus = constants.SKIPPED
                    log.debug("Dependency status %s for %s/%s" % \
                             (dstatus, dep, hostsToCheck))
                    if dstatus not in constants.SUCCESS_STATUSES:
                        log.debug("Skipping task " +
                                  "{0} as dependency {1} not passed".format(\
                                        a.task.name, dep))
                        run_on_server = False
                        if not only_run_escape:
                            # Do not update status if we were just looking
                            # to see if any escapes we should mark off
                            a.status = constants.SKIPPED
            if only_run_escape and not run_on_server:
                # Its an escape task and we only want to run escapes
                # But we have decided its not relevant for our host
                # Then we must stop and not process it
                log.log(constants.TRACE,
                        "Only carrying on to see if more escapes, found {0}" +\
                        " which will not run, so stopping".format(a.task.name))
                carry_on = False
                break

            # if this is a parallel task then we need to split out into tasks in order to assess whether any are due, and for
            # --list command to assess what to display

            if run_on_server:
                if self.askSkip and a.askSkip() and \
                          not options.list and not options.fix:
                    a.logCommand()
                    # Work out whether to skip or not
                    parallelComplete = False
                    if a.task.isParallel():
                        parallelComplete = a.sequenceNoneToRun(options.servertype, options.servername,
                                 excluded, self.wfsys.input,
                                 options.force, options.exact_match)

                    if (not (options.yes and not isinstance(a, PauseStatusTask))
                            and not options.automate and not parallelComplete):
                        ret_val = self.wfsys.input.askRunSkipTask(a, excluded)
                        if ret_val == 1:
                            run_on_server = False
                        elif ret_val == 2:
                            carry_on = False
                            break
            if options.list and not a.task.isTag():
                if a.task.isParallel():
                    tasks = a.listTasks(options.servertype, options.servername,
                                 excluded, self.wfsys.input,
                                 options.force, options.exact_match)
                    # Returns a list of tuples of task, run_on_server
                    for t, r in tasks:
                        if r:
                            log.info("RUN TASK {0}: {1}{2}\n".format(
                                t.getId(), t.getCmd(),
                                self._getHostStr(t)))
                            # for --list we assume all tasks that are run will be successful
                            a.status = constants.SUCCESS
                        else:
                            log.info("{0}{1}{2} TASK {3}: {4}{5}\n".format(
                                list_skip_colour,
                                list_skip_reason,
                                constants.COLOURS.END,
                                t.getId(), t.getCmd(),
                                self._getHostStr(a)))
                else:
                    if run_on_server:
                        log.info("RUN TASK {0}: {1}{2}\n".format(
                            a.getId(), a.getCmd(),
                             self._getHostStr(a)))
                        # for --list we assume all tasks that are run will be successful
                        a.status = constants.SUCCESS
                    else:
                            log.info("{0}{1}{2} TASK {3}: {4}{5}\n".format(
                                list_skip_colour,
                                list_skip_reason,
                                constants.COLOURS.END,
                                a.getId(), a.getCmd(),
                                self._getHostStr(a)))
                continue
            if run_on_server:
                try:
                    result = self._run_task(a, options)
                finally:
                    with settings(
                        hide('everything', 'aborts', 'status')
                    ):
                        disconnect_all()

                if result.status == WorkflowStatus.FAILED or \
                        result.status == WorkflowStatus.STOPPED:
                    if result.status == WorkflowStatus.STOPPED and \
                            isinstance(a, EscapeStatusTask):
                        # If this was an escape then process any more escapes
                        log.log(constants.TRACE,
                                "Found escape, check to see if more escapes")
                        only_run_escape = True
                    else:
                        carry_on = False
                        break
                elif result.status == WorkflowStatus.USER_INPUT:
                    #  Logic for prompt options:
                    # --automate - do not prompt for any execution task or pause
                    # in workflow.
                    # --yes prompt for pause but not execution tasks.
                    #  Otherwise, prompt for all.
                    if options.automate or \
                            (options.yes and not isinstance(a, PauseStatusTask)):
                        # Just output question and then we'll output result
                        log.info(result.user_msg)
                    else:
                        if not self.wfsys.input.askContinue(result):
                            carry_on = False
                            break
                    if result.success_msg is not None:
                        # output result if it was successful, and we asked
                        # for msg to be output
                        log.info(result.success_msg)
            elif not a.task.isTag():
                # Skipped task - unless its a tag
                hoststr = self._getHostStr(a)
                # update status to SKIPPED unless its been skipped because
                # it was already successful
                if a.status not in constants.SUCCESS_STATUSES:
                    a.setStatus(constants.SKIPPED)
                utils.logSkippedTask(log, a, hoststr)
            else:
                # If this is end tag then we want to stop processing
                if not a.task.is_start:
                    # Is it our end tag
                    if options.tag is not None and a.task.tag == options.tag:
                        # Our end tag so finish, skip from now on
                        skip_now = True

            # Update status file
            if options.list:
                log.debug("Writing results of listing to %s%s" % (sysfilename, constants.LISTFILE_SUFFIX))
                self.wfsys.write("%s%s" %(sysfilename, constants.LISTFILE_SUFFIX))
            else:
                self.wfsys.write(sysfilename)

        return self._postPhaseProcess(options.list, carry_on)

    def _getHostStr(self, task):
        """ Returns the hostname representation of task
            Arguments:
                task: StatusTask to get host from
            Returns:
                String
        """
        if task.hasHost():
            hostips = ""
            for host in task.getHosts():
                hostip = host.ipaddr
                if host.hostname == constants.LOCAL or \
                    task.task.run_local == True:
                    hostip = constants.LOCAL
                if hostips != "":
                    hostips = hostips + ", "
                hostips = "{0}{1}".format(hostips, hostip)
            hoststr = " on {0}".format(hostips)
        else:
            hoststr = ""
        return hoststr

    def _postPhaseProcess(self, list_only, carry_on):
        """ Performs any checking required after running phase tasks, and
            output any summary logic
            Arguments:
                list_only: True if run in list_only mode
                           so don't log summary output
                carry_on: Indicates if should continue to next phase
            Returns: Tuple of numSuccess, numFailed, numSkipped, carry_on
        """
        numFailed = 0
        numSuccess = 0
        numSkipped = 0
        for a in self.tasks:
            (incSuccess, incFailed, incSkipped) = a.getCounts()
            numSuccess = numSuccess + incSuccess
            numFailed = numFailed + incFailed
            numSkipped = numSkipped + incSkipped
        if not list_only:
            log.info("SUMMARY: Success: %d Failed: %d Skipped: %d" %
                  (numSuccess, numFailed, numSkipped))
        return (numSuccess, numFailed, numSkipped, carry_on)

    def _run_task(self, a, options):
        """ Runs a task
            Arguments:
                a: StatusTask to run remotely
                task: None if not asked to run particular task, or
                      task id to run (used when running task within parallel)
            Returns:
                whether to stop running workflow
        """
        return a.run(self._writeInLine, self.name, self.wfsys,
                                        options.task,
                                        self.alwaysRun, options)

    def _writeInLine(self, line, end=False, writelog=True, logger=log,
                           usestdout=True):
        """ Writes line to console output and log file, in way that if
            called again will update the line in place.
            Arguments:
                line: Line to write
                end: If True then writes a newline character as well
                writelog: Whether to write to log file
                logger: Logger to use
                usestdout: If true then write to stdout using stdout, else
                           use logger
        """
        if usestdout:
            if writelog == True:
                logger.debug(line)
            sys.stdout.write(line)
            if end:
                sys.stdout.write("\n")
            sys.stdout.flush()
        else:
            logger.info(line)

    def populateTree(self, element, writeHostParams=False):
        """ Populates phase element with tasks """
        for a in self.tasks:
            a.populateTree(element, writeHostParams)

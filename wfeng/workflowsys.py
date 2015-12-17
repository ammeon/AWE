""" Module represents the classes representing a workflow applied to a set
    of hosts
    @copyright: Ammeon Ltd """
from wfeng.task import FabricTaskManager, FabricStatusTask
from wfeng.task import WorkflowStatus
from wfeng.task import TagTask, ParallelTask, ParallelStatusTask, SequenceTask
from wfeng.task import SequenceStatusTask
from wfeng.msgtask import MsgTask, EscapeTask, EscapeStatusTask
from wfeng.msgtask import PauseStatusTask, PauseTask
from wfeng.msgtask import NoticeStatusTask, NoticeTask
from fabric.network import disconnect_all
from fabric.state import env
from fabric.context_managers import settings, hide
from lxml import etree
from wfeng.inputmgr import InputMgr
from wfeng import constants
from wfeng import utils
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
        self.logqueue = None
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
        self.trapped = False

    def interrupt_handler(self, signal, frame):
        """ Output that Ctrl C has been caught"""
        # NB both the main process and sub processes will have this
        # interrupt handler. Therefore the sub processes's wfsys will
        # be updated as well as the main one. Therefore no special signalling
        # is required between the main and child threads
        print "INTERRUPT CAUGHT - Engine will stop when running tasks " \
                 "have finished"
        self.trapped = True

    def isEquivalent(self, wsys):
        """ Compares this workflow system with that described by sys, and
            if they are the same ignoring status and ignoring dynamic pauses
            and dynamic escapes then they are equivalent

            Args:
                wsys: WorkflowSystem to compare against
            Returns:
                boolean: True if same ignoring status, False if different
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

    def validateWorkflow(self, tree, hosts):
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

    def load(self, filename, hosts):
        """ Reads filename to get running status

            Args:
                filename: workflowstatus file from previous run
                hosts: hosts list
            Returns: boolean: True if loaded ok, False otherwise
        """
        schema_file = constants.WORKFLOW_XSD
        xmlschema_doc = etree.parse(schema_file)
        xmlschema = etree.XMLSchema(xmlschema_doc)
        doc = etree.parse(filename)
        try:
            xmlschema.assertValid(doc)
            log.debug("Succesfully validated %s" % filename)
            tree = etree.parse(filename)
            validationRes = self.validateWorkflow(tree, hosts)
        except Exception as err:
            err_msg = "Failed to validate altered status file against " \
                      "%s: %s" % \
                                           (schema_file, repr(err))
            log.error(err_msg)
            log.debug(err_msg, exc_info=True)
            return False
        return validationRes

    def _parsePhase(self, phase, element, hosts):
        """Parses a phase of workflowsys, with taskstatus items

           Args:
               phase: list to hold any tasks found
               element: the element holding this phase, e.g. display
               hosts: hosts file read in
           Returns:
               boolean: True if parsed correctly, False if failed
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
                                log.error(("Unexpected tag %s in " \
                                   "sequencestatus within phase %s") % \
                                           (seqchild.tag, phasename))
                    else:
                        log.error(("Unexpected tag %s in parallelstatus " \
                                  "within phase %s") % \
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
                        checkparams = utils.get_dictionary(child,
                                              "checkparams")
                        gid = child.get("gid")
                        dynamic = utils.get_boolean(child, "dynamic")
                        task = PauseTask(child.get("id"), self.config,
                                         child.get("msg"), host, server,
                                         swversion, osversion,
                                         child.get("dependency"), optional,
                                         depsinglehost, checkparams, gid,
                                         dynamic)
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
                        checkparams = utils.get_dictionary(child,
                                              "checkparams")
                        gid = child.get("gid")
                        dynamic = utils.get_boolean(child, "dynamic")
                        task = EscapeTask(child.get("id"), self.config,
                                          child.get("msg"), host, server,
                                          swversion, osversion,
                                          child.get("dependency"), optional,
                                          depsinglehost, checkparams, gid,
                                          dynamic)
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
                        checkparams = utils.get_dictionary(child,
                                     "checkparams")
                        gid = child.get("gid")
                        task = NoticeTask(child.get("id"), self.config,
                                          child.get("msg"), host, server,
                                          swversion, osversion,
                                          child.get("dependency"), optional,
                                          depsinglehost, checkparams, gid)
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

            Args:
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

    def taskInWorkflow(self, taskid):
        """ Returns whether taskid is in workflow

            Args:
                taskid: ID of task to lookup
            Returns:
                boolean: True if found, else False
        """
        for phase in self.phasesToRun[constants.OPT_POSTCHECK]:
            if phase.getTask(taskid) is not None:
                return True
        return False

    def refIdInWorkflow(self, taskid):
        """ Returns whether taskid is in workflow

            Args:
                taskid: ID of task to lookup
            Returns:
                boolean: True if found, else False
        """
        for phase in self.phasesToRun[constants.OPT_POSTCHECK]:
            if phase.getTask(taskid) is not None:
                return True
        return False

    def tagInWorkflow(self, tag):
        """ Returns whether tag is in workflow

            Args:
                tag: ID of tag to lookup
            Returns:
                boolean: True if found, else False
        """
        if self.execute.getTag(tag) is not None:
            return True
        return False

    def eligibleDisplayTasks(self, servertypes, servernames, excluded,
                                   force, version_checker):
        """ returns True if there are non-completed eligible tasks in this
            phase, or False if there are none"""
        # split the excluded string into a list
        excludes = []
        if excluded != None:
            excludes = [x.strip() for x in excluded.split(',')]
        for dtask in self.display.tasks:
            if dtask.isParallelStatusTask():
                if not dtask.sequenceNoneToRun(servertypes, servernames,
                            excludes,
                            input, force, version_checker):
                    return True
            else:
                if dtask.shouldRunOnHost(servertypes, servernames, excludes,
                            input, force, version_checker):
                    # if task status is not in SUCCESS_STATUSES then it
                    # could be eligible for run
                    if not dtask.status in constants.SUCCESS_STATUSES:
                        return True
        return False

    def getExecutePhase(self):
        """ returns execute phase of workflow

            Args:
                none
            Return:
                phase - ie list of tasks
        """
        return self.execute

    def getTask(self, taskid):
        """ Returns task

            Args:
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

            Args:
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
                    log.debug("Running phase %d of %d, failed %s" % \
                               ((i + 1), numPhases, self.failed))
                    sysfilename = options.getSysStatusName()

                    phase = self.phasesToRun[options.phase][i]
                    (numSuccess, numFailed, numSkipped, carry_on) = \
                          phase.process(term_size,
                                 exclude,
                                 sysfilename,
                                 options)

                    if numFailed > 0:
                        self.failed = True
                    singleTask = None
                    listlen = 0

                    # Determine if exited phase in middle, and not for
                    # user input
                    if not options.list and not carry_on:
                        if self.trapped:
                            # Finished early due to interrupt
                            return WorkflowStatus(WorkflowStatus.FAILED,
                               "STOPPING due to interrupt")
                        elif self.failed:
                            # Finished phase early with failure
                            log.debug("Finished early with one or more "
                                      "failure")
                            return WorkflowStatus(WorkflowStatus.FAILED,
                               "STOPPING as requested")
                        else:
                            # Finished phase early without failure, eg escape
                            log.debug("Finished early with no failures")
                            return WorkflowStatus(WorkflowStatus.COMPLETE,
                               "STOPPING as requested")

                    # if we have not stopped already then check whether we
                    # should stop due to tasklist exhausted.
                    # If running specified task(s) and none of the tasks are
                    # in subsequent phases then we have finished
                    if options.task is not None:
                        listlen = len(options.task)
                        if listlen == 1:
                            singleTask = options.task[0]
                            log.debug("Single task is %s" % singleTask)
                            if phase.getTask(singleTask) is not None:
                                log.debug("STOPPING workflow as " \
                                            "ran chosen task")
                                if self.failed and not options.list:
                                    return WorkflowStatus(\
                                        WorkflowStatus.FAILED,
                                         WORKFLOW_FINISHED_LINE)
                                else:
                                    return WorkflowStatus(\
                                        WorkflowStatus.COMPLETE,
                                         WORKFLOW_FINISHED_LINE)
                        else:
                            log.debug("Checking for tasks in later phases")
                            all_done = True
                            # check whether any tasks are in subsequent phases
                            for t in options.task:
                                for p in range(i + 1, numPhases):
                                    if self.phasesToRun[options.phase][p].\
                                                   getTask(t) is not None:
                                        all_done = False
                            if all_done:
                                log.debug("STOPPING workflow "\
                                          "- no tasks in later phases")
                                if self.failed and not options.list:
                                    return WorkflowStatus(\
                                        WorkflowStatus.FAILED,
                                         WORKFLOW_FINISHED_LINE)
                                else:
                                    return WorkflowStatus(\
                                        WorkflowStatus.COMPLETE,
                                         WORKFLOW_FINISHED_LINE)

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
                        if (not options.yes and not options.list and \
                            not options.automate):
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

    def processManualReset(self, o):
        """ work through phase tasks processing manual reset
            NB
            Args:
                o: parameters
                phase: phase in which manual changes are to take place
            Returns:
                boolean: True if processed ok, else False
        """
        log.debug("process manual reset")
        phaselist = []
        phaselist.append(self.execute)
        startindex = 0
        endindex = 0

        for phase in phaselist:
            log.debug("Processing reset for phase {0}".\
                     format(phase.name))
            numTasksInPhase = len(phase.tasks)

            if o.tag != None and o.tag != "":
                tagindex = phase.getTag(o.tag)
                if tagindex == None:
                    log.info("Tag {0} not found in {1} phase".\
                               format(o.tag, phase.name))
                    return constants.R_ERROR
                else:
                    endindex = tagindex
                    log.debug("tag found - index {0}".format(tagindex))
                    ind = tagindex
                    while ind < numTasksInPhase:
                        if phase.tasks[ind].task.isTag() and \
                           not phase.tasks[ind].task.is_start:
                            # we have found the end of the tag
                            startindex = ind - 1
                            # exit the while loop
                            break
                        ind = ind + 1
                    if ind == numTasksInPhase:
                        log.debug("End of tag {0} not found - assume "\
                                  "end of phase is end of tag. ind={1}".\
                                  format(o.tag, ind))
                        startindex = ind - 1
                if not self.resetCandidates(o, phase, startindex, endindex):
                    log.error("\nStatus of dependent task(s) " \
                                  "prevent tag reset")
                    return constants.R_DEPENDENCY_CONFLICT

            if o.task != None and o.task != []:
                log.debug("processing task list")
                startindex = numTasksInPhase - 1
                endindex = 0
                if not self.resetCandidates(o, phase, startindex, endindex):
                    log.error("\nStatus of dependent task(s) " \
                              "prevent task(s) reset")
                    return constants.R_DEPENDENCY_CONFLICT
            return constants.R_OK

    def resetCandidates(self, o, executePhase, startindex, endindex):
        """ reverse through a range of tasks resetting candidates
        Args:
            o: parameters
            executePhase: the execute phase of the workflow
            startindex: the index at which to start iteration
            endindex: the index at which to end iteration
        Returns:
            boolean: False if dependency error encountered, otherwise True
        """
        ret = True
        updatedTasks = []
        updatesInfo = []
        log.debug("reset candidates")
        ind = startindex
        while ind >= endindex:
            # if this is a parallel task then we need to reverse through
            # it
            tasktocheck = executePhase.tasks[ind]
            log.debug("Assessing task %s at ind %s for reset" % \
                          (tasktocheck.task.name, ind))
            if tasktocheck.task.isParallel():
                log.debug("task is a parallel")
                # get the tasks from the sequences
                # need to iterate tasks in reverse order
                for s in reversed(tasktocheck.sequences):
                    for t in reversed(s.tasks):
                        candidateReset = self.resetCandidate(o, executePhase, \
                                   t, s, updatesInfo, updatedTasks)
                        if not candidateReset:
                            ret = False
            else:
                candidateReset = self.resetCandidate(o, executePhase, \
                        tasktocheck, None, updatesInfo, updatedTasks)
                if not candidateReset:
                    ret = False
            ind = ind - 1

        if len(updatesInfo) > 0:
            log.info("\n")
            for i in updatesInfo:
                log.info("{0}".format(i))

        if len(updatedTasks) > 0:
            if ret:
                log.info("\nThe following tasks are eligible for reset:\n")
                for u in updatedTasks:
                    log.info("{0}".format(u))
            else:
                log.debug("\nThe following tasks are eligible for reset:\n")
                for u in updatedTasks:
                    log.debug("{0}".format(u))
        else:
            log.info("\nNo tasks are eligible for reset")
        return ret

    def resetCandidate(self, o, executePhase, tasktocheck, sequence,
                                                  updatesInfo, updatedTasks):
        """ process single task reset candidates
        Args:
            o: parameters
            executePhase: the execute phase of the workflow
            tasktochedk: the task we are processing
            sequence: sequence if tasktocheck is in parallel, else None
            updatesInfo: list of update info msgs - to be appended to as needed
            updatedTasks: list of updates - to be appended to as needed
        Return:
            boolean: False if dependency conflict, otherwise True
        """
        taskid = tasktocheck.task.name
        hostname = "unknown"
        if tasktocheck.host != None:
            hostname = tasktocheck.host.hostname

        resettask = True
        if o.task != None and taskid not in o.task:
            log.debug("taskid %s is not in task list" % taskid)
            resettask = False
        if tasktocheck.task.isTag():
            resettask = False

        if resettask:

            log.debug("considering task %s on server %s" % (taskid, \
                                                                     hostname))
            candidate = self.serverOkForManualReset(executePhase, \
                                                             tasktocheck, o)

            if candidate:

                if tasktocheck.status in \
                                        constants.INIT_STATUSES:
                    updatesInfo.insert(0,
                          "Task {0} on {1} will not be reset as it is has " \
                                 "{2} status".format(\
                              taskid, \
                              hostname, \
                              tasktocheck.status))
                    return True

                dependents = []
                ex = self.execute.getDependencyConflictsByStatus(
                           taskid, hostname,
                           constants.INIT_STATUSES, sequence)
                post = self.postcheck.getDependencyConflictsByStatus(
                           taskid, hostname,
                           constants.INIT_STATUSES, sequence)
                dependents = dependents + ex + post
                dependentsError = False
                if dependents != []:
                    dependentscsv = ",".join(dependents)
                    log.debug("Dependent(s) {0} that are not in " \
                                  "initial, skipped or reset state " \
                                  "found for task {1}".\
                              format(dependentscsv, taskid))
                    dependentsError = True
                    if o.force:
                        status = WorkflowStatus(WorkflowStatus.USER_INPUT,
                             "Are you sure you want to force manual reset " \
                             "for task {0} on {1} when task(s) ({2}) are in " \
                             "completed/started state? Continue (y/n):\n".\
                                   format(taskid,
                                         tasktocheck.host.hostname,
                                         dependentscsv))
                        if self.input.askContinue(status):
                            log.info("Force manual reset confirmed")
                            dependentsError = False
                        else:
                            log.info("Force manual reset cancelled")
                    if dependentsError:
                        updatesInfo.insert(0,
                            "Completed/started dependent(s) ({0}) prevent " \
                            "manual reset for task {1} on {2}".\
                                   format(dependentscsv, taskid, hostname))
                        return False

                if not dependentsError:
                    updatesInfo.insert(0, "Resetting task {0} on {1} " \
                                 "will change status from " \
                                 "{2} to {3}".format(\
                              taskid, hostname, \
                              tasktocheck.status, \
                              constants.MANUAL_RESET))
                    updatedTasks.insert(0, "Task id: %s on server %s" % \
                                   (taskid, hostname))
                    tasktocheck.status = constants.MANUAL_RESET

        return True

    def serverOkForManualReset(self, phase, tasktocheck, o):
        """ assess whether server is valid for manual fix/reset according to
            the input params
            Args:
                phase: the phase being processed
                tasktocheck: the phase task being processed
                o: the parameters
            Returns: True if task matches the server criteria, otherwise False
        """
        okservertype = False
        okservername = False
        if o.servertypes != [constants.ALL]:
            for servertype in o.servertypes:
                if tasktocheck.host.servertype == servertype:
                    okservertype = True
        else:
            okservertype = True

        if o.servernames != [constants.ALL]:
            for servername in o.servernames:
                if tasktocheck.host.hostname == servername:
                    okservername = True
        else:
            okservername = True

        candidate = True
        if okservertype and okservername:
            log.debug("server ok according to servertype/servername")
            if o.exclude != None:
                excludes = []
                # Now strip of spaces
                excludes = [x.strip() for x in o.exclude.split(',')]
                for excludedServer in excludes:
                    if tasktocheck.host.hostname == excludedServer:
                        log.debug("server in exclusion list")
                        candidate = False
        else:
            log.debug("server not ok for servertype/servername")
            candidate = False

        return candidate


class WorkflowPhase:
    """
    Represents a workflow for a particular phase
    """

    def __init__(self, name, wfsys, alwaysRun=False, askSkip=False):
        """ Initialises the workflow phase.

            Args:
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

    def insertDynamicIntoGroup(self, task, hosts, inds, position, menuMsgs):
        """ Insert task and host from a particular index position to the
            workflow with INITIAL state

            Args:
                task: the task to insert
                hosts: the hosts object to determine which hosts to expand to
                inds: list of indices of the reference task expanded instances
                position: before or after
                menuMsgs: list to hold messages for display during interaction
            Returns:
        """
        #check server and hosts against reference task
        if len(inds) == 0:
            menuMsgs.append("No reference tasks for insertion")
            return False
        else:
            log.debug("num reference tasks found for dynamic insert is %s" % \
                    len(inds))

        if task.needsHost():
            if task.servertype == "*":
                tsks = []
                types = hosts.get_types()
                for servertype in types:
                    tsks.append(task.copy(servertype))
            else:
                tsks = [task]

            # indcnt takes us through the indices
            indcnt = 0
            # offsets adjust an index to account for prior insertions and
            # to account for relative position
            offsetinserts = 0
            offsetpos = 0
            if position == constants.DYNAMIC_AFTER:
                offsetpos = 1

            for eachtask in tsks:
                hostList = utils.getHostsThatApply(eachtask, hosts, log)
                for host in hostList:
                    stasks = eachtask.getStatusTasks(host)

                    for stsk in stasks:
                        log.debug("inserting dynamic task with host %s " \
                                  "servertype %s" % \
                                (stsk.host.hostname, stsk.task.servertype))

                        # check our insertion task is compatible
                        refstatustask = self.tasks[inds[indcnt] + \
                                                  offsetinserts]
                        if stsk.host.hostname == \
                             refstatustask.host.hostname and \
                             stsk.task.servertype == \
                             refstatustask.task.servertype:
                            pass
                        else:
                            menuMsgs.append("Group %s task %s is not " \
                                 "compatible with reference task %s" % \
                               (task.gid, task.name, refstatustask.task.name))
                            log.debug("group %s task %s is not " \
                                      "compatible with reference task %s" \
                                      "- stsk host %s reftsk host %s stsk " \
                                      "server %s reftsk server %s" % \
                               (task.gid, task.name, refstatustask.task.name,
                                stsk.host.hostname,
                                refstatustask.host.hostname,
                                stsk.task.servertype,
                                refstatustask.task.servertype))
                            return False
                        log.debug("insert dynamic task at index %s + %s + %s" \
                           % (inds[indcnt], offsetinserts, offsetpos))
                        self.tasks.insert(inds[indcnt] + offsetinserts +
                                          offsetpos, stsk)
                        offsetinserts = offsetinserts + 1
                        indcnt = indcnt + 1
            # here we can assume that since a group must all share the
            # same server and hosts
            # and workfile and hosts file are checked for changes
            # then number of ref and insertion tasks must match
            if indcnt != len(inds):
                menuMsgs.append("Number of insertion tasks %s does " \
                                "not match number of reference tasks %s" % \
                              (len(tsks), len(inds)))
                #return False

        elif task.isParallel():
            menuMsgs.append("Cannot dynamically add a parallel task")
            return False
        else:
            menuMsgs.append("Unexpectedly trying to dynamically add a "
                            "task which does not need a host")
            return False
        return True

    def insertDynamic(self, task, hosts, ind, menuMsgs):
        """ Insert task and host from a particular index position to the
            workflow with INITIAL state

            Args:
                task: the task to insert
                hosts: the hosts object to determine which hosts to expand to
                ind: the index from which the expanded tasks are to be inserted
                menuMsgs: list to hold messages for display during interaction
            Returns:
                boolean: True if inserted ok, else False
                """
        if ind > (len(self.tasks) + 1):
            menuMsgs.append("Invalid index (%s) for insertion of " \
                            "dynamic task" % ind)
            return False

        if task.needsHost():
            if task.servertype == "*":
                tasks = []
                types = hosts.get_types()
                for servertype in types:
                    tasks.append(task.copy(servertype))
            else:
                tasks = [task]

            for eachtask in tasks:
                hostList = utils.getHostsThatApply(eachtask, hosts, log)
                for host in hostList:
                    stasks = eachtask.getStatusTasks(host)
                    for stsk in stasks:
                        log.debug("inserting task with host %s "
                          "servertype %s" % (stsk.host.hostname,
                                             stsk.task.servertype))
                        self.tasks.insert(ind, stsk)
                        ind = ind + 1
        elif task.isParallel():
            menuMsgs.append("Cannot dynamically add a parallel task")
            return False
        else:
            menuMsgs.append("Unexpectedly trying to dynamically add "
                            "a task which does not need a host")
            return False
        return True

    def removeDynamic(self, dyntaskid, dyntype, menuMsgs):
        """ Remove dynamic task from workflow by id

            Args:
                dyntaskid: the id of the dynamic task to be removed
                dyntype: constants.DYNAMIC_ESCAPE or constants.DYNAMIC_PAUSE
                menuMsgs: list to hold messages for display during interaction
            Returns:
                boolean: True if task removed, else False
        """
        taskdict = self.getTaskIndices(dyntaskid)
        indxs = taskdict[constants.TASK_LIST]
        tasksFound = len(indxs)
        tasksForDeletion = []
        if tasksFound == 0:
            log.debug("Unable to find dynamic task %s in workflow" % dyntaskid)
            return False
        for indx in indxs:
            log.debug("index for deletion is %s" % indx)
            tsk = self.tasks[indx]
            if dyntype == constants.DYNAMIC_ESCAPE and \
                    not isinstance(tsk, EscapeStatusTask):
                menuMsgs.append("Task %s for removal was found "
                        "not to be an escape" % tsk.task.name)
                return False
            elif dyntype == constants.DYNAMIC_PAUSE and \
                      not isinstance(tsk, PauseStatusTask):
                menuMsgs.append("Task %s for removal was found "
                         "not to be a pause" % tsk.task.name)
                return False
            if not tsk.task.isDynamic():
                menuMsgs.append("Task %s for removal was found "
                         "not to be dynamic" % tsk.task.name)
                return False
            log.debug("task %s for removal " % tsk.task.name)
            tasksForDeletion.append(tsk)
        for taskForDel in tasksForDeletion:
            self.tasks.remove(taskForDel)
        log.debug("removed %s instances of dynamic task %s from workflow" % \
                    (tasksFound, dyntaskid))
        return True

    def isEquivalent(self, phase):
        """ Compares this workflow phase with that described by phase, and
            if they are the same ignoring status then they are equivalent

            Args:
                phase: WorkflowPhase to compare against
            Returns:
                boolean: True if same ignoring status, False if different
        """
        if self.name != phase.name:
            log.debug("Names on Phase differ: %s/%s" %
                  (self.name, phase.name))
            return False

        i = 0
        dynamic_tasks_in_flow = 0
        dynamic_tasks_in_phase = 0
        # get number of tasks in phase
        tasksInPhase = len(phase.tasks)
        # progress through the tasks in the workflow
        for a in self.tasks:
            #if this is a dynamic pause or escape then do not perform
            # comparison nor increment the index
            if a.task.isDynamic():
                dynamic_tasks_in_flow = dynamic_tasks_in_flow + 1
            else:
                # progress through the phase task indices until
                # find a non-dynamic task
                while i < len(phase.tasks) and phase.tasks[i].task.isDynamic():
                    dynamic_tasks_in_phase = dynamic_tasks_in_phase + 1
                    i = i + 1
                # provide protection here against index going out of
                # range
                if not i < tasksInPhase:
                    log.debug("Index %s for task in phase has gone beyond " \
                              "range %s without finding a nondynamic task " \
                              "for comparison" % \
                        (i, tasksInPhase))
                    return False
                if not a.isEquivalent(phase.tasks[i]):
                    log.debug("task %s is not equivalent to task %s" % \
                            (a.task.name, phase.tasks[i].task.name))
                    return False
                i = i + 1
        # now progress thru any phase tasks which are beyond the self.tasks
        while i < len(phase.tasks):
            if phase.tasks[i].task.isDynamic():
                dynamic_tasks_in_phase = dynamic_tasks_in_phase + 1
            else:
                log.debug("Unmatched non-dynamic task %s in phase" % \
                          phase.tasks[i].task.name)
                return False
            i = i + 1

        # count the number of non dynamic tasks in each and make sure
        # it is the same
        if (len(self.tasks) - dynamic_tasks_in_flow) != \
                   (len(phase.tasks) - dynamic_tasks_in_phase):
            log.debug("Number of tasks differ: %d/%d" %
                  ((len(self.tasks) - dynamic_tasks_in_flow), \
                   (len(phase.tasks) - dynamic_tasks_in_phase)))
            return False

        return True

    def getTask(self, taskid):
        """ Returns WTask object if its in phase

            Args:
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

    def hasDependentsOnTask(self, taskid):
        """ Identifies whether phase has any tasks dependent on taskid

            Args:
                taskid: ID of task to lookup
            Returns:
                boolean: True if dependents found, else False
        """
        for task in self.tasks:
            inParallel = False
            if task.isParallelStatusTask():
                # get the tasks from the sequences
                inParallel = task.task.name
                seqtasks = []
                for s in task.sequences:
                    for t in s.tasks:
                        if not t.task.isTag():
                            if t.task.dependency is not None:
                                dependencies = \
                                     utils.split_commas(t.task.dependency)
                                for dep in dependencies:
                                    if dep == taskid:
                                        return True
            else:
                if not task.task.isTag():
                    if task.task.dependency is not None:
                        dependencies = \
                                     utils.split_commas(task.task.dependency)
                        for dep in dependencies:
                            if dep == taskid:
                                return True
        return False

    def getDependencyConflictsByStatus(self, targetTask, hostname, \
                                           statusList, sequence):
        """ Identifies whether phase has any tasks dependent on targetTask for
            which the status is NOT in the supplied statusList
            NB
            Args:
                targetTask: ID of task whose dependencies we are checking
                hostname: the host on which the target task is to run
                statusList: list of status values
                sequence: sequence if targetTask in parallel, otherwise None
            Returns:
                [] : matchingDependents - list of completed dependents found
        """
        matchingDependents = []
        intraParallel = False
        for task in self.tasks:

            if task.isParallelStatusTask():
                # get the tasks from the sequences
                #  no need to iterate tasks in reverse order
                for s in task.sequences:
                    for t in s.tasks:
                        if self.dependencyConflict(t, targetTask,
                                         hostname, statusList, sequence):
                            matchingDependents.append("%s on %s" \
                                                        % (t.task.name,\
                                                          t.host.hostname))
            else:
                if self.dependencyConflict(task, targetTask,
                                     hostname, statusList, None):
                    matchingDependents.append("%s on %s" \
                                           % (task.task.name, \
                                              task.host.hostname))

        log.debug("MatchingDependents : %s" % matchingDependents)
        return matchingDependents

    def dependencyConflict(self, task, targetTask, hostname, \
                      statusList, checksequence):
        """ identify whether this task depends on the target task and has a
            status which is NOT included in statusList
            Note that if the task and targetTask are in the same parallel
            then the the dependency is forced to depend on single server
            Args:
                task: the dependent task
                targetTask: the task whose dependents we are checking
                hostname: the host on which the target task is to run
                statusList: a list of statuses which are NOT conflicting
                checksequence: sequence if we need to check whether task
                and targetTask are in the same parallel, else None
            Returns:
                boolean: True if dependent has conflicting status, else False
        """
        ret = False

        if not task.task.isTag():
            if task.task.dependency is not None:
                dependencies = utils.split_commas(task.task.dependency)
                for dep in dependencies:
                    if dep == targetTask:
                        if task.status not in statusList:
                            intraParallel = False
                            if checksequence != None:
                                if checksequence.hasTask(task.task.name):
                                    intraParallel = True
                            if task.task.depsinglehost or intraParallel:
                                if task.host.hostname == hostname:
                                    ret = True
                            else:
                                ret = True
        return ret

    def getTaskTopLevelInd(self, taskId):
        """ get the index of the first instance of this task or index
            of enclosing parallel

            Args:
                 taskid: ID of task to lookup
            Returns:
                 returns index first task with this id, or of enclosing
                     parallel or None if matching task not found
        """
        ind = 0
        while ind < len(self.tasks):
            if self.tasks[ind].task.name == taskId:
                return ind
            elif self.tasks[ind].isParallelStatusTask():
                for s in self.tasks[ind].sequences:
                    for t in s.tasks:
                        if t.task.name == taskId:
                            return ind
            ind = ind + 1

        return None

    def getTaskIndices(self, taskId):
        """ Returns the indices for instances of a given task
            within master status so long as it is not within a parallel

            Args:
                 taskid: ID of task to lookup
            Returns:
                 returns a dictionary containing list of indices TASK_LIST
                 of any tasks found with the given task id,
                 and TASK_IN_GROUP which contains group id of the last
                 matching task (None if not in a group)
        """
        ret = {}
        taskInds = []
        taskInGroup = None
        ind = 0
        while ind < len(self.tasks):
            if self.tasks[ind].task.name == taskId:
                taskInGroup = self.tasks[ind].task.gid
                taskInds.append(ind)
            elif self.tasks[ind].task.gid == taskId:
                taskInds.append(ind)
            ind = ind + 1
        ret[constants.TASK_LIST] = taskInds
        ret[constants.TASK_IN_GROUP] = taskInGroup
        return ret

    def getTag(self, tag):
        """ Returns index of the start tag corresponding to tag

            Args:
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

            Args:
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

            Args:
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
            if self.wfsys.trapped:
                log.debug("Finishing for loop as interrupt has been caught")
                carry_on = False
                break
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
                            "found {0} so continuing to check".format(
                                     a.task.name))
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
                log.debug("Checking whether task %s is in task list or " \
                           "contains any item from task list" % \
                             a.task.name)
                run_on_server = False
                for t in options.task:
                    if a.containsTask(t):
                        run_on_server = True
                if run_on_server == False:
                    log.debug("Skipping task %s %s as task not in %s" % \
                           (a.task.name, self._getHostStr(a), options.task))
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
                run_on_server = a.shouldRunOnHost(options.servertypes,
                       options.servernames, excluded, self.wfsys.input,
                       options.force, options.version_checker)
                if a.status == constants.REACHED_VERSION or \
                   a.status == constants.PARAM_NOTMATCH:
                    list_skip_reason = "SKIP_%s" % (a.status)
                    list_skip_colour = constants.COLOURS.status[a.status]
            if run_on_server and a.hasDependency():
                # First check dependencies
                # a.task.dependency is id of task to check
                hostsToCheck = constants.ALL
                # Check passed on all hosts unless both this task and
                # dependency are in the same group
                dependencies = utils.split_commas(a.task.dependency)
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

            # if this is a parallel task then we need to split out into
            # tasks in order to assess whether any are due, and for
            # --list command to assess what to display
            if run_on_server:
                if self.askSkip and a.askSkip() and \
                          not options.list and not options.fix:
                    a.logDetails()
                    # Work out whether to skip or not
                    parallelComplete = False
                    if a.task.isParallel():
                        parallelComplete = a.sequenceNoneToRun(
                                 options.servertypes, options.servernames,
                                 excluded, self.wfsys.input,
                                 options.force, options.version_checker)

                    if (not (options.yes and \
                            not isinstance(a, PauseStatusTask))
                            and not options.automate and not parallelComplete):
                        ret_val = self.wfsys.input.askRunSkipTask(a, excluded)
                        if ret_val == 1:
                            run_on_server = False
                        elif ret_val == 2:
                            carry_on = False
                            break
            if options.list and not a.task.isTag():
                if a.task.isParallel():
                    tasks = a.listTasks(options.servertypes,
                                 options.servernames,
                                 excluded, self.wfsys.input,
                                 options.force, options.version_checker)
                    # Returns a list of tuples of task, run_on_server
                    for t, r in tasks:
                        if r:
                            log.info("RUN TASK {0}: {1}{2}\n".format(
                                t.getId(), t.getCmd(),
                                self._getHostStr(t)))
                            # for --list we assume all tasks that are run
                            # will be successful
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
                        # for --list we assume all tasks that are run will
                        # be successful
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
                    # --automate - do not prompt for any execution task or
                    # pause in workflow.
                    # --yes prompt for pause but not execution tasks.
                    #  Otherwise, prompt for all.
                    if options.automate or \
                            (options.yes and \
                             not isinstance(a, PauseStatusTask)):
                        # Just output question and then we'll output result
                        log.info(result.user_msg)
                        # Needed to set status for pause on automate used
                        a.setStatus(constants.SUCCESS)
                    else:
                        if not self.wfsys.input.askContinue(result):
                            carry_on = False
                            break
                        else:
                            # Needed to set status for pause when answered y
                            a.setStatus(constants.SUCCESS)
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
                log.debug("Writing results of listing to %s%s" % (
                                   sysfilename, constants.LISTFILE_SUFFIX))
                self.wfsys.write("%s%s" % (sysfilename,
                                 constants.LISTFILE_SUFFIX))
            else:
                self.wfsys.write(sysfilename)

        if self.wfsys.trapped:
            log.debug("Finishing as interrupt has been caught")
        return self._postPhaseProcess(options.list, carry_on)

    def _getHostStr(self, task):
        """ Returns the hostname representation of task

            Args:
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

            Args:
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

            Args:
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

            Args:
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

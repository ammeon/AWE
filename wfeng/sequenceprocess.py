"""Represents the different task objects
@copyright: Ammeon Ltd
"""
from fabric.context_managers import settings, hide, show
from fabric.network import disconnect_all
from wfeng import constants
import logging
import multiprocessing
from wfeng import utils
from wfeng.status import StatusObject, WorkflowStatus
from wfeng.engformatter import WfengFormatter
import threading
import sys
import traceback
import os
import signal


def dumpstack(signal, frame):
    f = open("/tmp/seqdump_workflow.log.{0}".format(os.getpid()), "w")
    id2name = dict([(th.ident, th.name) for th in threading.enumerate()])
    code = []
    for threadId, stack in sys._current_frames().items():
        code.append("\n# Thread: %s(%d)" % \
                       (id2name.get(threadId, ""), threadId)
)
        for filename, lineno, name, line in traceback.extract_stack(stack):
            code.append('File: "%s", line %d, in %s' % (filename, lineno, name)
)
            if line:
                code.append("  %s" % (line.strip()))
    f.write("\n".join(code))
    f.close()


class SequenceProcess(multiprocessing.Process):
    def __init__(self, sequence, outputfunc, phasename, wfsys,
                       host_colour, tasklist, alwaysRun, options,
                       queue):
        super(SequenceProcess, self).__init__()
        self.output_func = outputfunc
        self.phasename = phasename
        self.seq = sequence
        self.status = None
        self.wfsys = wfsys
        self.host_colour = host_colour
        self.tasklist = tasklist
        self.alwaysRun = alwaysRun
        self.options = options
        self.queue = queue
        self.logger = None
        # Add handler for subprocesses
        self.subproc = SubProcessLogHandler(wfsys.logqueue)
        formatter = WfengFormatter('%(asctime)s %(message)s')
        self.subproc.setFormatter(formatter)
        self.subproc.setLevel(constants.TRACE)

    def interrupt_handler(self, signal, frame):
        """ Output that Ctrl C has been caught"""
        # Updates the copy of wfsys owned by this sub-process and has
        # different log statement. Use print so goes directly to screen,
        # rather than through event channels
        print "INTERRUPT CAUGHT - sub-process will stop after current " \
                  "task on %s has finished" % self.seq.tasks[0].host.hostname
        self.wfsys.trapped = True

    def run(self):
        """ Runs each of its tasks sequentially unless tasklist
            is specified"""
        signal.signal(signal.SIGUSR1, dumpstack)
        # Update the signal handler for Ctrl-C to be this local one
        signal.signal(signal.SIGINT, self.interrupt_handler)
        logging.addLevelName(constants.TRACE, "TRACE")
        logging.addLevelName(constants.DEBUGNOTIME, "DEBUGNOTIME")
        # Put our logger on the root logger
        root_logger = logging.getLogger()
        root_logger.handlers = []
        root_logger.addHandler(self.subproc)
        self.logger = root_logger
        try:
            for i in range(len(self.seq.tasks)):
                if self.wfsys.trapped:
                    self.logger.info(
                         "Stopping before task %s on %s due to Ctrl-C" %
                                     (self.seq.tasks[i].task.name,
                                     self.seq.tasks[i].host.hostname))
                    self.seq.wfstatus.value = \
                          self.seq.getWfValue(WorkflowStatus.FAILED)
                    return
                hostip = self.seq.tasks[i].host.ipaddr
                if self.seq.tasks[i].task.servertype == constants.LOCAL or \
                    self.seq.tasks[i].task.run_local == True:
                    hostip = constants.LOCAL
                hoststr = " on {0}".format(hostip)

                self.seq.should_run_task[i] = self._task_will_run(i,
                                                          self.logger)
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
                                                self.tasklist,
                                                self.alwaysRun,
                                                self.options,
                                                True,
                                                self.logger,
                                                self.host_colour)
                    self.logger.log(constants.TRACE,
                         "FINISHED task {0}".format(self.seq.tasks[i].getId()))

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

    def will_run(self, logger):
        """ Returns if there will be tasks to run in this sequence"""
        will_run = False
        for i in range(len(self.seq.tasks)):
            if self._task_will_run(i, logger):
                will_run = True
        return will_run

    def _task_will_run(self, i, logger):
        """ Returns whether this task in sequence needs to be run.

            Args:
               i, index into tasks array """

        will_run = True
        if not self.alwaysRun and \
            self.seq.tasks[i].status in constants.SUCCESS_STATUSES:
            will_run = False
        elif self.seq.should_run_task[i] == False:
            will_run = False
        elif self.seq.should_run_task[i] == True and \
              self.seq.tasks[i].hasDependency():
            dependencies = \
                   utils.split_commas(self.seq.tasks[i].task.dependency)
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
                        logger.log(constants.TRACE,
                           "Dependency {0} on {1} status {2}".format(\
                            depTask.name, hostsToCheck, dstatus))
                if dstatus not in constants.SUCCESS_STATUSES:
                    logger.debug(\
                       "Skipping task %s as dependency %s not passed %s" \
                       % (self.seq.tasks[i].task.name, dep,
                       dstatus))
                    will_run = False
                    break

        if self.seq.should_run_task[i] and self.tasklist != None:
            if self.seq.tasks[i].task.name not in self.tasklist:
                will_run = False
        return will_run


class SubProcessLogHandler(logging.Handler):
    """handler used by subprocesses
    It simply puts items on a Queue for the main process to log.
    """

    def __init__(self, queue):
        logging.Handler.__init__(self)
        self.queue = queue

    def emit(self, record):
        self.queue.put(record)

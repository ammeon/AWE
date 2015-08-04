"""Represents the different task objects
@copyright: Ammeon Ltd
"""
from wfeng import constants
import logging
import datetime
from wfeng import utils

log = logging.getLogger(__name__)


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
            log.error("Internal error, failed to find seq {0}".format(
                             self.seqname))
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
            log.debug("Writing results of listing to %s%s" % \
                  (options.getSysStatusName(), constants.LISTFILE_SUFFIX))
            wfsys.write("%s%s" % (options.getSysStatusName(), \
                               constants.LISTFILE_SUFFIX))
        else:
            wfsys.write(options.getSysStatusName())


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

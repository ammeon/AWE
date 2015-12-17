#!/usr/lib/python
""" Outer module that just invokes WorkflowEngine instance, set alias to
    this module
    @copyright: Ammeon Ltd

"""
import threading
import sys
import traceback
import os


def dumpstacks(signal, frame):
    f = open("/tmp/dump_workflow.log.{0}".format(os.getpid()), "w")
    id2name = dict([(th.ident, th.name) for th in threading.enumerate()])
    code = []
    for threadId, stack in sys._current_frames().items():
        code.append("\n# Thread: %s(%d)" % (id2name.get(threadId, ""), \
                                  threadId))
        for filename, lineno, name, line in traceback.extract_stack(stack):
            code.append('File: "%s", line %d, in %s' % \
                         (filename, lineno, name))
            if line:
                code.append("  %s" % (line.strip()))
    f.write("\n".join(code))
    f.close()

import signal
signal.signal(signal.SIGUSR1, dumpstacks)

if not os.environ.get("AWE_HOME"):
    # Use this for when invoke via ssh and user's profile is not run
    os.environ["AWE_HOME"] = "{0}/..".format(
             os.path.dirname(os.path.realpath(__file__)))
sys.path.append("{0}/lib".format(os.environ["AWE_HOME"]))

from wfeng.workflowengine import WorkflowEngine

if __name__ == "__main__":
    wfeng = WorkflowEngine()
    try:
        passed = wfeng.start()
    finally:
        wfeng.deletePidFile()
    if passed:
        sys.exit(0)
    else:
        sys.exit(1)

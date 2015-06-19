""" Outer module that just invokes WorkflowMgr instance, set alias to
    this module
@copyright: Ammeon Ltd
"""

from wfeng.wfeng import WorkflowEngine
import sys

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

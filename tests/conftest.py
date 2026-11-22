import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import tempfile  # noqa: E402

# The tool's private folder (markers, full recordings) goes into a throw-away
# folder during the tests, never into the real home folder.
import atexit  # noqa: E402
import shutil  # noqa: E402

os.environ["CHROMIQ_PROBE_HOME"] = tempfile.mkdtemp(prefix="probe-test-home-")
atexit.register(shutil.rmtree, os.environ["CHROMIQ_PROBE_HOME"], True)

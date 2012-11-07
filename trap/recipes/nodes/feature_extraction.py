import sys
from lofarpipe.support.lofarnode import LOFARnodeTCP
from lofarpipe.support.utilities import log_time
import trap.feature_extraction

class feature_extraction(LOFARnodeTCP):
    def run(self, transient, tkpconfigdir=None):
        with log_time(self.logger):
            trap.feature_extraction.logger = self.logger
            self.outputs['transient'] = trap.feature_extraction.extract_features(transient)
        return 0

if __name__ == "__main__":
    jobid, jobhost, jobport = sys.argv[1:4]
    sys.exit(feature_extraction(jobid, jobhost, jobport).run_with_stored_arguments())

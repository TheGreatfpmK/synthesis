import unittest
import subprocess
import logging

from test_utils import PayntTestUtils

"""
HybridTestSuite, which ensures that paynt works on the smoke level.
"""


class SynthesisTestSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 1.setup phase
        logging.info("[SETUP] - Preparing HybridTestSuite")
        # self.shared_data = ...

    def test_hybrid_herman_5(self):

        # 2.exercise phase
        process = subprocess.Popen([
            'python3',
            PayntTestUtils.get_path_to_paynt_executable(),
            '--project',
            PayntTestUtils.get_path_to_workspace_examples() + '/herman/5/',
            'hybrid',
            '--short-summary',
            '--constants', 'CMAX=0',
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stdout, stderr = process.communicate()
        # 3.verify phase
        self.assertIn("Hybrid: opt = 18.19306", str(stdout))


    @classmethod
    def tearDownClass(cls):
        # 4.teardown phase
        logging.info("[TEARDOWN] - Cleaning HybridTestSuite")
        # self.shared_data = None


if __name__ == '__main__':
    unittest.main()

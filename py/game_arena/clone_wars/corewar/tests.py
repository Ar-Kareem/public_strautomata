#! /usr/bin/env python
# coding: utf-8

import unittest
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / 'corewar'))
from tests.redcode_test import TestRedcodeAssembler
from tests.mars_test import TestMars

if __name__ == '__main__':
    unittest.main()


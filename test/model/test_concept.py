# Copyright 2019 PyI40AAS Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

import unittest

from aas import model


class IEC61360ConceptDescriptionTest(unittest.TestCase):
    def test_set_value(self):
        cp = model.IEC61360ConceptDescription(model.Identifier('test', model.IdentifierType.CUSTOM),
                                              {'de': 'test'},
                                              model.concept.IEC61360DataType.STRING,
                                              value_format=model.datatypes.Int,
                                              value=2)
        self.assertEqual(cp.value, 2)
        cp.value = None
        self.assertIsNone(cp.value)
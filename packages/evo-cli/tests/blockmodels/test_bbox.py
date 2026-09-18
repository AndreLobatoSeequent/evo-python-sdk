#  Copyright © 2025 Bentley Systems, Incorporated
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#      http://www.apache.org/licenses/LICENSE-2.0
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from __future__ import annotations

import unittest

import typer

from evo.blockmodels.endpoints.models import BBox, BBoxXYZ
from evo.cli.blockmodels._bbox import parse_bbox_ijk, parse_bbox_option, parse_bbox_xyz


class TestParseBboxIjk(unittest.TestCase):
    def test_valid(self) -> None:
        bbox = parse_bbox_ijk("0,10,0,10,0,10")
        self.assertIsInstance(bbox, BBox)
        self.assertEqual(bbox.i_minmax.min, 0)
        self.assertEqual(bbox.i_minmax.max, 10)

    def test_wrong_count_exits(self) -> None:
        with self.assertRaises(typer.Exit):
            parse_bbox_ijk("0,10,0,10")

    def test_non_numeric_exits(self) -> None:
        with self.assertRaises(typer.Exit):
            parse_bbox_ijk("a,b,c,d,e,f")


class TestParseBboxXyz(unittest.TestCase):
    def test_valid(self) -> None:
        bbox = parse_bbox_xyz("0.5,10.5,0,10,0,10")
        self.assertIsInstance(bbox, BBoxXYZ)
        self.assertEqual(bbox.x_minmax.min, 0.5)
        self.assertEqual(bbox.x_minmax.max, 10.5)

    def test_wrong_count_exits(self) -> None:
        with self.assertRaises(typer.Exit):
            parse_bbox_xyz("0,10,0,10")


class TestParseBboxOption(unittest.TestCase):
    def test_neither_returns_none(self) -> None:
        self.assertIsNone(parse_bbox_option(None, None))

    def test_both_given_exits(self) -> None:
        with self.assertRaises(typer.Exit):
            parse_bbox_option("0,10,0,10,0,10", "0,10,0,10,0,10")

    def test_ijk_only(self) -> None:
        bbox = parse_bbox_option("0,10,0,10,0,10", None)
        self.assertIsInstance(bbox, BBox)

    def test_xyz_only(self) -> None:
        bbox = parse_bbox_option(None, "0,10,0,10,0,10")
        self.assertIsInstance(bbox, BBoxXYZ)

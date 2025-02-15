# Copyright (c) MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
from functools import partial
from typing import Callable

import torch
from parameterized import parameterized

import monai
from monai.apps import ComponentLocator, ConfigComponent, ConfigExpression, ConfigItem
from monai.data import DataLoader, Dataset
from monai.transforms import LoadImaged, RandTorchVisiond
from monai.utils import optional_import

_, has_tv = optional_import("torchvision")

TEST_CASE_1 = [{"lr": 0.001}, 0.0001]

TEST_CASE_2 = [{"<name>": "LoadImaged", "<args>": {"keys": ["image"]}}, LoadImaged]
# test python `<path>`
TEST_CASE_3 = [{"<path>": "monai.transforms.LoadImaged", "<args>": {"keys": ["image"]}}, LoadImaged]
# test `<disabled>`
TEST_CASE_4 = [{"<name>": "LoadImaged", "<disabled>": True, "<args>": {"keys": ["image"]}}, dict]
# test `<disabled>`
TEST_CASE_5 = [{"<name>": "LoadImaged", "<disabled>": "true", "<args>": {"keys": ["image"]}}, dict]
# test non-monai modules and excludes
TEST_CASE_6 = [
    {"<path>": "torch.optim.Adam", "<args>": {"params": torch.nn.PReLU().parameters(), "lr": 1e-4}},
    torch.optim.Adam,
]
TEST_CASE_7 = [{"<name>": "decollate_batch", "<args>": {"detach": True, "pad": True}}, partial]
# test args contains "name" field
TEST_CASE_8 = [
    {"<name>": "RandTorchVisiond", "<args>": {"keys": "image", "name": "ColorJitter", "brightness": 0.25}},
    RandTorchVisiond,
]
# test execute some function in args, test pre-imported global packages `monai`
TEST_CASE_9 = ["collate_fn", "$monai.data.list_data_collate"]
# test lambda function, should not execute the lambda function, just change the string
TEST_CASE_10 = ["collate_fn", "$lambda x: monai.data.list_data_collate(x) + torch.tensor(var)"]


class TestConfigItem(unittest.TestCase):
    @parameterized.expand([TEST_CASE_1])
    def test_item(self, test_input, expected):
        item = ConfigItem(config=test_input)
        conf = item.get_config()
        conf["lr"] = 0.0001
        item.update_config(config=conf)
        self.assertEqual(item.get_config()["lr"], expected)

    @parameterized.expand(
        [TEST_CASE_2, TEST_CASE_3, TEST_CASE_4, TEST_CASE_5, TEST_CASE_6, TEST_CASE_7]
        + ([TEST_CASE_8] if has_tv else [])
    )
    def test_component(self, test_input, output_type):
        locator = ComponentLocator(excludes=["metrics"])
        configer = ConfigComponent(id="test", config=test_input, locator=locator)
        ret = configer.instantiate()
        if test_input.get("<disabled>", False):
            # test `<disabled>` works fine
            self.assertEqual(ret, None)
            return
        self.assertTrue(isinstance(ret, output_type))
        if isinstance(ret, LoadImaged):
            self.assertEqual(ret.keys[0], "image")

    @parameterized.expand([TEST_CASE_9, TEST_CASE_10])
    def test_expression(self, id, test_input):
        configer = ConfigExpression(id=id, config=test_input, globals={"monai": monai, "torch": torch})
        var = 100
        ret = configer.evaluate(locals={"var": var})
        self.assertTrue(isinstance(ret, Callable))

    def test_lazy_instantiation(self):
        config = {"<name>": "DataLoader", "<args>": {"dataset": Dataset(data=[1, 2]), "batch_size": 2}}
        configer = ConfigComponent(config=config, locator=None)
        init_config = configer.get_config()
        # modify config content at runtime
        init_config["<args>"]["batch_size"] = 4
        configer.update_config(config=init_config)

        ret = configer.instantiate()
        self.assertTrue(isinstance(ret, DataLoader))
        self.assertEqual(ret.batch_size, 4)


if __name__ == "__main__":
    unittest.main()

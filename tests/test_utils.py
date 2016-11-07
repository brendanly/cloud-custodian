# Copyright 2016 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import unittest
import time

from botocore.exceptions import ClientError
import ipaddress

from c7n import utils

from common import BaseTest


class Backoff(BaseTest):

    def test_retry_passthrough(self):
        def func(): return 42
        retry = utils.get_retry((), 5)
        self.assertEqual(retry(func), 42)

    def test_retry_errors(self):
        self.patch(time, 'sleep', lambda x: x)
        self.count = 0

        def func():
            self.count += 1
            raise ClientError({'Error': {'Code': 42}}, 'something')

        retry = utils.get_retry((42,), 5)

        try:
            retry(func)
        except ClientError:
            self.assertEqual(self.count, 5)
        else:
            self.fail("should have raised")

    def test_delays(self):
        self.assertEqual(
            list(utils.backoff_delays(1, 256)),
            [1, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0])

    def test_delays_jitter(self):
        for idx, i in enumerate(utils.backoff_delays(1, 256, jitter=True)):
            maxv = 2 ** idx
            self.assertTrue(i > 0)
            self.assertTrue(i < maxv)


class WorkerDecorator(BaseTest):

    def test_method_worker(self):

        class foo(object):

            @utils.worker
            def bar(self, err=False):
                """abc"""
                if err:
                    raise ValueError("foo")
                return 42

        i = foo()
        log_output = self.capture_logging("c7n.worker")
        self.assertEqual(i.bar(), 42)
        self.assertRaises(ValueError, i.bar, True)
        self.assertTrue(
            log_output.getvalue().startswith(
                "Error invoking tests.test_utils.bar\nTraceback"))

    def test_function_worker(self):
        @utils.worker
        def rabbit(err=False):
            """what's up doc"""
            if err:
                raise ValueError("more carrots")
            return 42

        self.assertEqual(rabbit.__doc__, "what's up doc")
        log_output = self.capture_logging("c7n.worker")
        self.assertEqual(rabbit(), 42)
        self.assertEqual(log_output.getvalue(), "")
        self.assertRaises(ValueError, rabbit, True)
        self.assertTrue(
            log_output.getvalue().startswith(
                "Error invoking tests.test_utils.rabbit\nTraceback"))
        self.assertTrue("more carrots" in log_output.getvalue())


class UtilTest(unittest.TestCase):

    def test_ipv4_network(self):
        n1 = utils.IPv4Network(u'10.0.0.0/16')
        n2 = utils.IPv4Network(u'10.0.1.0/24')
        self.assertTrue(n2 in n1)
        self.assertFalse(n1 in n2)

        n3 = utils.IPv4Network(u'10.0.0.0/8')
        self.assertTrue(n2 in n3)
        self.assertTrue(n1 in n3)

        n4 = utils.IPv4Network(u'192.168.1.0/24')
        self.assertFalse(n4 in n3)

        a1 = ipaddress.ip_address(u'10.0.1.16')
        self.assertTrue(a1 in n1)
        self.assertTrue(a1 in n3)
        self.assertFalse(a1 in n4)

    def test_chunks(self):
        self.assertEqual(
            list(utils.chunks(range(100), size=50)),
            [range(50), range(50, 100, 1)])
        self.assertEqual(
            list(utils.chunks(range(1), size=50)),
            [range(1)])
        self.assertEqual(
            list(utils.chunks(range(60), size=50)),
            [range(50), range(50, 60, 1)])

    def test_type_schema(self):
        self.assertEqual(
            utils.type_schema('tester'),
            {'type': 'object',
             'additionalProperties': False,
             'required': ['type'],
             'properties': {
                 'type': {'enum': ['tester']}}})
        res = utils.type_schema('tester', inherits=['tested'])
        self.assertIn({'$ref': 'tested'}, res['allOf'])

    def test_generate_arn(self):
        self.assertEqual(
            utils.generate_arn('s3', 'my_bucket'),
            'arn:aws:s3:::my_bucket')
        self.assertEqual(
            utils.generate_arn(
                'cloudformation',
                'MyProductionStack/abc9dbf0-43c2-11e3-a6e8-50fa526be49c',
                region='us-east-1',
                account_id='123456789012',
                resource_type='stack'),
            'arn:aws:cloudformation:us-east-1:123456789012:'
            'stack/MyProductionStack/abc9dbf0-43c2-11e3-a6e8-50fa526be49c')
        self.assertEqual(
            utils.generate_arn(
                'rds',
                'mysql-option-group1',
                region='us-east-1',
                account_id='123456789012',
                resource_type='og',
                separator=':'),
            'arn:aws:rds:us-east-1:123456789012:og:mysql-option-group1')

    def testCamelCase(self):
        d = {'zebraMoon': [{'instanceId': 123}, 'moon'],
             'color': {'yellow': 1, 'green': 2}}
        self.assertEqual(
            utils.camelResource(d),
            {'ZebraMoon': [{'InstanceId': 123}, 'moon'],
             'Color': {'Yellow': 1, 'Green': 2}})

    def test_snapshot_identifier(self):
        identifier = utils.snapshot_identifier('bkup', 'abcdef')
        # e.g. bkup-2016-07-27-abcdef
        self.assertEqual(len(identifier), 22)

    def test_load_error(self):
        original_yaml = utils.yaml
        utils.yaml = None
        self.assertRaises(RuntimeError, utils.yaml_load, 'testing')
        utils.yaml = original_yaml

    def test_format_event(self):
        event = {
            'message': 'This is a test',
            'timestamp': 1234567891011,
        }
        event_json = (
            '{\n  "timestamp": 1234567891011, \n'
            '  "message": "This is a test"\n}'
        )
        self.assertEqual(utils.format_event(event), event_json)

    def test_date_time_decoder(self):
        dtdec = utils.DateTimeEncoder()
        self.assertRaises(TypeError, dtdec.default, 'test')

    def test_set_annotation(self):
        self.assertRaises(
            ValueError,
            utils.set_annotation,
            'not a dictionary',
            'key',
            'value',
        )

    def test_parse_s3(self):
        self.assertRaises(ValueError, utils.parse_s3, 'bogus')
        self.assertEqual(
            utils.parse_s3('s3://things'),
            ('s3://things', 'things', ''),
        )

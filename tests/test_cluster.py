import unittest

from acdhQos.cluster import Rancher


class DummyResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class DummySession:
    def get(self, *args, **kwargs):
        return DummyResponse({'data': []})


class ProcessWorkloadTests(unittest.TestCase):
    def setUp(self):
        self.rancher = Rancher.__new__(Rancher)
        self.rancher.base_url = 'https://example.invalid'
        self.rancher.clusters = {'cluster-id': 'test-cluster'}
        self.rancher.session = DummySession()

    def make_cfg(self, name='demo', publicEndpoints=None, labels=None):
        if publicEndpoints is None:
            publicEndpoints = [{'protocol': 'https', 'hostname': 'example.com'}]
        return {
            'name': name,
            'type': 'deployment',
            'namespaceId': 'namespace:demo',
            'containers': [{'image': 'nginx:latest'}],
            'publicEndpoints': publicEndpoints,
            'labels': labels or {},
            'workloadLabels': {},
            'annotations': {},
            'workloadAnnotations': {},
        }

    def test_skips_service_deployments(self):
        cfg = self.make_cfg(name='Service')

        result = self.rancher.processWorkload(cfg, {'id': 'proj-1', 'name': 'Project', 'clusterId': 'cluster-id'})

        self.assertIsNone(result)

    def test_skips_deployments_without_endpoint(self):
        cfg = self.make_cfg(name='demo', publicEndpoints=[])

        result = self.rancher.processWorkload(cfg, {'id': 'proj-1', 'name': 'Project', 'clusterId': 'cluster-id'})

        self.assertIsNone(result)

    def test_returns_payload_for_trackable_deployment(self):
        cfg = self.make_cfg(name='demo', publicEndpoints=[{'protocol': 'https', 'hostname': 'example.com'}])

        result = self.rancher.processWorkload(cfg, {'id': 'proj-1', 'name': 'Project', 'clusterId': 'cluster-id'})

        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'demo')
        self.assertEqual(result['endpoint'], 'https://example.com')


if __name__ == '__main__':
    unittest.main()

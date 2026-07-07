import unittest

from acdhQos.backend import Redmine


class DummyResponse:
    def __init__(self, status_code=200, text=''):
        self.status_code = status_code
        self.text = text


class DummySession:
    def __init__(self):
        self.calls = []

    def put(self, url, json=None):
        self.calls.append((url, json))
        return DummyResponse()


class SaveStructuredReportTests(unittest.TestCase):
    def setUp(self):
        self.redmine = Redmine.__new__(Redmine)
        self.redmine.baseUrl = 'https://redmine.example.invalid'
        self.redmine.logIssueId = 42
        self.redmine.session = DummySession()

    def test_formats_redmine_ids_as_textile_links(self):
        report = {
            'duplicates': [
                {
                    'redmine_id': '123',
                    'project': 'Project',
                    'users_short': 'User',
                    'namespace_1': 'ns',
                    'name_1': 'app-one',
                    'name_2': 'app-two',
                }
            ],
            'qos': [
                {
                    'redmine_id': '456',
                    'name': 'demo-service',
                    'endpoint': 'https://demo.example.invalid',
                    'service_type': 'Service',
                    'checks': [
                        {'check': 'Reachability', 'status': 'FAIL', 'details': 'down'},
                    ],
                }
            ],
        }

        self.redmine.saveStructuredReport(report)

        description = self.redmine.session.calls[0][1]['issue']['description']

        self.assertIn('#123', description)
        self.assertIn('#456', description)

    def test_omits_duplicate_rows_with_dev_domains(self):
        report = {
            'duplicates': [
                {
                    'redmine_id': '123',
                    'project': 'Project',
                    'users_short': 'User',
                    'namespace_1': 'ns',
                    'name_1': 'app-one',
                    'name_2': 'app-two',
                    'endpoint': 'https://demo-dev.acdh.oeaw.ac.at',
                },
                {
                    'redmine_id': '456',
                    'project': 'Project',
                    'users_short': 'User',
                    'namespace_1': 'ns',
                    'name_1': 'app-three',
                    'name_2': 'app-four',
                    'endpoint': 'https://demo.example.invalid',
                },
            ],
        }

        self.redmine.saveStructuredReport(report)

        description = self.redmine.session.calls[0][1]['issue']['description']

        self.assertNotIn('app-one', description)
        self.assertIn('app-three', description)

    def test_omits_passing_services_and_marks_passed_checks(self):
        report = {
            'qos': [
                {
                    'redmine_id': '789',
                    'name': 'fully-passing',
                    'endpoint': 'https://passing.example.invalid',
                    'service_type': 'Service',
                    'checks': [
                        {'check': 'Reachability', 'status': 'PASS', 'details': ''},
                        {'check': 'ACDH Logo', 'status': 'PASS', 'details': ''},
                        {'check': 'Helpdesk Email', 'status': 'PASS', 'details': ''},
                        {'check': 'Imprint Page', 'status': 'PASS', 'details': ''},
                        {'check': 'Accessibility', 'status': 'PASS', 'details': ''},
                    ],
                },
                {
                    'redmine_id': '790',
                    'name': 'mixed-results',
                    'endpoint': 'https://mixed.example.invalid',
                    'service_type': 'Service',
                    'checks': [
                        {'check': 'Reachability', 'status': 'PASS', 'details': ''},
                        {'check': 'ACDH Logo', 'status': 'FAIL', 'details': 'missing'},
                        {'check': 'Helpdesk Email', 'status': 'PASS', 'details': ''},
                        {'check': 'Imprint Page', 'status': 'PASS', 'details': ''},
                        {'check': 'Accessibility', 'status': 'PASS', 'details': ''},
                    ],
                },
            ],
        }

        self.redmine.saveStructuredReport(report)

        description = self.redmine.session.calls[0][1]['issue']['description']

        self.assertNotIn('fully-passing', description)
        self.assertIn('mixed-results', description)
        self.assertIn('✓', description)
        self.assertIn('!/images/false.png!', description)


if __name__ == '__main__':
    unittest.main()

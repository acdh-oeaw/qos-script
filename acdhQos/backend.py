import datetime
import json
import logging
import re
import time
import urllib
import requests
from requests.exceptions import RequestException

from acdhQos.interface import *
from acdhQos.redmine_helpers import format_container_description_textile


class RecordNotFound(Exception):
    pass

class RecordCreationFailed(Exception):
    data = None
    response = None
    
    def __init__(self, data, response):
        self.data = data
        self.response = response

class RecordDuplicated(Exception):
    id = None
    newData = None
    oldData = None

    def __init__(self, id, newData, oldData):
        self.id = id
        self.newData = newData
        self.oldData = oldData

class RecordError(Exception):
    pass

class Redmine(IBackend):
    customFields = None
    envTypes = None
    logIssueId = None
    defaultTrackerId = None
    defaultProjectId = None
    defaultStatus = None
    defaultPrority = None
    inContainerAppCategory = None
    baseUrl = None
    session = None
    api_key = None

    def __init__(self, baseUrl, auth=None, api_key=None, logIssueId=None, defTrackerId=7, defProjectId=164, defStatus=1, defPrority=2, inContainerAppCategory=52):
        # Normalize base URL by stripping trailing slash
        self.baseUrl = baseUrl.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ACDH-QoS-Redmine/1.0"})
        
        # Authentication priority: API key takes precedence over Basic Auth
        self.username = None
        self.password = None
        if auth is not None:
            self.username, self.password = auth

        if api_key:
            self.session.headers.update({"X-Redmine-API-Key": api_key})
            self.session.auth = None
        else:
            self.session.auth = auth

        self.logIssueId = logIssueId
        self.defaultTrackerId = defTrackerId
        self.defaultProjectId = defProjectId
        self.defaultStatus = defStatus
        self.defaultPrority = defPrority
        self.inContainerAppCategory = inContainerAppCategory
        self._min_interval = 1.0
        self._last_request_time = 0.0

        # custom fields
        self.customFields = {}
        resp = self._send('get', self.baseUrl + '/custom_fields.json')
        if resp is None or resp.status_code != 200:
            auth_method = 'API key' if api_key else 'Basic Auth'
            raise Exception(f'Failed to load Redmine custom fields (using {auth_method})')
        data = resp.json()
        for i in data['custom_fields']:
            self.customFields[i['name']] = i

        # environment types
        self.envTypes = {}
        resp = self._send(
            'get',
            self.baseUrl + '/issues.json',
            data={'cf_' + str(self.customFields['tags']['id']): 'environment type', 'status_id': '*', 'limit': 100},
        )
        if resp is None or resp.status_code != 200:
            raise Exception('Failed to load Redmine environment types')
        data = resp.json()
        for i in data['issues']:
            self.envTypes[i['subject'].lower().split(' ')[0]] = i['id']

    def _throttle(self):
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _send(self, method, url, **kwargs):
        self._throttle()
        try:
            resp = getattr(self.session, method)(url, **kwargs)
        except RequestException as e:
            logging.error(f'[Redmine] {method.upper()} {url} failed: {e}')
            return None
        except Exception as e:
            logging.error(f'[Redmine] unexpected error for {method.upper()} {url}: {e}')
            return None

        if resp.status_code >= 500:
            logging.warning(f'[Redmine] {method.upper()} {url} returned {resp.status_code}')

        return resp

    def begin(self):
        self.setupNotifications(False)
        
    def end(self, log, procServers):
        self.setupNotifications(True)
        if self.logIssueId is not None:
            self.saveLog(log, procServers)

    def saveLog(self, log, procServers):
        # get the current log and split it into entries - we must combine it with the new one
        url = '%s/issues/%s.json' % (self.baseUrl, str(self.logIssueId))
        resp = self._send('get', url)
        if resp is None or resp.status_code != 200:
            raise Exception('Fetching Redmine log issue failed')
        # Ensure description is properly decoded as UTF-8 string
        desc_raw = resp.json()['issue']['description']
        if isinstance(desc_raw, bytes):
            desc = self.parseRedmineDescription(desc_raw.decode('utf-8', errors='replace'))
        else:
            desc = self.parseRedmineDescription(str(desc_raw))
        log = self.parseLog(log)
        # now every desc and log element is an array of [severity, server, message, data]

        # combine logs by keeping all lines from the old ones which do not apply to
        # the servers processed in the new log and adding a complete new log to it
        desc = [i for i in desc if len(i) < 2 or (i[1] not in procServers and i[1] != '')]
        desc += log
        # Filter and deduplicate: keep only items with 4 elements (severity, server, message, data)
        desc = [tuple(i) if len(i) == 4 else None for i in desc]
        desc = [i for i in desc if i is not None]
        desc = list(set(desc))  # to avoid duplication of lines without the server
        desc.sort()

        # update the redmine issue
        formatted = []
        for item in desc:
            # item is now a tuple/list of (severity, server, message, data_field)
            severity, server, message, data_field = item
            if isinstance(data_field, str) and data_field.strip().startswith('{') and data_field.strip().endswith('}'):
                try:
                    container_info = json.loads(data_field)
                    data_field = format_container_description_textile(container_info)
                except Exception:
                    pass
            # Build the table row: join the 4 columns with pipes
            row = '|'.join([severity, server, message, data_field])
            formatted.append(row)
            # Log the row for debugging to verify correct formatting
            logging.debug(f'Table row: |{row}|')

        desc = '|Severity|Server|Message|Container Description|\n' + '\n'.join(formatted)
        # Ensure description is a proper UTF-8 string before sending
        if isinstance(desc, bytes):
            desc = desc.decode('utf-8', errors='replace')
        desc = str(desc)  # Ensure it's a string, not any other type
        data = {'issue': {
            'description': desc,
            'due_date': str(datetime.date.today())
        }}
        resp = self._send('put', url, json=data)
        if resp is None or (resp.status_code != 200 and resp.status_code != 204):
            raise Exception('Updating Redmine log issue failed')

    def parseLog(self, log):
        log = log.strip()[1:].split('\n#')
        severity = [(i[0:i.find(':')]).strip() for i in log] # from 1 to :
        server = [(i[(i.find('[') + 1):i.find(']')]).strip() if i.find(']') > 0 else '' for i in log] # from [ to ]
        message = [(i[(i.find(']') + 1):(i.find('{') if i.find('{') > 0 else None)]).strip() for i in log] # from ] to {
        data = [(i[(i.find('{') - 1):]).strip() if i.find('{') > 0 else '' for i in log] # after {
        return list(zip(severity, server, message, data))

    def parseRedmineDescription(self, desc):
        desc = ('\n' + desc.strip()).split('\n|')[2:]
        desc = [[j.strip() for j in (i.strip()[0:-1]).split('|')] for i in desc]
        return desc

    def createRecord(self, data) -> IRecord:
        reqData = {'issue': {
            'subject': 'Automatically created service issue for %s@%s' % (data['name'], data['server']),
            'tracker_id': self.defaultTrackerId,
            'project_id': self.defaultProjectId,
            'status': self.defaultStatus,
            'priority': self.defaultPrority,
            'custom_fields': [
                {'id': self.customFields['server']['id'], 'value': data['server']}
            ]
        }}
        resp = self._send('post', self.baseUrl + '/issues.json', json=reqData)
        if resp is None or resp.status_code != 201:
            raise RecordCreationFailed(reqData, resp)

        respData = resp.json()['issue']
        url = '%s/issues/%s.json' % (self.baseUrl, str(respData['id']))
        record = RedmineRecord(url, self, respData)
        record.update(data)
        
        return record

    def findRecord(self, data) -> IRecord:
        url = '%s/issues/%s.json' % (self.baseUrl, str(data['id']))
        resp = self._send('get', url)
        if resp is None or resp.status_code == 404:
            raise RecordNotFound()
        if resp.status_code != 200:
            raise RecordNotFound(str(resp.status_code) + ' ' + resp.text + ' (ID ' + str(id) + ')')
        return RedmineRecord(url, self, resp.json()['issue'])

    def setupNotifications(self, on):
        resp = self._send('get', self.baseUrl + '/login')
        if resp is None or resp.status_code != 200:
            logging.error('[Redmine] Unable to load login page for notification setup')
            return

        loginForm = resp.text.replace('\n', '')
        authToken = re.sub('.*input type="hidden" name="authenticity_token" value="([^"]*)".*', '\\1', loginForm)
        if not self.username or not self.password:
            raise Exception(
                'Redmine username and password are required for notification setup. API key authentication is used for API calls, but login/notification setup still requires username/password.'
            )
        if authToken != loginForm:
            resp = self._send(
                'post',
                self.baseUrl + '/login',
                cookies=resp.cookies,
                data={'authenticity_token': authToken, 'username': self.username, 'password': self.password},
            )
            if resp is None or resp.status_code != 200:
                logging.error('[Redmine] Login failed during notification setup')
                return

        resp = self._send('get', self.baseUrl + '/settings?tab=notifications', cookies=resp.cookies)
        if resp is None or resp.status_code != 200:
            logging.error('[Redmine] Unable to load notification settings page')
            return

        form = re.sub('</form>.*', '', re.sub('^.*<form action="/settings/edit[?]tab=notifications"[^>]*>', '', resp.text.replace('\n', '')))

        issueUpdateRe = '<input type="checkbox" name="settings\\[notified_events\\]\\[\\]" value="issue_updated"[^/]*checked="checked"[^/]*/>'
        if not on:
            form = re.sub(issueUpdateRe, '', form)
        elif re.search(issueUpdateRe, form) is None:
            form += '<input type="checkbox" name="settings[notified_events][]" value="issue_updated" checked="checked" />'

        chbs = form.split('<input type="checkbox"')[1:]
        chbs = ['checked="checked"' in i for i in chbs]
        form = re.split('<input|<textarea', form)[1:]
        formFields = [re.sub('^.*name="([^"]*)".*$', '\\1', i) for i in form]
        formValues = [re.sub('^.*>([^<]*)</textarea>.*$', '\\1', i) if re.search('</textarea>', i) else re.sub('^.*value="([^"]*)".*$', '\\1', i) for i in form]

        data = ''
        nChb = -1
        for i in range(len(formValues)):
            if re.search('type="checkbox"', form[i]):
                nChb += 1
                if not chbs[nChb]:
                    continue
            data += urllib.parse.quote(formFields[i], safe='') + '=' + urllib.parse.quote(formValues[i], safe='') + '&'
        resp = self._send(
            'post',
            self.baseUrl + '/settings/edit?tab=notifications',
            cookies=resp.cookies,
            data=data,
        )
        if resp is None or resp.status_code != 200:
            logging.error(f'setting up Redmine notifications failed with {resp.status_code if resp else "no response"}')

class RedmineRecord(IRecord):

    expectedTrackerName = 'Service'
    mapping = {
        'backendConnection': 'backend_connection', 
        'name':              'container_name', 
        'project':           'project_name',
        'users':             'ssh_users',
        'techStack':         'tech_stack'
    }

    url = None
    id = None
    data = None
    redmine = None

    def __init__(self, url, redmine, data=None):
        self.url = url
        self.id = int(re.sub('^.*/([0-9]+)([.]json)?$', '\\1', url))
        self.redmine = redmine
        self.data = data
        
        if data is not None and 'tracker' in data and data['tracker']['name'] != RedmineRecord.expectedTrackerName:
            raise RecordError('Redmine issue %d has a wrong tracker %s' % (self.id, data['tracker']['name']))

    def update(self, newData):
        # same Redmine issue can't be updated with different services within the same day
        #   (as this indicates many services might use same Redmine issue)
        if self.data is None:
            resp = self.redmine.session.get(self.url)
            self.data = resp.json()['issue']
        lastUpdate = [i['value'] for i in self.data['custom_fields'] if i['name'] == 'qos_update_date']
        if len(lastUpdate) > 0 and lastUpdate[0] == str(datetime.date.today()) and 'server' in newData and 'name' in newData:
            curServer = self.getCustomField(self.data, 'server') or ''
            curName = self.getCustomField(self.data, 'name') or ''
            if curServer + '@' + curName != newData['server'] + '@' + newData['name']:
                raise RecordDuplicated(self.id, newData, {'name': curName, 'server': curServer})
        
        # prepare request data
        relations = []
        reqData = {'custom_fields': []}
        newData['qos_update_date'] = str(datetime.date.today())
        
        if 'inContainerApps' in newData and newData['inContainerApps'] is not None:
            try: 
                for inId, inCfg in newData['inContainerApps'].items():
                    try:
                        app = self.redmine.findRecord({'id': inId})
                        relations.append({'id': inId, 'type': 'relates'})
                        app.update({'id': inId, 'Service categories': [self.redmine.inContainerAppCategory]})
                    except RecordNotFound:
                        logging.error('[%s] Redmine issue %d inContainerApps refers to a non-existing Redmine issue %s' % (newData['server'], self.id, str(inId)))
                del newData['inContainerApps']
            except AttributeError:
                logging.error('[%s] Incorrect inContainerApps in %s' % (newData['server'], json.dumps(newData)))
        
        for name, value in newData.items():
            if value is not None:
                key = RedmineRecord.mapping[name] if name in RedmineRecord.mapping else name
                if key in self.redmine.customFields:
                    reqData['custom_fields'].append({'id': self.redmine.customFields[key]['id'], 'value': value})
                else:
                    reqData[key] = value
 
        resp = self.redmine.session.put(self.url, json={'issue': reqData})
        if resp.status_code != 200 and resp.status_code != 204:
            logging.debug(json.dumps({'issue': reqData}))
            raise RecordError('Redmine issue %d update failed with code %d and response "%s"' % (int(self.id), resp.status_code, resp.text))
        
        if 'envType' in newData:
            envType = newData['envType'].lower()
            if envType in self.redmine.envTypes:
                relations.append({'id': self.redmine.envTypes[envType], 'type': 'relates'})
            else:
                logging.error('[%s] Redmine issue %d has unknown environment type %s' % (newData['server'], self.id, envType))

        for i in relations:
            resp = self.redmine.session.post(self.url.replace('.json', '/relations.json'), json={'relation': {'issue_to_id': i['id'], 'relation_type': i['type']}})
            if resp.status_code == 422 and 'Related issue has already been taken' != resp.json()['errors'][0]:
                logging.error('[%s] Redmine issue %d->%d relation creation failed with message "%s"' % (newData['server'], int(self.id), int(i['id']), resp.json()['errors'][0]))

    def getCustomField(self, data, field):
        if field in RedmineRecord.mapping:
           field = RedmineRecord.mapping[field]
        value = [i['value'] for i in data['custom_fields'] if i['name'] == field]
        return value[0] if len(value) > 0 else None


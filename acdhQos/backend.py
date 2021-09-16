import datetime
import json
import logging
import re
import requests
import urllib

from acdhQos.interface import *


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

    def __init__(self, baseUrl, auth, logIssueId=None, defTrackerId=7, defProjectId=164, defStatus=1, defPrority=2, inContainerAppCategory=52):
        self.baseUrl = baseUrl
        self.session = requests.Session()
        self.session.auth = auth
        self.logIssueId = logIssueId
        self.defaultTrackerId = defTrackerId
        self.defaultProjectId = defProjectId
        self.defaultStatus = defStatus
        self.defaultPrority = defPrority
        self.inContainerAppCategory = inContainerAppCategory
        
        # custom fields
        self.customFields = {}
        resp = self.session.get(self.baseUrl + '/custom_fields.json')
        data = resp.json()
        for i in data['custom_fields']:
            self.customFields[i['name']] = i

        # environment types
        self.envTypes = {}
        resp = self.session.get(self.baseUrl + '/issues.json', data={'cf_' + str(self.customFields['tags']['id']): 'environment type', 'status_id': '*', 'limit': 100})
        data = resp.json()
        for i in data['issues']:
            self.envTypes[i['subject'].lower().split(' ')[0]] = i['id']

    def begin(self):
        self.setupNotifications(False)
        
    def end(self, log, procServers):
        self.setupNotifications(True)
        if self.logIssueId is not None:
            self.saveLog(log, procServers)

    def saveLog(self, log, procServers):
        # get the current log and split it into entries - we must combine it with the new one
        url = '%s/issues/%s.json' % (self.baseUrl, str(self.logIssueId))
        resp = self.session.get(url)
        if resp.status_code != 200:
            raise Exception('Fetching Redmine log issue failed')
        desc = self.parseRedmineDescription(resp.json()['issue']['description'])
        log = self.parseLog(log)
        # now every desc and log element is an array of [severity, server, message, data]

        # combine logs by keeping all lines from the old ones which do not apply to
        # the servers processed in the new log and adding a complete new log to it
        desc = [i for i in desc if len(i) < 2 or (i[1] not in procServers and i[1] != '')]
        desc += log
        desc = ['|' + '|'.join(i) + '|' if len(i) == 4 else '' for i in desc]
        desc = list(set(desc)) # to avoid duplication of lines without the server
        desc.sort()

        # update the redmine issue
        desc = '|Severity|Server|Message|Container Description|\n' + '\n'.join(desc)
        data = {'issue': {
            'description': desc,
            'due_date': str(datetime.date.today())
        }}
        resp = self.session.put(url, json=data)
        if resp.status_code != 200 and resp.status_code != 204:
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
        resp = self.session.post(self.baseUrl + '/issues.json', json=reqData)
        if resp.status_code != 201:
            raise RecordCreationFailed(reqData, resp)
        
        respData = resp.json()['issue']
        url = '%s/issues/%s.json' % (self.baseUrl, str(respData['id']))
        record = RedmineRecord(url, self, respData)
        record.update(data)
        
        return record

    def findRecord(self, data) -> IRecord:
        url = '%s/issues/%s.json' % (self.baseUrl, str(data['id']))
        resp = self.session.get(url)
        if resp.status_code == 404:
            raise RecordNotFound()
        if resp.status_code != 200:
            raise RecordNotFound(str(resp.status_code) + ' ' + resp.text + ' (ID ' + str(id) + ')')
        return RedmineRecord(url, self, resp.json()['issue'])

    def setupNotifications(self, on):
        resp = self.session.get(self.baseUrl + '/login')
        authToken = re.sub('.*input type="hidden" name="authenticity_token" value="([^"]*)".*', '\\1', resp.text.replace('\n', ''))
        resp = self.session.post(self.baseUrl + '/login', cookies=resp.cookies, data={'authenticity_token': authToken, 'username': self.session.auth[0], 'password': self.session.auth[1]})

        resp = self.session.get(self.baseUrl + '/settings?tab=notifications', cookies=resp.cookies)
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
        resp = self.session.post('https://redmine.acdh.oeaw.ac.at/settings/edit?tab=notifications', cookies=resp.cookies, data=data)
        if resp.status_code != 200:
            raise Exception('setting up Redmine notifications failed')

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


import json
import logging
import re
import requests
import urllib.parse


class Redmine:
    customFields = None
    envTypes = None
    defaultTrackerId = 7
    defaultProjectId = 164
    defaultStatus = 1
    baseUrl = None
    auth = None

    def __init__(self, baseUrl, auth):
        self.baseUrl = baseUrl
        self.auth = auth

        # custom fields
        self.customFields = {}
        resp = requests.get(self.baseUrl + '/custom_fields.json', auth=self.auth)
        data = resp.json()
        for i in data['custom_fields']:
            self.customFields[i['name']] = i

        # environment types
        self.envTypes = {}
        resp = requests.get(self.baseUrl + '/issues.json', data={'cf_' + str(self.customFields['tags']['id']): 'environment type', 'status_id': '*', 'limit': 100}, auth=self.auth)
        data = resp.json()
        for i in data['issues']:
            self.envTypes[i['subject'].lower().split(' ')[0]] = i['id']

    def setupNotifications(self, on):
        resp = requests.get(self.baseUrl + '/login')
        authToken = re.sub('.*input type="hidden" name="authenticity_token" value="([^"]*)".*', '\\1', resp.text.replace('\n', ''))
        resp = requests.post(self.baseUrl + '/login', cookies=resp.cookies, data={'authenticity_token': authToken, 'username': self.auth[0], 'password': self.auth[1]})

        resp = requests.get(self.baseUrl + '/settings?tab=notifications', cookies=resp.cookies)
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
        resp = requests.post('https://redmine.acdh.oeaw.ac.at/settings/edit?tab=notifications', cookies=resp.cookies, data=data)
        if resp.status_code != 200:
            raise Exception('setting up Redmine notifications failed')

    def createService(self, **kwargs):
        data = dict(kwargs)
        data = self.addCustomFields(data)
        if 'tracker_id' not in data and self.defaultTrackerId is not None:
            data['tracker_id'] = self.defaultTrackerId
        if 'project_id' not in data and self.defaultProjectId is not None:
            data['project_id'] = self.defaultProjectId
        if 'status' not in data and self.defaultStatus is not None:
            data['status'] = self.defaultStatus

        resp = requests.post(self.baseUrl + '/issues.json', json={'issue': data}, auth=self.auth)
        if resp.status_code != 201:
            logging.debug(json.dumps({'issue': data}))
            raise Exception('Redmine issue creation failed with code %d and response %s' % (resp.status_code, resp.text))
        return resp.json()['issue']

    def getService(self, id):
        resp = requests.get('%s/issues/%s.json' % (self.baseUrl, str(id)), auth=self.auth)
        if resp.status_code == 404:
            raise LookupError()
        if resp.status_code != 200:
            raise Exception(str(resp.status_code) + ' ' + resp.text + ' (ID ' + str(id) + ')')
        return resp.json()['issue']

    def updateService(self, id, **kwargs):
        data = {}
        for name, value in dict(kwargs).items():
            if value is not None: 
                data[name] = value
        data = self.addCustomFields(data)
        resp = requests.put('%s/issues/%d.json' % (self.baseUrl, id), json={'issue': data}, auth=self.auth)
        if resp.status_code != 200:
            logging.debug(json.dumps({'issue': data}))
            raise Exception('Redmine issue update failed with code %d and response %s' % (resp.status_code, resp.text))
        
        if 'envType' in data:
            envType = data['envType'].lower()
            if envType in self.envTypes:
                resp = requests.post('%s/issues/%d/relations.json' % (self.baseUrl, id), json={'relation': {'issue_to_id': self.envTypes[envType], 'relation_type': 'relates'}}, auth=self.auth)
            else:
                logging.error('  Unknown environment type ' + envType)

        if 'relations' in data:
            for i in data['relations']:
                resp = requests.post('%s/issues/%d/relations.json' % (self.baseUrl, id), json={'relation': {'issue_to_id': int(i['id']), 'relation_type': i['type']}}, auth=self.auth)

    def addCustomFields(self, data):
        customFields = []
        for name, value in data.items():
            if name in self.customFields and value is not None:
                customFields.append({'id': self.customFields[name]['id'], 'value': value})
        data['custom_fields'] = customFields
        return data


import json
import logging
import os
import re
import requests
import traceback

class Rancher:

    def maintainRedmine(self, redmine, server, apiBase, user, pswd):
        auth = requests.auth.HTTPBasicAuth(user, pswd)
        resp = requests.get(apiBase + '/projects', auth=auth)
        if resp.status_code == 200:
            for project in resp.json()['data']:
                pId = project['id']
                print(project['name'])

                resp = requests.get(apiBase + '/project/' + pId + '/workloads', auth=auth)
                for workload in resp.json()['data']:
                    print('\t' + workload['name'])

                    for container in workload['containers']:
                        print('\t\t' + container['image'])

                    #print(workload)
                    for endpoint in workload['publicEndpoints'] if 'publicEndpoints' in workload else []:
                        print('\t\t' + endpoint['protocol'].lower() + '://' + (endpoint['hostname'] if 'hostname' in endpoint else ', '.join(endpoint['addresses'])))


                resp = requests.get(apiBase + '/project/' + pId + '/projectRoleTemplateBindings', auth=auth)
                for user in resp.json()['data']:
                    username = re.sub('.*CN=([^,]*),OU=.*', '\\1', user['userPrincipalId'].replace('\\,', ''))
                    print('\t\t' + username + ' (' + user['userId'] + '): ' + user['roleTemplateId'])


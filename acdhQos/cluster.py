import docker
import json
import logging
import os
import re
import requests
import traceback
import yaml

from acdhQos.interface import *

class Rancher(ICluster):

    server = None
    apiBase = None
    project = None
    skipProjects = None
    session = None

    def __init__(self, server, apiBase, user, pswd, project=None, skipProjects=None):
        self.server = server
        self.apiBase = apiBase
        self.project = project
        self.skipProjects = [] if skipProjects is None else skipProjects
        
        if self.server is None:
            self.server = re.sub('^.*[/.]', '', re.sub('([.]arz|[.]acdh|[.]acdh-dev)?[.]oeaw[.].*$', '', self.server))
        
        self.session = requests.Session()
        self.session.auth = (user, pswd)
        
    def harvest(self):
        data = []
        resp = self.session.get(self.apiBase + '/projects')
        for project in resp.json()['data']:
            if (self.project is not None and project['name'] != self.project) or project['name'] in self.skipProjects:
                continue
            try:
                logging.info('[%s] Processing project %s' % (self.server, project['name']))
                resp = self.session.get(self.apiBase + '/project/' + project['id'] + '/workloads')
                for workload in resp.json()['data']:
                    logging.info('[%s] Processing workload %s' % (self.server, workload['name']))
                    data.append(self.processWorkload(workload, project))
            except Exception:
                logging.error('[%s] %s' % (self.server, traceback.format_exc()))
        return data

    def processWorkload(self, cfg, pcfg):
        name = cfg['name']

        redmineId = self.getLabel(cfg, 'ID')

        images = [i['image'] for i in cfg['containers']]
        images = '\n'.join(set(images))

        endpoint = []
        for i in cfg['publicEndpoints'] if 'publicEndpoints' in cfg and cfg['publicEndpoints'] is not None else []:
            endpoint.append(i['protocol'].lower() + '://' + (i['hostname'] if 'hostname' in i else ', '.join(i['addresses'])))
        endpoint = '\n'.join(set(endpoint))

        techStack = '\n'.join([i['image'] for i in cfg['containers']])

        inContainerApps = None #TODO

        backendConnection = None #TODO

        users = []
        resp = self.session.get(self.apiBase + '/project/' + pcfg['id'] + '/projectRoleTemplateBindings')
        for user in resp.json()['data']:
            username = re.sub('.*CN=([^,]*),OU=.*', '\\1', user['userPrincipalId'].replace('\\,', ''))
            users.append(username + ' (' + user['userId'] + '): ' + user['roleTemplateId'])
        users = '\n'.join(set(users))

        return {'name': name, 'id': redmineId, 'endpoint': endpoint, 'techStack': techStack, 'inContainerApps': inContainerApps, 'backendConnection': backendConnection, 'users': users, 'server': self.server, 'project': pcfg['name']}

    def getLabel(self, cfg, name):
        if 'labels' not in cfg or name not in cfg['labels']:
            return None
        return cfg['labels'][name]

class Portainer(ICluster):

    server = None
    apiBase = None
    session = None
    users = None
    teams = None
    projectsPath = None
    stack = None

    def __init__(self, server, apiBase, user, pswd, projectsPath, stack=None):
        self.server = server
        self.apiBase = apiBase
        self.projectsPath = projectsPath
        self.stack = stack

        if self.server is None:
            self.server = re.sub('^.*[/.]', '', re.sub('([.]arz|[.]acdh|[.]acdh-dev)?[.]oeaw[.].*$', '', self.server))

        resp = requests.post(apiBase + '/auth', data=json.dumps({'Username': user, 'Password': pswd}))
        self.session = requests.Session()
        self.session.headers.update({'Authorization': 'Bearer ' + resp.json()['jwt']})

        resp = self.session.get(apiBase + '/roles')
        roles = {}
        for role in resp.json():
            roles[str(role['Id'])] = role['Name']

        resp = self.session.get(apiBase + '/users')
        self.users = [{'Id': i['Id'], 'Name': i['Username'], 'Role': roles[str(i['Role'])]} for i in resp.json()]
        self.users = dict(zip([str(i['Id']) for i in self.users], self.users))

        self.teams = {}
        resp = self.session.get(apiBase + '/teams')
        for team in resp.json():
            resp = self.session.get(apiBase + '/teams/' + str(team['Id']) + '/memberships')
            self.teams[str(team['Id'])] = [self.users[str(i['UserID'])] for i in resp.json()]

    def harvest(self):
        data = []
        resp = self.session.get(self.apiBase + '/stacks')
        for stack in resp.json():
            if self.stack is not None and stack['Name'] != self.stack:
                continue
            try:
                logging.info('[%s] Processing stack %s' % (self.server, str(stack['Id'])))
                users = self.getUsers(stack)

                resp = self.session.get(self.apiBase + '/stacks/' + str(stack['Id']) + '/file')
                cfg = yaml.safe_load(resp.json()['StackFileContent'])
                for name, ccfg in cfg['services'].items():
                    logging.info('[%s] Processing container %s' % (self.server, stack['Name'] + '-' + name))
                    data.append(self.processContainer(name, ccfg, stack))
            except Exception:
                logging.error('[%s] %s' % (self.server, traceback.format_exc()))
        return data

    def processContainer(self, name, ccfg, scfg):
        name = scfg['Name'] + '-' + name

        ccfg['labels'] = self.parseLabels(ccfg)

        redmineId = self.getLabel(ccfg, 'ID')
        if redmineId is None:
            redmineId = self.getLabel(ccfg, 'redmineId')
            if redmineId is not None:
                logging.warning('[%s] container %s-%s uses non-standard label for the redmine issue id' % (self.server, scfg['Name'], name))

        endpoint = self.getEndpoint(ccfg)

        if 'image' in ccfg:
            techStack = ccfg['image']
        elif isinstance(ccfg['build'], str):
            techStack = ' '.join(self.inspectLocalDockerfile(scfg['ProjectPath'], ccfg['build']))
        else:
            techStack = ' '.join(self.inspectLocalDockerfile(scfg['ProjectPath'], ccfg['build']['context']))

        inContainerApps = self.getLabel(ccfg, 'InContainerApps')
        if inContainerApps is None:
            inContainerApps = self.getLabel(ccfg, 'inContainerApps')
            if inContainerApps is not None:
                logging.warning('[%s] container %s-%s uses non-standard label for the InContainerApps' % (self.server, scfg['Name'], name))
        
        backendConnection = self.getLabel(ccfg, 'BackendConnection')
        if backendConnection is None:
            backendConnection = self.getLabel(ccfg, 'backendConnection')
            if backendConnection is not None:
                logging.warning('[%s] container %s-%s uses non-standard label for the BackendConnection' % (self.server, scfg['Name'], name))

        users = '\n'.join([i['Name'] for i in self.getUsers(scfg)])

        return {'name': name, 'id': redmineId, 'endpoint': endpoint, 'techStack': techStack, 'inContainerApps': inContainerApps, 'backendConnection': backendConnection, 'users': users, 'pid': scfg['Id'], 'server': self.server, 'project': scfg['Name']}

    def inspectLocalDockerfile(self, path, context):
        dockerfile = os.path.join(self.projectsPath, re.sub('^/', '', path), context, 'Dockerfile')
        if os.path.exists(dockerfile):
            with open(dockerfile) as f:
                for i in f:
                    i = i.strip()
                    if i.upper().replace('\t', ' ').startswith('FROM '):
                        return [dockerfile, i[4:].strip()]
        return [dockerfile]

    def getUsers(self, stack):
        if 'ResourceControl' not in stack:
            return []
        users = {}
        for i in stack['ResourceControl']['UserAccesses']:
            users[str(i['UserId'])] = self.users[str(i['UserId'])]
        for j in stack['ResourceControl']['TeamAccesses']:
            for i in self.teams[str(j['TeamId'])]:
                users[str(i['Id'])] = self.users[str(i['Id'])]
        return users.values()

    def getEndpoint(self, cfg):
        endpoint = None
        if 'labels' in cfg and 'traefik.frontend.rule' in cfg['labels']:
            endpoint = cfg['labels']['traefik.frontend.rule']
            endpoint = re.sub('^[^:]*:', '', endpoint)
        return endpoint

    def getLabel(self, cfg, lbl):
        if lbl in cfg['labels']:
            return cfg['labels'][lbl]
        if lbl.lower() in cfg['labels']:
            return cfg['labels'][lbl.lower()]
        return None
        
    def parseLabels(self, cfg):
        if 'labels' not in cfg:
            return {}
        labels = {}
        for i in cfg['labels']:
            p = i.index('=')
            labels[i[0:p]] = i[(p + 1):]
        return labels

class DockerTools(ICluster):

    server = None
    accounts = None

    def __init__(self, server, account=None):
        self.server = server

        if account is not None:
            self.accounts = [account]
        else:
            self.accounts = os.listdir('/home')

    def harvest(self):
        client = docker.from_env();
        data = []
        for account in self.accounts:
            cfgFile = os.path.join('/home', account, 'config.json')
            if os.path.isfile(cfgFile):
                try:
                    with open(cfgFile, 'r') as f:
                        cfg = json.load(f)
                    for c in cfg:
                        try:
                            logging.info('[%s] Processing container %s-%s' % (self.server, account, c['Name']))
                            data.append(self.processContainer(client, c, account))
                        except docker.errors.NotFound:
                            logging.error("[%s] Container %s-%s is defined in config.json but doesn't exist" % (self.server, account, c['Name']))
                        except Exception as e:
                            logging.error('[%s] %s' % (self.server, traceback.format_exc()))
                except:
                    logging.error('[%s] Can not parse %s: %s' % (self.server, cfgFile, str(e)))
        return data

    def processContainer(self, client, cfg, account):
        id = cfg['ID'] if 'ID' in cfg else None
        if id == '':
            id = None

        name = account + '-' + cfg['Name']

        protocols = ['https']
        if 'HTTPS' in cfg:
            if str(cfg['HTTPS']).lower() == 'false':
                protocols = ['http']
            if str(cfg['HTTPS']) == 'both':
                protocols = ['http', 'https']
        endpoint = ''
        if 'ServerName' in cfg:
            endpoint += '\n'.join([p + '://' + cfg['ServerName'] for p in protocols])
        if 'ServerAlias' in cfg:
            for i in self.asList(cfg['ServerAlias']):
                endpoint += '\n' + '\n'.join([p + '://' + i for p in protocols])
        endpoint = endpoint.strip()

        techStack = []
        for i in client.containers.get(name).image.history():
            if i['Tags'] is not None:
                techStack += i['Tags']
        techStack = ' '.join(techStack)

        inContainerApps = cfg['InContainerApps'] if 'InContainerApps' in cfg else None

        backendConnection = None
        if 'BackendConnection' in cfg:
            backendConnection = '\n'.join(self.asList(cfg['BackendConnection']))

        users = ''
        keysFile = os.path.join('/home', account, '.ssh/authorized_keys')
        if os.path.exists(keysFile):
            with open(keysFile) as f:
                for l in f.readlines():
                    l = l.split(' ')
                    if len(l) > 2:
                        users += (l[2].strip() + '\n')
        users = users.strip()

        return {'name': name, 'id': id, 'endpoint': endpoint, 'techStack': techStack, 'inContainerApps': inContainerApps, 'backendConnection': backendConnection, 'users': users, 'server': self.server, 'project': account}

    def updateConfigWithId(self, cfgFile, name, id):
        with open(cfgFile, 'r') as f:
            cfg = json.load(f)
        update = False
        for i in cfg:
            if i['Name'] == name:
                if 'ID' not in i or i['ID'] != id:
                    i['ID'] = id
                    update = True
                    break
        if update:
            with open(cfgFile, 'w') as f:
                cfg = json.dump(cfg, f, indent=2)
        return update

    @staticmethod
    def asList(arg):
        if arg is None:
            arg = []
        elif not isinstance(arg, list):
            arg = [arg]
        return arg


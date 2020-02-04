import datetime
import docker
import json
import logging
import os


class Container:
    idList = []
    expectedTrackerName = 'Service'

    cfg = None
    server = None
    account = None
    containerName = None

    def __init__(self, cfg, server, account):
        self.cfg = cfg
        self.server = server
        self.account = account
        self.containerName = account + '-' + self.cfg['Name']

    def maintainRedmine(self, redmine, create, cfgFile):
        client = docker.from_env();
        relations = []

        if 'ID' in self.cfg and self.cfg['ID'] in Container.idList:
            logging.error('Redmine ID %s used many times' % str(self.cfg['ID']))
            relations.append({'id': self.cfg['ID'], 'type': 'relates'})
            self.cfg['ID'] = None
        if 'ID' in self.cfg and self.cfg['ID'] is not None:
            try:
                data = redmine.getService(int(self.cfg['ID']))
            except LookupError:
                self.cfg['ID'] = None
        if 'ID' not in self.cfg or self.cfg['ID'] is None:
            if create:
                subject = 'Automatically created service issue for %s-%s@%s' % (self.account, self.cfg['Name'], self.server)
                data = redmine.createService(subject=subject, server=self.server)
                self.cfg['ID'] = int(data['id'])
                self.maintainConfig(cfgFile) # the only situation when the config.json should be updated
            else:
                raise LookupError('No Redmine ID')
        if data['tracker']['name'] != Container.expectedTrackerName:
            logging.error('Redmine issue %d has a wrong tracker %s' % (int(self.cfg['ID']), data['tracker']['name']))
        Container.idList.append(int(self.cfg['ID']))

        protocols = ['https']
        if 'HTTPS' in self.cfg:
            if str(self.cfg['HTTPS']).lower() == 'false':
                protocols = ['http']
            if str(self.cfg['HTTPS']) == 'both':
                protocols = ['http', 'https']
        endpoint = ''
        if 'ServerName' in self.cfg:
            endpoint += '\n'.join([p + '://' + self.cfg['ServerName'] for p in protocols])
        if 'ServerAlias' in self.cfg:
            for i in self.asList(self.cfg['ServerAlias']):
                endpoint += '\n' + '\n'.join([p + '://' + i for p in protocols])
        endpoint = endpoint.strip()

        techStack = []
        try:
            for i in client.containers.get(self.containerName).image.history():
                if i['Tags'] is not None:
                    techStack += i['Tags']
        except Exception as e:
            logging.error(str(e))
        techStack = ' '.join(techStack)

        backendConnection = None
        if 'BackendConnection' in self.cfg:
            backendConnection = '\n'.join(self.asList(self.cfg['BackendConnection']))

        sshUsers = ''
        keysFile = os.path.join('/home', self.account, '.ssh/authorized_keys')
        if os.path.exists(keysFile):
            with open(keysFile) as f:
                l = f.readline().split(' ')
                if len(l) > 2:
                    sshUsers += l[2].strip() + '\n'
        sshUsers = sshUsers.strip()

        redmine.updateService(
            int(self.cfg['ID']), 
            backend_connection=backendConnection, 
            container_name=self.cfg['Name'], 
            endpoint=endpoint, 
            envType=self.cfg['Type'], 
            project_name=self.account,
            qos_update_date=str(datetime.date.today()),
            relations=relations,
            server=self.server, 
            ssh_users=sshUsers,
            tech_stack=techStack
        )

    def maintainConfig(self, cfgFile):
        with open(cfgFile, 'r') as f:
            cfg = json.load(f)
        for i in cfg:
            if i['Name'] == self.cfg['Name']:
                if 'ID' not in i or i['ID'] != self.cfg['ID']:
                    i['ID'] = self.cfg['ID']
        with open(cfgFile, 'w') as f:
            cfg = json.dump(cfg, f, indent=2)

    @staticmethod
    def asList(arg):
        if arg is None:
            arg = []
        elif not isinstance(arg, list):
            arg = [arg]
        return arg

    @staticmethod
    def factory(cfgFile, n=0, server='', account=''):
        with open(cfgFile, 'r') as f:
            return Container(json.load(f)[n], server, account)

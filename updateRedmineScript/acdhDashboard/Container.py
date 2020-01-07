import docker
import json
import logging


class Container:
    idList = []

    cfg = None
    server = None
    account = None
    containerName = None

    def __init__(self, cfg, server, account):
        self.cfg = cfg
        self.server = server
        self.account = account
        self.containerName = account + '-' + self.cfg['Name']

    def maintainRedmine(self, redmine, create):
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
            else:
                raise LookupError('No Redmine ID')
        self.cfg['ID'] = data['id']
        Container.idList.append(data['id'])

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
        for i in client.containers.get(self.containerName).image.history():
            if i['Tags'] is not None:
                techStack += i['Tags']
        techStack = ' '.join(techStack)

        redmine.updateService(self.cfg['ID'], server=self.server, endpoint=endpoint, envType=self.cfg['Type'], tech_stack=techStack, relations=relations)

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

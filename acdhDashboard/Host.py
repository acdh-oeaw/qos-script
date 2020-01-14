import json
import logging
import os

from acdhDashboard.Container import Container


class Host:

    redmine = None

    def maintainRedmine(self, redmine, server):
        for account in os.listdir('/home'):
            cfgFile = os.path.join('/home', account, 'config.json')
            if os.path.isfile(cfgFile):
                try:
                    with open(cfgFile, 'r') as f:
                        cfg = json.load(f)
                    for c in cfg:
                        try:
                            logging.info('Processing container %s-%s' % (account, c['Name']))
                            cntnr = Container(c, server, account)
                            cntnr.maintainRedmine(redmine, True)
                            cntnr.maintainConfig(cfgFile)
                        except Exception as e:
                            logging.error(str(e))
                except:
                    logging.error('Can not parse ' + cfgFile)


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

    apiBase = None
    project = None
    skipProjects = None
    skipClusters = None
    skipTypes = None
    session = None
    clusters = None

    def __init__(self, apiBase, token, project=None, skipProjects=None, skipClusters=None, skipTypes=None):
        self.apiBase = apiBase
        self.project = project
        self.skipProjects = skipProjects or []
        self.skipClusters = skipClusters or []
        self.skipTypes = skipTypes or []
        
        self.session = requests.Session()
        self.session.headers = {'Authorization': 'Bearer ' + token}

        resp = self.session.get(self.apiBase + '/clusters')
        resp.raise_for_status()  # Ensure the request was successful

        clusters = resp.json().get('data', [])
        if self.skipClusters:
            clusters = [cluster for cluster in clusters if cluster['id'] not in self.skipClusters]
        self.clusters = {x['id']: x['name'] for x in clusters}
    
    def getClusters(self):
        return self.clusters.values()

    def harvest(self):
        data = []
        try:
            resp = self.session.get(self.apiBase + '/projects')
            projects = resp.json().get('data', [])
            logging.info(f"Found {len(projects)} projects")

            for project in projects:
                logging.info(f"Checking project {project['name']}")
                if (self.project is not None and project['name'] != self.project) or project['name'] in self.skipProjects:
                    logging.info(f"Skipping project {project['name']} due to project filter")
                    continue
                try:
                    logging.info(f"Processing project {project['name']}")
                    resp = self.session.get(self.apiBase + '/project/' + project['id'] + '/workloads')
                    workloads = resp.json().get('data', [])
                    logging.info(f"Found {len(workloads)} workloads in project {project['name']}")
                    print(f"Workloads: {workloads}")

                    # Fetch ingresses for the project
                    ingresses_resp = self.session.get(self.apiBase + '/project/' + project['id'] + '/ingresses')
                    ingresses = ingresses_resp.json().get('data', [])
                    logging.info(f"Found {len(ingresses)} ingresses in project {project['name']}")
                    print(f"Ingresses: {ingresses}")

                    for workload in workloads:
                        if workload['type'] in self.skipTypes:
                            logging.info(f"Skipping workload {workload['name']} due to type filter")
                            continue

                        # Check if the workload has an associated ingress
                        has_ingress = any(
                            workload['name'] in ingress['name'] for ingress in ingresses
                        )
                        print(f"Workload {workload['name']} has ingress: {has_ingress}")

                        if has_ingress:
                            logging.info(f"Processing workload {workload['name']}")
                            data.append(self.processWorkload(workload, project))
                        else:
                            logging.info(f"Skipping workload {workload['name']} (no ingress)")
                except Exception as e:
                    logging.error(f"Error processing project {project['name']}: {traceback.format_exc()}")
                    print(f"Error processing project {project['name']}: {e}")
        except Exception as e:
            logging.error(f"Failed to fetch projects: {traceback.format_exc()}")
            print(f"Error fetching projects: {e}")
        return data if data else []

    def processWorkload(self, cfg, pcfg):
        name = cfg['name']
        type = cfg['type']
        server = self.clusters[pcfg['clusterId']]

        redmineId = self.getLabel(cfg, 'ID')

        images = [i['image'] for i in cfg['containers']]
        images = '\n'.join(set(images))

        endpoint = []
        for i in cfg['publicEndpoints'] if 'publicEndpoints' in cfg and cfg['publicEndpoints'] is not None else []:
            if 'addresses' not in i and 'hostname' not in i:
                continue
            endpoint.append(i['protocol'].lower() + '://' + (i['hostname'] if 'hostname' in i else ', '.join(i['addresses'])))
        endpoint = '\n'.join(set(endpoint))

        techStack = '\n'.join([i['image'] for i in cfg['containers']])

        inContainerApps = self.getAnnotation(cfg, 'InContainerApps')

        backendConnection = self.getAnnotation(cfg, 'BackendConnection')

        users = []
        resp = self.session.get(self.apiBase + '/project/' + pcfg['id'] + '/projectRoleTemplateBindings')
        for user in resp.json()['data']:
            if user.get('userPrincipalId') is not None:
                username = re.sub('.*CN=([^,]*),OU=.*', '\\1', user['userPrincipalId'].replace('\\,', ''))
                users.append(username + ' (' + user['userId'] + '): ' + user['roleTemplateId'])
        users = '\n'.join(set(users))

        return {'name': name, 'id': redmineId, 'endpoint': endpoint, 'techStack': techStack, 'inContainerApps': inContainerApps, 'backendConnection': backendConnection, 'users': users, 'server': server, 'project': pcfg['name'], 'type': type}

    def getLabel(self, cfg, name):
        if 'labels' not in cfg or name not in cfg['labels']:
            if 'workloadLabels' not in cfg or name not in cfg['workloadLabels']:
                return None
            else:
                return cfg['workloadLabels'][name]
        return cfg['labels'][name]

    def getAnnotation(self, cfg, name):
        if 'annotations' not in cfg or name not in cfg['annotations']:
            if 'workloadAnnotations' not in cfg or name not in cfg['workloadAnnotations']:
                return None
            else:
                return cfg['workloadAnnotations'][name]
        return cfg['annotations'][name]
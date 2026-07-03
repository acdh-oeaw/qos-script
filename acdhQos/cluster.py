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
        self.base_url = apiBase.rstrip('/')
        self.apiBase = self.base_url
        self.project = project
        self.skipProjects = skipProjects or []
        self.skipClusters = skipClusters or []
        self.skipTypes = skipTypes or []
        
        self.session = requests.Session()
        # Rancher expects API keys as a Bearer token in the Authorization header.
        # A 401/403 usually means the token is invalid, has wrong scope, or lacks permissions.
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
            'User-Agent': 'ACDH-QoS-Rancher/1.0',
        })

        try:
            resp = self.session.get(f'{self.base_url}/clusters', timeout=30)
            resp.raise_for_status()  # Ensure the request was successful
        except requests.exceptions.HTTPError as e:
            status = resp.status_code if resp is not None else 'unknown'
            if status in (401, 403):
                raise Exception(
                    f'Failed to authenticate with Rancher at {self.base_url}. '
                    f'Status code: {status}. Check RANCHER_TOKEN, its scope/permissions, and the Rancher URL.'
                ) from e
            raise
        except requests.RequestException as e:
            raise Exception(f'Failed to connect to Rancher at {self.base_url}/clusters: {e}') from e

        clusters = resp.json().get('data', [])
        if self.skipClusters:
            clusters = [cluster for cluster in clusters if cluster['id'] not in self.skipClusters]
        self.clusters = {x['id']: x['name'] for x in clusters}
    
    def getClusters(self):
        return self.clusters.values()

    def harvest(self):
        data = []
        try:
            resp = self.session.get(f'{self.base_url}/projects', timeout=30)
            resp.raise_for_status()
            projects = resp.json().get('data', [])
            logging.info(f"Found {len(projects)} projects")

            for project in projects:
                logging.info(f"Checking project {project['name']}")
                if (self.project is not None and project['name'] != self.project) or project['name'] in self.skipProjects:
                    logging.info(f"Skipping project {project['name']} due to project filter")
                    continue
                try:
                    logging.info(f"Processing project {project['name']}")
                    resp = self.session.get(f'{self.base_url}/project/{project["id"]}/workloads', timeout=30)
                    resp.raise_for_status()
                    workloads = resp.json().get('data', [])
                    logging.info(f"Found {len(workloads)} workloads in project {project['name']}")
                    logging.debug("Workloads: %s", workloads)

                    # Fetch ingresses for the project
                    ingresses_resp = self.session.get(f'{self.base_url}/project/{project["id"]}/ingresses', timeout=30)
                    ingresses_resp.raise_for_status()
                    ingresses = ingresses_resp.json().get('data', [])
                    logging.info(f"Found {len(ingresses)} ingresses in project {project['name']}")
                    logging.debug("Ingresses: %s", ingresses)

                    for workload in workloads:
                        if workload['type'] in self.skipTypes:
                            logging.info(f"Skipping workload {workload['name']} due to type filter")
                            continue

                        # Check if the workload has an associated ingress
                        has_ingress = any(
                            workload['name'] in ingress['name'] for ingress in ingresses
                        )
                        logging.debug("Workload %s has ingress: %s", workload['name'], has_ingress)

                        if has_ingress:
                            logging.info(f"Processing workload {workload['name']}")
                            data.append(self.processWorkload(workload, project))
                        else:
                            logging.info(f"Skipping workload {workload['name']} (no ingress)")
                except Exception as e:
                    logging.error(f"Error processing project {project['name']}: {traceback.format_exc()}")
        except Exception as e:
            logging.error(f"Failed to fetch projects: {traceback.format_exc()}")
        return data if data else []

    def processWorkload(self, cfg, pcfg):
        name = cfg['name']
        type = cfg['type']
        namespace = cfg.get('namespaceId', '').split(':')[-1] if cfg.get('namespaceId') else ''
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

        users_detailed = []
        users_names = []
        resp = self.session.get(f'{self.base_url}/project/{pcfg["id"]}/projectRoleTemplateBindings', timeout=30)
        resp.raise_for_status()
        for user in resp.json()['data']:
            if user.get('userPrincipalId') is not None:
                username = re.sub('.*CN=([^,]*),OU=.*', '\\1', user['userPrincipalId'].replace('\\,', ''))
                users_detailed.append(username + ' (' + user['userId'] + '): ' + user['roleTemplateId'])
                users_names.append(username)
        users = '\n'.join(sorted(set(users_detailed)))
        users_short = ', '.join(sorted(set(users_names)))

        return {'name': name, 'id': redmineId, 'endpoint': endpoint, 'techStack': techStack, 'inContainerApps': inContainerApps, 'backendConnection': backendConnection, 'users': users, 'users_short': users_short, 'server': server, 'project': pcfg['name'], 'type': type, 'namespace': namespace}

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
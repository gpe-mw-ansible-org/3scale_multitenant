#!/usr/bin/python

import os

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.yedit import Yedit
from ansible.module_utils.openshift import Utils
from ansible.module_utils.openshift import OpenShiftCLI

class RouteConfig(object):
    ''' Handle route options '''
    # pylint: disable=too-many-arguments
    def __init__(self,
                 sname,
                 namespace,
                 oc_binary,
                 labels=None,
                 destcacert=None,
                 cacert=None,
                 cert=None,
                 key=None,
                 host=None,
                 tls_termination=None,
                 service_name=None,
                 wildcard_policy=None,
                 weight=None,
                 port=None):
        ''' constructor for handling route options '''
        self.oc_binary = oc_binary
        self.name = sname
        self.namespace = namespace
        self.labels = labels
        self.host = host
        self.tls_termination = tls_termination
        self.destcacert = destcacert
        self.cacert = cacert
        self.cert = cert
        self.key = key
        self.service_name = service_name
        self.port = port
        self.data = {}
        self.wildcard_policy = wildcard_policy
        if wildcard_policy is None:
            self.wildcard_policy = 'None'
        self.weight = weight
        if weight is None:
            self.weight = 100

        self.create_dict()

    def create_dict(self):
        ''' return a service as a dict '''
        self.data['apiVersion'] = 'v1'
        self.data['kind'] = 'Route'
        self.data['metadata'] = {}
        self.data['metadata']['name'] = self.name
        self.data['metadata']['namespace'] = self.namespace
        if self.labels:
            self.data['metadata']['labels'] = self.labels
        self.data['spec'] = {}

        self.data['spec']['host'] = self.host

        if self.tls_termination:
            self.data['spec']['tls'] = {}

            self.data['spec']['tls']['termination'] = self.tls_termination

            if self.tls_termination != 'passthrough':
                self.data['spec']['tls']['key'] = self.key
                self.data['spec']['tls']['caCertificate'] = self.cacert
                self.data['spec']['tls']['certificate'] = self.cert

            if self.tls_termination == 'reencrypt':
                self.data['spec']['tls']['destinationCACertificate'] = self.destcacert

        self.data['spec']['to'] = {'kind': 'Service',
                                   'name': self.service_name,
                                   'weight': self.weight}

        self.data['spec']['wildcardPolicy'] = self.wildcard_policy

        if self.port:
            self.data['spec']['port'] = {}
            self.data['spec']['port']['targetPort'] = self.port

# pylint: disable=too-many-instance-attributes,too-many-public-methods
class Route(Yedit):
    ''' Class to wrap the oc command line tools '''
    wildcard_policy = "spec.wildcardPolicy"
    host_path = "spec.host"
    port_path = "spec.port.targetPort"
    service_path = "spec.to.name"
    weight_path = "spec.to.weight"
    cert_path = "spec.tls.certificate"
    cacert_path = "spec.tls.caCertificate"
    destcacert_path = "spec.tls.destinationCACertificate"
    termination_path = "spec.tls.termination"
    key_path = "spec.tls.key"
    kind = 'route'

    def __init__(self, content):
        '''Route constructor'''
        super(Route, self).__init__(content=content)

    def get_destcacert(self):
        ''' return cert '''
        return self.get(Route.destcacert_path)

    def get_cert(self):
        ''' return cert '''
        return self.get(Route.cert_path)

    def get_key(self):
        ''' return key '''
        return self.get(Route.key_path)

    def get_cacert(self):
        ''' return cacert '''
        return self.get(Route.cacert_path)

    def get_service(self):
        ''' return service name '''
        return self.get(Route.service_path)

    def get_weight(self):
        ''' return service weight '''
        return self.get(Route.weight_path)

    def get_termination(self):
        ''' return tls termination'''
        return self.get(Route.termination_path)

    def get_host(self):
        ''' return host '''
        return self.get(Route.host_path)

    def get_port(self):
        ''' return port '''
        return self.get(Route.port_path)

    def get_wildcard_policy(self):
        ''' return wildcardPolicy '''
        return self.get(Route.wildcard_policy)

class OCRoute(OpenShiftCLI):
    ''' Class to wrap the oc command line tools '''
    kind = 'route'

    def __init__(self,
                 config,
                 verbose=False):
        ''' Constructor for OCVolume '''
        super(OCRoute, self).__init__(config.namespace, oc_binary=config.oc_binary, verbose=verbose)
        self.config = config
        self._route = None

    @property
    def route(self):
        ''' property function for route'''
        if not self._route:
            self.get()
        return self._route

    @route.setter
    def route(self, data):
        ''' setter function for route '''
        self._route = data

    def exists(self):
        ''' return whether a route exists '''
        if self.route:
            return True

        return False

    def get(self):
        '''return route information '''
        result = self._get(self.kind, self.config.name)
        if result['returncode'] == 0:
            self.route = Route(content=result['results'][0])
        elif 'routes \"%s\" not found' % self.config.name in result['stderr']:
            result['returncode'] = 0
            result['results'] = [{}]
        elif 'namespaces \"%s\" not found' % self.config.namespace in result['stderr']:
            result['returncode'] = 0
            result['results'] = [{}]

        return result

    def delete(self):
        '''delete the object'''
        return self._delete(self.kind, self.config.name)

    def create(self):
        '''create the object'''
        return self._create_from_content(self.config.name, self.config.data)

    def update(self):
        '''update the object'''
        return self._replace_content(self.kind,
                                     self.config.name,
                                     self.config.data,
                                     force=(self.config.host != self.route.get_host()))

    def needs_update(self):
        ''' verify an update is needed '''
        skip = []
        return not Utils.check_def_equal(self.config.data, self.route.yaml_dict, skip_keys=skip, debug=self.verbose)

    @staticmethod
    def get_cert_data(path, content):
        '''get the data for a particular value'''
        rval = None
        if path and os.path.exists(path) and os.access(path, os.R_OK):
            rval = open(path).read()
        elif content:
            rval = content

        return rval

    # pylint: disable=too-many-return-statements,too-many-branches
    @staticmethod
    def run_ansible(params, check_mode=False):
        ''' run the oc_route module

            params comes from the ansible portion for this module
            files: a dictionary for the certificates
                   {'cert': {'path': '',
                             'content': '',
                             'value': ''
                            }
                   }
            check_mode: does the module support check mode.  (module.check_mode)
        '''
        files = {'destcacert': {'path': params['dest_cacert_path'],
                                'content': params['dest_cacert_content'],
                                'value': None, },
                 'cacert': {'path': params['cacert_path'],
                            'content': params['cacert_content'],
                            'value': None, },
                 'cert': {'path': params['cert_path'],
                          'content': params['cert_content'],
                          'value': None, },
                 'key': {'path': params['key_path'],
                         'content': params['key_content'],
                         'value': None, }, }

        if params['tls_termination'] and params['tls_termination'].lower() != 'passthrough':  # E501

            for key, option in files.items():
                if not option['path'] and not option['content']:
                    continue

                option['value'] = OCRoute.get_cert_data(option['path'], option['content'])  # E501

                if not option['value']:
                    return {'failed': True,
                            'msg': 'Verify that you pass a correct value for %s' % key}

        rconfig = RouteConfig(params['name'],
                              params['namespace'],
                              params['oc_binary'],
                              params['labels'],
                              files['destcacert']['value'],
                              files['cacert']['value'],
                              files['cert']['value'],
                              files['key']['value'],
                              params['host'],
                              params['tls_termination'],
                              params['service_name'],
                              params['wildcard_policy'],
                              params['weight'],
                              params['port'])

        oc_route = OCRoute(rconfig, verbose=params['debug'])

        state = params['state']

        api_rval = oc_route.get()

        #####
        # Get
        #####
        if state == 'list':
            return {'changed': False,
                    'ansible_module_results': api_rval['results'],
                    'state': 'list'}

        ########
        # Delete
        ########
        if state == 'absent':
            if oc_route.exists():

                if check_mode:
                    return {'changed': False, 'msg': 'CHECK_MODE: Would have performed a delete.'}  # noqa: E501

                api_rval = oc_route.delete()

                return {'changed': True, 'ansible_module_results': api_rval, 'state': "absent"}  # noqa: E501
            return {'changed': False, 'state': 'absent'}

        if state == 'present':
            ########
            # Create
            ########
            if not oc_route.exists():

                if check_mode:
                    return {'changed': True, 'msg': 'CHECK_MODE: Would have performed a create.'}  # noqa: E501

                # Create it here
                api_rval = oc_route.create()

                if api_rval['returncode'] != 0:
                    return {'failed': True, 'msg': api_rval, 'state': "present"}  # noqa: E501

                # return the created object
                api_rval = oc_route.get()

                if api_rval['returncode'] != 0:
                    return {'failed': True, 'msg': api_rval, 'state': "present"}  # noqa: E501

                return {'changed': True, 'ansible_module_results': api_rval, 'state': "present"}  # noqa: E501

            ########
            # Update
            ########
            # if update is set to false, return
            update = params['update']
            if not update:
                return {'changed': False, 'ansible_module_results': api_rval, 'state': state}

            if oc_route.needs_update():

                if check_mode:
                    return {'changed': True, 'msg': 'CHECK_MODE: Would have performed an update.'}  # noqa: E501

                api_rval = oc_route.update()

                if api_rval['returncode'] != 0:
                    return {'failed': True, 'msg': api_rval, 'state': "present"}  # noqa: E501

                # return the created object
                api_rval = oc_route.get()

                if api_rval['returncode'] != 0:
                    return {'failed': True, 'msg': api_rval, 'state': "present"}  # noqa: E501

                return {'changed': True, 'ansible_module_results': api_rval, 'state': "present"}  # noqa: E501

            return {'changed': False, 'ansible_module_results': api_rval, 'state': "present"}

        # catch all
        return {'failed': True, 'msg': "Unknown State passed"}

def main():
    '''
    ansible oc module for route
    '''
    module = AnsibleModule(
        argument_spec=dict(
            oc_binary=dict(default=None, require=True, type='str'),
            state=dict(default='present', type='str',
                       choices=['present', 'absent', 'list']),
            debug=dict(default=False, type='bool'),
            labels=dict(default=None, type='dict'),
            name=dict(default=None, required=True, type='str'),
            namespace=dict(default=None, required=True, type='str'),
            tls_termination=dict(default=None, type='str'),
            dest_cacert_path=dict(default=None, type='str'),
            cacert_path=dict(default=None, type='str'),
            cert_path=dict(default=None, type='str'),
            key_path=dict(default=None, type='str'),
            dest_cacert_content=dict(default=None, type='str'),
            cacert_content=dict(default=None, type='str'),
            cert_content=dict(default=None, type='str'),
            key_content=dict(default=None, type='str'),
            service_name=dict(default=None, type='str'),
            host=dict(default=None, type='str'),
            wildcard_policy=dict(default=None, type='str'),
            weight=dict(default=None, type='int'),
            port=dict(default=None, type='int'),
            update=dict(default=False, type='bool'),
        ),
        mutually_exclusive=[('dest_cacert_path', 'dest_cacert_content'),
                            ('cacert_path', 'cacert_content'),
                            ('cert_path', 'cert_content'),
                            ('key_path', 'key_content'), ],
        supports_check_mode=True,
    )

    results = OCRoute.run_ansible(module.params, module.check_mode)

    if 'failed' in results:
        module.fail_json(**results)

    module.exit_json(**results)


if __name__ == '__main__':
    main()
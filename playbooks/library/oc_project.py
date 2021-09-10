#!/usr/bin/python

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.openshift import OpenShiftCLIConfig
from ansible.module_utils.openshift import OpenShiftCLI
from ansible.module_utils.yedit import Yedit

class ProjectConfig(OpenShiftCLIConfig):

    def __init__(self, rname, namespace, oc_binary, project_options):
        super(ProjectConfig, self).__init__(rname, None, oc_binary, project_options)

class Project(Yedit):

    def __init__(self, content):
        super(Project, self).__init__(content=content)

class OCProject(OpenShiftCLI):

    kind = 'project'

    def __init__(self,
                 config,
                 verbose=False):
        ''' Constructor for OCProject '''
        super(OCProject, self).__init__(None, config.oc_binary)
        self.config = config
        self._project = None

    @property
    def project(self):
        ''' property for project'''
        if not self._project:
            self.get()
        return self._project

    @project.setter
    def project(self, data):
        ''' setter function for project propeorty'''
        self._project = data

    def exists(self):
        ''' return whether a project exists '''
        if self.project:
            return True

        return False

    def get(self):
        '''return project '''
        result = self._get(self.kind, self.config.name)

        if result['returncode'] == 0:
            self.project = Project(content=result['results'][0])
            result['results'] = self.project.yaml_dict

        elif 'namespaces "%s" not found' % self.config.name in result['stderr']:
            result = {'results': [], 'returncode': 0}

        return result

    def delete(self):
        '''delete the object'''
        return self._delete(self.kind, self.config.name)

    def create(self):
        '''create a project '''
        cmd = ['new-project', self.config.name]
        cmd.extend(self.config.to_option_list())

        return self.openshift_cmd(cmd, oadm=False)

    @staticmethod
    def run_ansible(params, check_mode):

        pconfig = ProjectConfig(
            params['name'],
            'None',
            params['oc_binary'],
            {
                'description': {'value': params['description'], 'include': True},
                'display_name': {'value': params['display_name'], 'include': True},
            },
        )
        
        oadm_project = OCProject(pconfig, verbose=params['debug'])

        state = params['state']

        api_rval = oadm_project.get()

        #####
        # Get
        #####
        if state == 'list':
            return {'changed': False, 'ansible_module_results': api_rval['results'], 'state': state}

        ########
        # Delete
        ########
        if state == 'absent':
            if oadm_project.exists():

                if check_mode:
                    return {'changed': True, 'msg': 'CHECK_MODE: Would have performed a delete.'}

                api_rval = oadm_project.delete()

                if api_rval['returncode'] != 0:
                    return {'failed': True, 'msg': api_rval}

                return {'changed': True, 'ansible_module_results': api_rval, 'state': state}

            return {'changed': False, 'state': state}

        if state == 'present':
            ########
            # Create
            ########
            if not oadm_project.exists():

                if check_mode:
                    return {'changed': True, 'msg': 'CHECK_MODE: Would have performed a create.'}

                # Create it here
                api_rval = oadm_project.create()

                if api_rval['returncode'] != 0:
                    return {'failed': True, 'msg': api_rval}

                # return the created object
                api_rval = oadm_project.get()

                if api_rval['returncode'] != 0:
                    return {'failed': True, 'msg': api_rval}

                return {'changed': True, 'ansible_module_results': api_rval, 'state': state}

            return {'changed': False, 'ansible_module_results': api_rval, 'state': state}


def main():
    module_args = dict(
        oc_binary=dict(default=None, require=True, type='str'),
        state=dict(default='present', type='str',
                   choices=['present', 'absent', 'list']),
        debug=dict(default=False, type='bool'),
        name=dict(default=None, require=True, type='str'),
        display_name=dict(default=None, type='str'),
        description=dict(default=None, type='str'),
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    rval = OCProject.run_ansible(module.params, module.check_mode)
    if 'failed' in rval:
        return module.fail_json(**rval)

    return module.exit_json(**rval)

if __name__ == '__main__':
    main()

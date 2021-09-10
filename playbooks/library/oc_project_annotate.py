#!/usr/bin/python

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.openshift import OpenShiftCLIConfig
from ansible.module_utils.openshift import OpenShiftCLI

class ProjectConfig(OpenShiftCLIConfig):

    def __init__(self, rname, oc_binary, project_options):
        super(ProjectConfig, self).__init__(rname, None, oc_binary, project_options)

class OCProject(OpenShiftCLI):

    def __init__(self,
                 config,
                 verbose=False):
        ''' Constructor for OCProject '''
        super(OCProject, self).__init__(None, config.oc_binary)
        self.config = config

    def annotate(self):
        '''annotate the project'''
        cmd = ['annotate', 'namespace', self.config.name, self.config.config_options['annotations']['value']]
        cmd.extend(['--overwrite'])
        return self.openshift_cmd(cmd, oadm=False)

    
    @staticmethod
    def run_ansible(params, check_mode):

        pConfig = ProjectConfig(
            params['name'],
            params['oc_binary'],
            {'annotations': {'value': params['annotations'], 'include': False},
            },
        )

        project = OCProject(pConfig, params['debug'])

        state = params['state']
        
        if state == 'present':
            ########
            # Create
            ########
            if check_mode:
                return {'changed': True, 'msg': 'CHECK_MODE: would have performed a create'}
            
            api_rval = project.annotate()
            
            if api_rval['returncode'] != 0:
                return {'failed': True, 'msg': api_rval}

            return {'changed': True, 'ansible_module_results': api_rval, state: 'present'}
        
        return {'failed': True, 'changed': False, 'ansible_module_results': 'Unknown state passed. %s' % state, state: 'unknown'}


def main():
    module_args = dict(
        oc_binary=dict(default=None, require=True, type='str'),
        state=dict(default='present', type='str',
                   choices=['present', 'absent', 'list']),
        debug=dict(default=False, type='bool'),
        name=dict(default=None, require=True, type='str'),
        annotations=dict(default=None, type='str'),
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
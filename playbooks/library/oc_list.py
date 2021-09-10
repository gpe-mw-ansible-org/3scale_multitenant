#!/usr/bin/python

try:
    import ruamel.yaml as yaml
except ImportError:
    import yaml


from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.openshift import OpenShiftCLI
from ansible.module_utils.openshift import Utils


class OCList(OpenShiftCLI):
    ''' Class to wrap the oc command line tools '''

    def __init__(self,
                 namespace,
                 selector=None,
                 oc_binary=None,
                 verbose=False,
                 field_selector=None):
        ''' Constructor for OpenshiftOC '''
        super(OCList, self).__init__(namespace, oc_binary=oc_binary, verbose=verbose,
                                       all_namespaces=False)
        self.selector = selector
        self.field_selector = field_selector

    def get(self):
        '''return a kind by name '''
        results = self._get(self.kind, name=self.name, selector=self.selector, field_selector=self.field_selector)
        if (results['returncode'] != 0 and 'stderr' in results and
                '\"{}\" not found'.format(self.name) in results['stderr']):
            results['returncode'] = 0

        return results

    def delete(self):
        '''delete the object'''
        results = self._delete(self.kind, name=self.name, selector=self.selector)
        if (results['returncode'] != 0 and 'stderr' in results and
                '\"{}\" not found'.format(self.name) in results['stderr']):
            results['returncode'] = 0

        return results

    def create(self, files=None, content=None):
        '''
           Create a config

           NOTE: This creates the first file OR the first conent.
           TODO: Handle all files and content passed in
        '''
        if files:
            return self._create(files[0])

        # The purpose of this change is twofold:
        # - we need a check to only use the ruamel specific dumper if ruamel is loaded
        # - the dumper or the flow style change is needed so openshift is able to parse
        # the resulting yaml, at least until gopkg.in/yaml.v2 is updated
        if hasattr(yaml, 'RoundTripDumper'):
            content['data'] = yaml.dump(content['data'], Dumper=yaml.RoundTripDumper)
        else:
            content['data'] = yaml.safe_dump(content['data'], default_flow_style=False)

        content_file = Utils.create_tmp_files_from_contents(content)[0]

        return self._create(content_file['path'])

    def update(self, files=None, content=None, force=False):
        '''update a current openshift object

           This receives a list of file names or content
           and takes the first and calls replace.

           TODO: take an entire list
        '''
        if files:
            return self._replace(files[0], force)

        if content and 'data' in content:
            content = content['data']

        return self.update_content(content, force)

    def update_content(self, content, force=False):
        '''update an object through using the content param'''
        return self._replace_content(self.kind, self.name, content, force=force)

    def needs_update(self, files=None, content=None, content_type='yaml'):
        ''' check to see if we need to update '''
        objects = self.get()
        if objects['returncode'] != 0:
            return objects

        data = None
        if files:
            data = Utils.get_resource_file(files[0], content_type)
        elif content and 'data' in content:
            data = content['data']
        else:
            data = content

            # if equal then no need.  So not equal is True
        return not Utils.check_def_equal(data, objects['results'][0], skip_keys=None, debug=False)

    @staticmethod
    def run_ansible(params, check_mode=False):
        '''run the oc_obj module'''

        ocobj = OCList(params['namespace'],
                       params['selector'],
                       oc_binary=params['oc_binary'],
                       verbose=params['debug'],
                       field_selector=params['field_selector'])

        state = params['state']

        if state == 'present':
            ########
            # Create
            ########
            if check_mode:
                return {'changed': True, 'msg': 'CHECK_MODE: Would have performed a create'}

            # Create it here
            api_rval = ocobj.create(params['files'], params['content'])
            if api_rval['returncode'] != 0:
                return {'failed': True, 'msg': api_rval}

            # Remove files
            if params['files'] and params['delete_after']:
                Utils.cleanup(params['files'])

            return {'changed': True, 'ansible_module_results': api_rval, 'state': state}

        # catch all
        return {'failed': True, 'msg': "Unknown State passed"}

def main():
    '''
    ansible oc module for services
    '''

    module = AnsibleModule(
        argument_spec=dict(
            oc_binary=dict(default=None, require=True, type='str'),
            state=dict(default='present', type='str',
                       choices=['present']),
            debug=dict(default=False, type='bool'),
            namespace=dict(default='default', type='str'),
            files=dict(default=None, type='list'),
            delete_after=dict(default=False, type='bool'),
            content=dict(default=None, type='dict'),
            force=dict(default=False, type='bool'),
            selector=dict(default=None, type='str'),
            field_selector=dict(default=None, type='str'),
        ),
        mutually_exclusive=[["content", "files"], ["selector", "name"], ["field_selector", "name"]],

        supports_check_mode=True,
    )
    rval = OCList.run_ansible(module.params, module.check_mode)
    if 'failed' in rval:
        module.fail_json(**rval)

    module.exit_json(**rval)

if __name__ == '__main__':
    main()
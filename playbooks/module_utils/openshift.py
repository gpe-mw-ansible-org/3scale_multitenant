#!/usr/bin/python

import atexit
import os
import shutil
import tempfile
import subprocess
import json
try:
    import ruamel.yaml as yaml
except ImportError:
    import yaml

from ansible.module_utils.yedit import Yedit

class OpenShiftCLIError(Exception):
    '''Exception class for openshiftcli'''
    pass

class OpenShiftCLI(object):
    ''' Class to wrap the command line tools '''
    def __init__(self,
                 namespace,
                 oc_binary,
                 verbose=False,
                 all_namespaces=False):
        ''' Constructor for OpenshiftCLI '''
        self.namespace = namespace
        self.verbose = verbose
        self.oc_binary = oc_binary
        self.all_namespaces = all_namespaces

    def _replace_content(self, resource, rname, content, edits=None, force=False, sep='.'):
        ''' replace the current object with the content '''
        res = self._get(resource, rname)
        if not res['results']:
            return res

        fname = Utils.create_tmpfile(rname + '-')

        yed = Yedit(fname, res['results'][0], separator=sep)
        updated = False

        if content is not None:
            changes = []
            for key, value in content.items():
                changes.append(yed.put(key, value))

            if any([change[0] for change in changes]):
                updated = True

        elif edits is not None:
            results = Yedit.process_edits(edits, yed)

            if results['changed']:
                updated = True

        if updated:
            yed.write()
            atexit.register(Utils.cleanup, [fname])

            return self._replace(fname, force)

        return {'returncode': 0, 'updated': False}

    def _replace(self, fname, force=False):
        '''replace the current object with oc replace'''
        # We are removing the 'resourceVersion' to handle
        # a race condition when modifying oc objects
        yed = Yedit(fname)
        results = yed.delete('metadata.resourceVersion')
        if results[0]:
            yed.write()

        cmd = ['replace', '-f', fname]
        if force:
            cmd.append('--force')
        return self.openshift_cmd(cmd)

    def _create_from_content(self, rname, content):
        '''create a temporary file and then call oc create on it'''
        fname = Utils.create_tmpfile(rname + '-')
        yed = Yedit(fname, content=content)
        yed.write()

        atexit.register(Utils.cleanup, [fname])

        return self._create(fname)

    def _create(self, fname):
        '''call oc create on a filename'''
        return self.openshift_cmd(['create', '-f', fname])

    def _get(self, resource, name=None, selector=None, field_selector=None):
        '''return a resource by name '''
        cmd = ['get', resource]

        if selector is not None:
            cmd.append('--selector={}'.format(selector))

        if field_selector is not None:
            cmd.append('--field-selector={}'.format(field_selector))

        # Name cannot be used with selector or field_selector.
        if selector is None and field_selector is None and name is not None:
            cmd.append(name)

        cmd.extend(['-o', 'json'])

        rval = self.openshift_cmd(cmd, output=True)

        # Ensure results are retuned in an array
        if 'items' in rval:
            rval['results'] = rval['items']
        elif not isinstance(rval['results'], list):
            rval['results'] = [rval['results']]

        return rval

    def _run(self, cmds, input_data):
        ''' Actually executes the command. This makes mocking easier. '''
        curr_env = os.environ.copy()
        proc = subprocess.Popen(cmds,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env=curr_env)

        stdout, stderr = proc.communicate(input_data)

        return proc.returncode, stdout.decode('utf-8'), stderr.decode('utf-8')

    def _delete(self, resource, name=None, selector=None):
        '''call oc delete on a resource'''
        cmd = ['delete', resource]
        if selector is not None:
            cmd.append('--selector={}'.format(selector))
        elif name is not None:
            cmd.append(name)
        else:
            raise OpenShiftCLIError('Either name or selector is required when calling delete.')

        return self.openshift_cmd(cmd)

    def openshift_cmd(self, cmd, oadm=False, output=False, output_type='json', input_data=None):

        '''Base command for oc '''
        cmds = [self.oc_binary]

        if oadm:
            cmds.append('adm')

        cmds.extend(cmd)

        if self.all_namespaces:
            cmds.extend(['--all-namespaces'])
        elif self.namespace is not None and self.namespace.lower() not in ['none', 'emtpy']:  # E501
            cmds.extend(['-n', self.namespace])

        if self.verbose:
            print(' '.join(cmds))

        try:
            returncode, stdout, stderr = self._run(cmds, input_data)
        except OSError as ex:
            returncode, stdout, stderr = 1, '', 'Failed to execute {}: {}'.format(subprocess.list2cmdline(cmds), ex)

        rval = {"returncode": returncode,
                "cmd": ' '.join(cmds)}

        if output_type == 'json':
            rval['results'] = {}
            if output and stdout:
                try:
                    rval['results'] = json.loads(stdout)
                except ValueError as verr:
                    if "No JSON object could be decoded" in verr.args:
                        rval['err'] = verr.args
        elif output_type == 'raw':
            rval['results'] = stdout if output else ''

        if self.verbose:
            print("STDOUT: {0}".format(stdout))
            print("STDERR: {0}".format(stderr))

        if 'err' in rval or returncode != 0:
            rval.update({"stderr": stderr,
                         "stdout": stdout})

        return rval


class Utils(object):

    @staticmethod
    def _write(filename, contents):
        with open(filename, 'w') as sfd:
            sfd.write(str(contents))

    @staticmethod
    def create_tmp_file_from_contents(rname, data, ftype='yaml'):
        ''' create a file in tmp with name and contents'''

        tmp = Utils.create_tmpfile(prefix=rname)

        if ftype == 'yaml':
            # AUDIT:no-member makes sense here due to ruamel.YAML/PyYAML usage
            if hasattr(yaml, 'RoundTripDumper'):
                Utils._write(tmp, yaml.dump(data, Dumper=yaml.RoundTripDumper))
            else:
                Utils._write(tmp, yaml.safe_dump(data, default_flow_style=False))

        elif ftype == 'json':
            Utils._write(tmp, json.dumps(data))
        else:
            Utils._write(tmp, data)

        # Register cleanup when module is done
        atexit.register(Utils.cleanup, [tmp])
        return tmp

    @staticmethod
    def create_tmp_files_from_contents(content, content_type=None):
        '''Turn an array of dict: filename, content into a files array'''
        if not isinstance(content, list):
            content = [content]
        files = []
        for item in content:
            path = Utils.create_tmp_file_from_contents(item['path'] + '-',
                                                       item['data'],
                                                       ftype=content_type)
            files.append({'name': os.path.basename(item['path']),
                          'path': path})
        return files

    @staticmethod
    def cleanup(files):
        '''Clean up on exit '''
        for sfile in files:
            if os.path.exists(sfile):
                if os.path.isdir(sfile):
                    shutil.rmtree(sfile)
                elif os.path.isfile(sfile):
                    os.remove(sfile)

    @staticmethod
    def exists(results, _name):
        ''' Check to see if the results include the name '''
        if not results:
            return False

        if Utils.find_result(results, _name):
            return True

        return False

    @staticmethod
    def find_result(results, _name):
        ''' Find the specified result by name'''
        rval = None
        for result in results:
            if 'metadata' in result and result['metadata']['name'] == _name:
                rval = result
                break

        return rval

    @staticmethod
    def get_resource_file(sfile, sfile_type='yaml'):
        ''' return the service file '''
        contents = None
        with open(sfile) as sfd:
            contents = sfd.read()

        if sfile_type == 'yaml':
            # AUDIT:no-member makes sense here due to ruamel.YAML/PyYAML usage
            if hasattr(yaml, 'RoundTripLoader'):
                contents = yaml.load(contents, yaml.RoundTripLoader)
            else:
                contents = yaml.safe_load(contents)
        elif sfile_type == 'json':
            contents = json.loads(contents)

        return contents
    
    @staticmethod
    def create_tmpfile_copy(inc_file):
        '''create a temporary copy of a file'''
        tmpfile = Utils.create_tmpfile('lib_openshift-')
        Utils._write(tmpfile, open(inc_file).read())

        # Cleanup the tmpfile
        atexit.register(Utils.cleanup, [tmpfile])

        return tmpfile

    @staticmethod
    def create_tmpfile(prefix='tmp'):
        ''' Generates and returns a temporary file name '''

        with tempfile.NamedTemporaryFile(prefix=prefix, delete=False) as tmp:
            return tmp.name

    @staticmethod
    def check_def_equal(user_def, result_def, skip_keys=None, debug=False):
        ''' Given a user defined definition, compare it with the results given back by our query.  '''

        # Currently these values are autogenerated and we do not need to check them
        skip = ['metadata', 'status']
        if skip_keys:
            skip.extend(skip_keys)

        for key, value in result_def.items():
            if key in skip:
                continue

            # Both are lists
            if isinstance(value, list):
                if key not in user_def:
                    if debug:
                        print('User data does not have key [%s]' % key)
                        print('User data: %s' % user_def)
                    return False

                if not isinstance(user_def[key], list):
                    if debug:
                        print('user_def[key] is not a list key=[%s] user_def[key]=%s' % (key, user_def[key]))
                    return False

                if len(user_def[key]) != len(value):
                    if debug:
                        print("List lengths are not equal.")
                        print("key=[%s]: user_def[%s] != value[%s]" % (key, len(user_def[key]), len(value)))
                        print("user_def: %s" % user_def[key])
                        print("value: %s" % value)
                    return False

                for values in zip(user_def[key], value):
                    if isinstance(values[0], dict) and isinstance(values[1], dict):
                        if debug:
                            print('sending list - list')
                            print(type(values[0]))
                            print(type(values[1]))
                        result = Utils.check_def_equal(values[0], values[1], skip_keys=skip_keys, debug=debug)
                        if not result:
                            print('list compare returned false')
                            return False

                    elif value != user_def[key]:
                        if debug:
                            print('value should be identical')
                            print(user_def[key])
                            print(value)
                        return False

            # recurse on a dictionary
            elif isinstance(value, dict):
                if key not in user_def:
                    if debug:
                        print("user_def does not have key [%s]" % key)
                    return False
                if not isinstance(user_def[key], dict):
                    if debug:
                        print("dict returned false: not instance of dict")
                    return False

                # before passing ensure keys match
                api_values = set(value.keys()) - set(skip)
                user_values = set(user_def[key].keys()) - set(skip)
                if api_values != user_values:
                    if debug:
                        print("keys are not equal in dict")
                        print(user_values)
                        print(api_values)
                    return False

                result = Utils.check_def_equal(user_def[key], value, skip_keys=skip_keys, debug=debug)
                if not result:
                    if debug:
                        print("dict returned false")
                        print(result)
                    return False

            # Verify each key, value pair is the same
            else:
                if key not in user_def or value != user_def[key]:
                    if debug:
                        print("value not equal; user_def does not have key")
                        print(key)
                        print(value)
                        if key in user_def:
                            print(user_def[key])
                    return False

        if debug:
            print('returning true')
        return True

class OpenShiftCLIConfig(object):
    '''Generic Config'''
    def __init__(self, rname, namespace, oc_binary, options):
        self.oc_binary = oc_binary
        self.name = rname
        self.namespace = namespace
        self._options = options

    @property
    def config_options(self):
        ''' return config options '''
        return self._options

    def to_option_list(self, ascommalist=''):
        '''return all options as a string
           if ascommalist is set to the name of a key, and
           the value of that key is a dict, format the dict
           as a list of comma delimited key=value pairs'''
        return self.stringify(ascommalist)

    def stringify(self, ascommalist=''):
        ''' return the options hash as cli params in a string
            if ascommalist is set to the name of a key, and
            the value of that key is a dict, format the dict
            as a list of comma delimited key=value pairs '''
        rval = []
        for key in sorted(self.config_options.keys()):
            data = self.config_options[key]
            if data['include'] \
               and (data['value'] is not None or isinstance(data['value'], int)):
                if key == ascommalist:
                    val = ','.join(['{}={}'.format(kk, vv) for kk, vv in sorted(data['value'].items())])
                else:
                    val = data['value']
                rval.append('--{}={}'.format(key.replace('_', '-'), val))

        return rval

from twisted.web import resource, server
from twisted.internet import defer, threads

import json
import os
import subprocess
import traceback
from txrestapi.resource import APIResource
from txrestapi.methods import GET, POST, PUT, ALL

from models import Package, Job
from models import JobStatus
from config import config

def parser_dscfile(dscfile):
    #Just support linux architecture
    arches = {}
    with open(dsc_file) as fp:
        for line in fp:
            if line.startswith('Architecture: '):
                _arches = line.split(':')[1].strip().split(',')
                break
    for arch in _arches:
        if '-' in arch:
            arches.add(arch.split('-')[1])
        else:
            arches.add(arch)
    return list(arches)


def deunicodify_hook(pairs):
    new_pairs = []
    for key, value in pairs:
        if isinstance(value, unicode):
            value = value.encode('utf-8')
        if isinstance(key, unicode):
            key = key.encode('utf-8')
        new_pairs.append((key, value))
    return dict(new_pairs)

def add_task(kwargs):
    if Package.selectBy(**kwargs).count() != 0:
        package = Package.selectBy(**kwargs).orderBy('-id')[0]
        package.triggered = package.triggered + 1
    else:
        package = package(**kwargs)

class Task(APIResource):
    isLeaf = False  

    @POST('/apply')
    def post_apply(self, request):
        '''
        POST /api/task/apply

        {
            "state": "SUCCESS",
            "id": package.dict()
        }
        '''
        request.setHeader("content-type", "application/json")
        
        def get_result():
            content = json.loads(request.content.read(), object_pairs_hook=deunicodify_hook)
            # first will checkif the repo exists
            repopath =  os.path.join(config['cache'].get('repos'), content['reponame'])
            repo_config = os.path.join(repopath, '%s.json' % content['reponame'])
            if not os.path.exists(repo_config):
                raise OSError("Repository has not exists, Please create it first!")
            
            repo_config = json.load(open(repo_config, "r"))
            dist = repo_config.get(content['action'])['dist']
            arches = repo_config.get(content['action'])['arches']

            command = "../tools/git.py --config ../config/default.packages.json"
            command += " --pkgname %(pkgname)s --action %(action)s --cachedir %(cache)s" % {
                "pkgname": content['pkgname'],
                "action": content['action'],
                "cache": config['cache'].get('sources')
            }

            try:
                """result will like blow
                {'files': 
                    ['dde-session-ui_4.3.1+2+gc1ab148.dsc', 
                    'dde-session-ui_4.3.1+2+gc1ab148.tar.xz'], 
                'path': '/tmp/git-archive-temp/tmp3HoN4D',
                'version': '4.3.1+2+gc1ab148', 
                'hashsum': 'c1ab1484818011ab76bbe383101b25d33e923ef4'
                }
                """
                result = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
            except:
                raise
            
            result = eval(result)

            for file in result['files']:
                if file.endswith('.dsc'):
                    dsc_file = os.path.join(result['path'], file)
                    _arches = parser_dscfile(dsc_file)
                    break

            added_arches = {}
            for arch in _arches:
                if arch == 'any':
                    for repo_arch in arches:
                        added_arches.add(repo_arch)
                elif arch == 'all':
                    added_arches.add(arches[0])
                elif arch in repo_arch:
                    added_arches.add(arch)

            if len(added_arches) == 0:
                os.system("rm -rf %s" % result['path'])
                raise OSError("None of architecture support with this action.")

            kwargs = {
                'pkgname': content['pkgname'], 'pkgver': result['version'], 
                'reponame': content['reponame'], 'action': content['action'],
                'hashsum': result['hashsum']
                }

            if Package.selectBy(**kwargs).count() != 0:
                package = Package.selectBy(**kwargs).orderBy('-id')[0]
                package.triggered = package.triggered + 1
            else:
                package = Package(**kwargs)
                for arch in added_arches:
                    Job(package=package, arch=arch, dist=dist, status=JobStatus.WAIT)
                
                #save the source to cache
                tasks_cache = config['cache'].get('tasks')
                if not os.path.exists(tasks_cache):
                    os.makedirs(tasks_cache)
                source_cache = os.path.join(tasks_cache, str(package.id), 'source')
                for file in result['files']:
                    os.system("install -Dm644 %(source)s %(dest)s" % {
                        'source': os.path.join(result['path'], file),
                        'dest': os.path.join(source_cache, file)
                        })
                    
            os.system("rm -rf %s" % result['path'])
            return package.dict()
        
        d = threads.deferToThread(get_result)
        d.addCallback(self.callback, request)
        d.addErrback(self.failure, request)
        return server.NOT_DONE_YET

    @GET('/(?P<id>[^/]+)/info')
    def get_jobinfo(self, request, id):
        '''
        GET /api/task/<id>/info

        {
            "state": "SUCCESS",
            "id": "xxxxx"
        }
        '''
        def get_result():
            package = Package.selectBy(id=id)[0]
            return package.dict()
        
        d = threads.deferToThread(get_result)
        d.addCallback(self.callback, request)
        d.addErrback(self.failure, request)
        return server.NOT_DONE_YET

    def callback(self, result, request):
        request.setResponseCode(200)
        request.write(json.dumps(result))
        request.finish()

    def failure(self, result, request):
        request.setResponseCode(400)
        _result = {"state": "FAILED",
            "message": result.getErrorMessage()
        }
        request.write(json.dumps(_result))
        request.finish()
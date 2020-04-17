import os

import bottle
from bottle import request


FILE_SAVE_DIR = '/tmp'


@bottle.get('/static/<path:path>')
def static(path):
    return bottle.static_file(path, root='static')


@bottle.get('/')
def index():
    return bottle.static_file('mock.html', root='static')


@bottle.post('/upload_solution')
def recv_solution():
    prob_id = request.forms.get('prob_id')
    upload = request.files.get('upload')
    upload.save(os.path.join(FILE_SAVE_DIR, upload.filename))
    return {'status': 'success'}

    
if __name__ == '__main__':
    bottle.run(host='localhost', port=8080)

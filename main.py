from contextlib import contextmanager
import os

import jinja2
from jinja2 import Environment, FileSystemLoader
import bottle
from bottle import request, response
import sqlalchemy

import models
import config


FILE_SAVE_DIR = '/tmp'

engine = sqlalchemy.create_engine(config.CONN_STRING)
Session = sqlalchemy.orm.sessionmaker(bind=engine)
jinja_env = Environment(loader=FileSystemLoader('template'))


def get_problems(hard_level, language):
    root_dir = config.PROBLEM_DIR
    fpath = os.path.join(root_dir, language, hard_level + '.txt')
    with open(fpath) as f:
        return f.read().split('\n\n')


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


def static(path):
    return bottle.static_file(path, root='static')


@bottle.get('/')
def index():
    return bottle.static_file('mock.html', root='static')


@bottle.get('/user/<uid>/prob')
def get_prob_page(uid):
    msg = request.query.get('msg', '')
    hard_level = request.query.get('hard_level', 'easy')
    language = request.query.get('lang', 'english')
    if hard_level not in ('easy', 'hard'):
        # error
        pass
    if language not in ('english', 'spanish'):
        # error
        pass
    with session_scope() as session:
        user = session.query(models.User).filter_by(access_uuid=uid).first()
        if user is None:
            return 'Access Id not found'
        problems = get_problems(hard_level, language)
        return jinja_env.get_template('problems.html').render(
                user=user, problems=problems, msg=msg, 
                lang=language, hard_level=hard_level)


@bottle.post('/upload_solution/<uid>')
def recv_solution(uid):
    prob_id = request.forms.get('prob_id')
    link = request.forms.get('link')
    user_id = request.forms.get('user_id')
    upload = request.files.get('upload', None)
    if upload is not None:
        if link:
            bottle.redirect(
                '/user/{}/prob?msg=cannot+upload+file+and+link+at+the+same+time'.format(uid))
        upload.save(os.path.join(config.FILE_SAVE_DIR, upload.filename))
        link = os.path.join(config.STATIC_FILE_URL, upload.filename)
    redirect_url = '/user/{}/prob?msg=success'.format(uid)
    sub = models.Submission()
    sub.link = link
    sub.user_id = user_id
    sub.prob_id = prob_id
    with session_scope() as session:
        session.add(sub)
    return bottle.redirect(redirect_url)


@bottle.get('/all_solutions')
def all_solutions():
    with session_scope() as session:
        submissions = session.query(models.Submission, models.User).filter(
                models.Submission.user_id == models.User.uid)
        print(list(submissions))
        return jinja_env.get_template('submissions.html'
            ).render(submissions=submissions)


application = bottle.default_app()

if __name__ == '__main__':
    models.Base.metadata.create_all(engine)
    bottle.run(host='localhost', port=8080)

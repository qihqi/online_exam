# -*- coding: utf-8 -*-


from contextlib import contextmanager
import datetime
import os
import uuid

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

ALL_LANG = sorted("""
english
french
spanish
german
uzbek
italian
russian
chinese
japanese
albanian
arabic
hungarian
ukranian
portuguese
dutch-flemish
slovenian
croatian
latvian
turkish
hindi
thai
romanian
""".strip().split('\n'))

ANSWER_LANG = sorted("""
english
spanish
french
arabic
russian
german
italian
thai
hungarian
estonian
""".strip().split('\n'))


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


@bottle.get('/static/<path:path>')
def static(path):
    return bottle.static_file(path, root='static')


@bottle.get('/')
def index():
    return bottle.static_file('mock.html', root='static')

@bottle.get('/user/<uid>')
def get_landing_page(uid):
    with session_scope() as session:
        user = session.query(models.User).filter_by(access_uuid=uid).first()
        if user is None:
            return 'Access Id not found'
    return jinja_env.get_template('landing.html').render(
            uid=uid)


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

        if user.start_timestamp is None:
            session.query(models.User).filter_by(access_uuid=uid).update(
                    {'start_timestamp': datetime.datetime.utcnow()})

        print(user.start_timestamp)
        problems = get_problems(hard_level, language)
        return jinja_env.get_template('problems.html').render(
                user=user, problems=problems, msg=msg, 
                lang=language, hard_level=hard_level, 
                languages=ALL_LANG, answer_lang=ANSWER_LANG)


@bottle.post('/upload_solution/<uid>')
def recv_solution(uid):
    print(request.forms.keys())
    print(request.query.keys())
    prob_id = int(request.forms.get('prob_id'))
    link = request.forms.get('link')
    user_id = int(request.forms.get('user_id'))
    upload = request.files.get('upload', None)
    language = request.forms.get('language')
    timestamp = datetime.datetime.utcnow()
    if upload is not None:
        if link:
            bottle.redirect(
                ('/user/{}/prob?msg=cannot+'
                'upload+file+and+link+at+the+same+time').format(uid))
        orig_name, ext = os.path.splitext(upload.filename)
        new_filename = uuid.uuid4().hex + ext
        upload.save(os.path.join(config.FILE_SAVE_DIR, new_filename))
        link = os.path.join(config.STATIC_FILE_URL, new_filename)
        print(link)
    redirect_url = '/user/{}/prob?msg=success'.format(uid)
    sub = models.Submission()
    sub.link = link
    sub.user_id = user_id
    sub.prob_id = prob_id
    sub.language = language
    sub.timestamp = timestamp
    with session_scope() as session:
        session.add(sub)
    return bottle.redirect(redirect_url)


@bottle.get('/all_solutions')
def all_solutions():
    with session_scope() as session:
        submissions = session.query(models.Submission, models.User).filter(
                models.Submission.user_id == models.User.uid)
        return jinja_env.get_template('submissions.html'
            ).render(submissions=submissions)


application = bottle.default_app()

if __name__ == '__main__':
    models.Base.metadata.create_all(engine)
    bottle.run(host='0.0.0.0', port=8099)

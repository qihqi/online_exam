from contextlib import contextmanager
import os

import jinja2
from jinja2 import Environment, FileSystemLoader
import bottle
from bottle import request, response
import sqlalchemy

import models


FILE_SAVE_DIR = '/tmp'

engine = sqlalchemy.create_engine('mysql://root:no jodas@localhost/online_exam')
Session = sqlalchemy.orm.sessionmaker(bind=engine)
jinja_env = Environment(loader=FileSystemLoader('template'))


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
    with session_scope() as session:
        user = session.query(models.User).filter_by(access_uuid=uid).first()
        if user is None:
            return 'Access Id not found'
        problems = [
            """Prove that \( x^2 - y^2 = (x - y)(x + y) \).""",
            """Prove that \( x^2 - y^2 = (x - y)(x + y) \)."""
        ]
        return jinja_env.get_template('problems.html').render(
                user=user, problems=problems, msg=msg)


@bottle.post('/upload_solution/<uid>')
def recv_solution(uid):
    prob_id = request.forms.get('prob_id')
    link = request.forms.get('link')
    user_id = request.forms.get('user_id')
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
